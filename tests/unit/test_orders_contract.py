"""Unit tests for order creation with CONTRACT payment method.

Tests the B2B contract integration in BaseOrderService.create_order():
- TOCTOU-safe contract lock (Block A)
- Per-product quantity quota reservation (Block B)
- Price override from contract price items
- Quantity release on cancel
"""

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import BadRequestError
from src.modules.contracts.enums import ContractStatus
from src.modules.contracts.exceptions import (
    ContractNotActiveError,
    ContractRequiredError,
    ProductNotInContractError,
    QuantityLimitExceededError,
)
from src.modules.orders.enums import OrderStatus, PaymentMethod
from src.modules.orders.schemas import Item, OrderCreate
from src.modules.orders.services import BaseOrderService
from src.modules.users.enums import Role

# ─── Helpers ──────────────────────────────────────────────


def make_product(
    product_id: uuid.UUID | None = None,
    price: int = 20_000,
    returnable_item_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=product_id or uuid.uuid4(),
        name="Test Water 19L",
        price=price,
        returnable_item_id=returnable_item_id,
        is_active=True,
    )


def make_contract(
    contract_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    status: ContractStatus = ContractStatus.ACTIVE,
    end_date: date | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=contract_id or uuid.uuid4(),
        client_id=client_id or uuid.uuid4(),
        status=status,
        end_date=end_date,
    )


def make_price_item(
    price_item_id: uuid.UUID | None = None,
    contract_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    price: int = 20_000,
    quantity: int = 0,
    quantity_used: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=price_item_id or uuid.uuid4(),
        contract_id=contract_id or uuid.uuid4(),
        product_id=product_id or uuid.uuid4(),
        price=price,
        quantity=quantity,
        quantity_used=quantity_used,
    )


def make_order(
    order_id: uuid.UUID | None = None,
    status: OrderStatus = OrderStatus.NEW,
    payment_method: PaymentMethod = PaymentMethod.CONTRACT,
    total_amount: int = 20_000,
    contract_id: uuid.UUID | None = None,
    quantities_reserved: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=order_id or uuid.uuid4(),
        status=status,
        payment_method=payment_method,
        total_amount=total_amount,
        contract_id=contract_id,
        quantities_reserved=quantities_reserved,
        items=[],
        sale_type=None,
        courier_id=None,
        client_id=uuid.uuid4(),
    )


def _make_fake_uow(
    contract: SimpleNamespace | None = None,
    price_items: list[SimpleNamespace] | None = None,
    saved_order: SimpleNamespace | None = None,
) -> MagicMock:
    """Build a MagicMock UoW with all repos needed by
    BaseOrderService.create_order().
    """
    uow = MagicMock()

    # Contracts repo
    uow.contracts.get_active_for_client = AsyncMock(
        return_value=contract,
    )

    # Price items repo
    uow.price_items.get_for_products_locked = AsyncMock(
        return_value=price_items or [],
    )
    uow.price_items.increment_quantities_used = AsyncMock()
    uow.price_items.decrement_quantities_used = AsyncMock()

    # Orders repo
    order_obj = saved_order or SimpleNamespace(
        id=uuid.uuid4(),
        total_amount=20_000,
        payment_method=PaymentMethod.CONTRACT,
        contract_id=(contract.id if contract else None),
        quantities_reserved=contract is not None,
        status=OrderStatus.NEW,
        items=[],
        sale_type=None,
        courier_id=None,
        client_id=uuid.uuid4(),
    )
    uow.orders.add = AsyncMock(return_value=order_obj)
    uow.orders.get_with_details = AsyncMock(
        return_value=order_obj,
    )
    uow.orders.update_status = AsyncMock(return_value=order_obj)
    uow.orders.update = AsyncMock(return_value=order_obj)

    # Order items repo
    uow.order_items.add_many = AsyncMock()
    uow.order_items.get_by_order = AsyncMock(return_value=[])

    # Inventories repo (for tara exchange check)
    fake_inv = SimpleNamespace(id=uuid.uuid4(), balances=[])
    uow.inventories.get_inventory_with_balances = AsyncMock(
        return_value=fake_inv,
    )
    uow.inventories.get_vendor_inventory = AsyncMock(
        return_value=SimpleNamespace(id=uuid.uuid4()),
    )

    # Misc
    uow.commit = AsyncMock()
    uow.flush = AsyncMock()
    uow.rollback = AsyncMock()
    uow.session.refresh = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)

    # Status audit log
    uow.status_logs.log_transition = AsyncMock()

    return uow


def _make_catalog_service(
    products: list[SimpleNamespace],
) -> MagicMock:
    svc = MagicMock()
    svc.get_by_ids = AsyncMock(return_value=products)
    return svc


def _make_user_service(
    role: Role = Role.CLIENT_B2C,
) -> MagicMock:
    svc = MagicMock()
    client = SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        is_active=True,
    )
    svc.get_client = AsyncMock(return_value=client)
    return svc


# ─── Tests: role guard ────────────────────────────────────


class TestContractRoleGuard:
    @pytest.mark.asyncio
    async def test_contract_payment_b2c_raises_bad_request(
        self,
    ):
        """CLIENT_B2C cannot use CONTRACT payment method."""
        product = make_product()
        uow = _make_fake_uow()
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service()
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[Item(product_id=product.id, quantity=1)],
            payment_method=PaymentMethod.CONTRACT,
            client_inventory_id=uuid.uuid4(),
        )

        with pytest.raises(BadRequestError) as exc:
            await svc.create_order(
                client_id=uuid.uuid4(),
                dto=dto,
            )
        assert exc.value.error_code == "CONTRACT_PAYMENT_NOT_ALLOWED"


# ─── Tests: contract validation ───────────────────────────


class TestContractValidation:
    @pytest.mark.asyncio
    async def test_contract_required_when_no_active_contract(
        self,
    ):
        """No ACTIVE contract → ContractRequiredError."""
        product = make_product()
        uow = _make_fake_uow(contract=None)
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service(role=Role.CLIENT_B2B)
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[Item(product_id=product.id, quantity=1)],
            payment_method=PaymentMethod.CONTRACT,
            client_inventory_id=uuid.uuid4(),
        )

        with pytest.raises(ContractRequiredError) as exc:
            await svc.create_order(
                client_id=uuid.uuid4(),
                dto=dto,
            )
        assert exc.value.error_code == "CONTRACT_REQUIRED"

    @pytest.mark.asyncio
    async def test_suspended_contract_raises_not_active(self):
        """SUSPENDED contract → ContractNotActiveError."""
        product = make_product()
        suspended = make_contract(
            status=ContractStatus.SUSPENDED,
        )
        uow = _make_fake_uow(contract=suspended)
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service(role=Role.CLIENT_B2B)
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[Item(product_id=product.id, quantity=1)],
            payment_method=PaymentMethod.CONTRACT,
            client_inventory_id=uuid.uuid4(),
        )

        with pytest.raises(ContractNotActiveError) as exc:
            await svc.create_order(
                client_id=uuid.uuid4(),
                dto=dto,
            )
        assert exc.value.error_code == "CONTRACT_NOT_ACTIVE"

    @pytest.mark.asyncio
    async def test_expired_contract_raises_expired_error(self):
        from src.modules.contracts.exceptions import (
            ContractExpiredError,
        )

        product = make_product()
        expired_contract = make_contract(
            status=ContractStatus.ACTIVE,
            end_date=date(2020, 1, 1),
        )
        uow = _make_fake_uow(contract=expired_contract)
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service(role=Role.CLIENT_B2B)
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[Item(product_id=product.id, quantity=1)],
            payment_method=PaymentMethod.CONTRACT,
            client_inventory_id=uuid.uuid4(),
        )

        with pytest.raises(ContractExpiredError) as exc:
            await svc.create_order(
                client_id=uuid.uuid4(),
                dto=dto,
            )
        assert exc.value.error_code == "CONTRACT_EXPIRED"


# ─── Tests: per-product quantity quota ────────────────────


class TestQuantityLimit:
    @pytest.mark.asyncio
    async def test_quantity_limit_exceeded_raises(self):
        """quantity_used + order_qty > quantity →
        QuantityLimitExceededError."""
        product = make_product(price=20_000)
        active = make_contract(status=ContractStatus.ACTIVE)

        pi = make_price_item(
            contract_id=active.id,
            product_id=product.id,
            price=20_000,
            quantity=10,
            quantity_used=8,  # only 2 left
        )
        uow = _make_fake_uow(
            contract=active,
            price_items=[pi],
        )
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service(role=Role.CLIENT_B2B)
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[
                Item(product_id=product.id, quantity=5),
            ],  # 5 > 2 available
            payment_method=PaymentMethod.CONTRACT,
            client_inventory_id=uuid.uuid4(),
        )

        with pytest.raises(QuantityLimitExceededError) as exc:
            await svc.create_order(
                client_id=uuid.uuid4(),
                dto=dto,
            )
        assert exc.value.error_code == "QUANTITY_LIMIT_EXCEEDED"
        # Quantities NOT incremented on failure
        uow.price_items.increment_quantities_used.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unlimited_quantity_zero_passes(self):
        """quantity=0 means unlimited — large order passes."""
        product = make_product(price=20_000)
        active = make_contract(status=ContractStatus.ACTIVE)

        pi = make_price_item(
            contract_id=active.id,
            product_id=product.id,
            price=20_000,
            quantity=0,  # unlimited
            quantity_used=0,
        )
        uow = _make_fake_uow(
            contract=active,
            price_items=[pi],
        )
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service(role=Role.CLIENT_B2B)
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[
                Item(product_id=product.id, quantity=9999),
            ],
            payment_method=PaymentMethod.CONTRACT,
            client_inventory_id=uuid.uuid4(),
        )

        await svc.create_order(
            client_id=uuid.uuid4(),
            dto=dto,
        )
        uow.price_items.increment_quantities_used.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_quantity_exactly_at_limit_passes(self):
        """quantity_used + order_qty == quantity → allowed."""
        product = make_product(price=20_000)
        active = make_contract(status=ContractStatus.ACTIVE)

        pi = make_price_item(
            contract_id=active.id,
            product_id=product.id,
            price=20_000,
            quantity=10,
            quantity_used=7,  # 3 remaining = exact match
        )
        uow = _make_fake_uow(
            contract=active,
            price_items=[pi],
        )
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service(role=Role.CLIENT_B2B)
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[
                Item(product_id=product.id, quantity=3),
            ],
            payment_method=PaymentMethod.CONTRACT,
            client_inventory_id=uuid.uuid4(),
        )

        await svc.create_order(
            client_id=uuid.uuid4(),
            dto=dto,
        )
        uow.price_items.increment_quantities_used.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_product_not_in_contract_raises(self):
        """Product missing from contract price list →
        ProductNotInContractError."""
        product = make_product(price=20_000)
        active = make_contract(status=ContractStatus.ACTIVE)

        # Empty price items — product not in contract
        uow = _make_fake_uow(
            contract=active,
            price_items=[],
        )
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service(role=Role.CLIENT_B2B)
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[
                Item(product_id=product.id, quantity=1),
            ],
            payment_method=PaymentMethod.CONTRACT,
            client_inventory_id=uuid.uuid4(),
        )

        with pytest.raises(ProductNotInContractError) as exc:
            await svc.create_order(
                client_id=uuid.uuid4(),
                dto=dto,
            )
        assert exc.value.error_code == "PRODUCT_NOT_IN_CONTRACT"


# ─── Tests: contract price override ──────────────────────


class TestContractPriceOverride:
    @pytest.mark.asyncio
    async def test_contract_price_overrides_catalog_price(
        self,
    ):
        """Contract price item replaces catalog price in the
        OrderItem snapshot and total_amount."""
        product_id = uuid.uuid4()
        product = make_product(
            product_id=product_id,
            price=20_000,  # catalog price
        )
        active = make_contract(status=ContractStatus.ACTIVE)

        pi = make_price_item(
            contract_id=active.id,
            product_id=product_id,
            price=15_000,  # contract overrides to 15_000
        )
        uow = _make_fake_uow(
            contract=active,
            price_items=[pi],
        )
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service(role=Role.CLIENT_B2B)
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[Item(product_id=product_id, quantity=2)],
            payment_method=PaymentMethod.CONTRACT,
            client_inventory_id=uuid.uuid4(),
        )

        await svc.create_order(
            client_id=uuid.uuid4(),
            dto=dto,
        )

        # total = 15_000 * 2 = 30_000
        order_add_call = uow.orders.add.call_args[0][0]
        assert order_add_call["total_amount"] == 30_000

        # OrderItem snapshot uses contract price
        items_call = uow.order_items.add_many.call_args[0][0]
        assert items_call[0]["unit_price"] == 15_000

    @pytest.mark.asyncio
    async def test_contract_id_and_quantities_reserved_saved(
        self,
    ):
        """contract_id and quantities_reserved=True are stored
        on the order row."""
        product_id = uuid.uuid4()
        product = make_product(product_id=product_id)
        contract_id = uuid.uuid4()
        active = make_contract(
            contract_id=contract_id,
            status=ContractStatus.ACTIVE,
        )

        pi = make_price_item(
            contract_id=contract_id,
            product_id=product_id,
        )
        uow = _make_fake_uow(
            contract=active,
            price_items=[pi],
        )
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service(role=Role.CLIENT_B2B)
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[Item(product_id=product_id, quantity=1)],
            payment_method=PaymentMethod.CONTRACT,
            client_inventory_id=uuid.uuid4(),
        )

        await svc.create_order(
            client_id=uuid.uuid4(),
            dto=dto,
        )

        order_add_call = uow.orders.add.call_args[0][0]
        assert order_add_call["contract_id"] == contract_id
        assert order_add_call["quantities_reserved"] is True


# ─── Tests: non-contract orders ──────────────────────────


class TestNonContractOrders:
    @pytest.mark.asyncio
    async def test_cash_order_skips_contract_validation(self):
        """CASH payment skips all contract logic."""
        product = make_product()
        uow = _make_fake_uow(contract=None)
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service()
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[Item(product_id=product.id, quantity=1)],
            payment_method=PaymentMethod.CASH,
            client_inventory_id=uuid.uuid4(),
        )

        await svc.create_order(
            client_id=uuid.uuid4(),
            dto=dto,
        )

        uow.contracts.get_active_for_client.assert_not_awaited()
        uow.price_items.get_for_products_locked.assert_not_awaited()
        uow.price_items.increment_quantities_used.assert_not_awaited()

        order_add_call = uow.orders.add.call_args[0][0]
        assert order_add_call.get("contract_id") is None
        assert order_add_call["quantities_reserved"] is False


# ─── Tests: quantity release on cancel ───────────────────


class TestQuantityRelease:
    @pytest.mark.asyncio
    async def test_cancel_order_releases_quantities(self):
        """Cancelling a CONTRACT order in NEW status releases
        reserved quantities via order items."""
        from src.modules.orders.enums import SaleType

        contract_id = uuid.uuid4()
        order_id = uuid.uuid4()
        product_id = uuid.uuid4()

        order_item = SimpleNamespace(
            id=uuid.uuid4(),
            order_id=order_id,
            product_id=product_id,
            quantity=3,
            unit_price=20_000,
        )

        order = SimpleNamespace(
            id=order_id,
            status=OrderStatus.NEW,
            payment_method=PaymentMethod.CONTRACT,
            contract_id=contract_id,
            total_amount=60_000,
            quantities_reserved=True,
            items=[],
            sale_type=SaleType.DELIVERY,
            courier_id=None,
            client_id=uuid.uuid4(),
        )

        uow = _make_fake_uow()
        uow.orders.get_with_details = AsyncMock(
            return_value=order,
        )
        uow.orders.update_status = AsyncMock(
            return_value=order,
        )
        uow.orders.update = AsyncMock()
        uow.order_items.get_by_order = AsyncMock(
            return_value=[order_item],
        )

        catalog_svc = _make_catalog_service([])
        user_svc = _make_user_service()
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )

        await svc.update_status(
            order_id=order_id,
            new_status=OrderStatus.CANCELLED,
        )

        # Order items fetched to build decrements
        uow.order_items.get_by_order.assert_awaited_once_with(
            order_id,
        )
        # Quantities decremented per product
        uow.price_items.decrement_quantities_used.assert_awaited_once_with(
            contract_id,
            [(product_id, 3)],
        )
        # quantities_reserved flag cleared
        uow.orders.update.assert_any_await(
            order_id,
            {"quantities_reserved": False},
        )

    @pytest.mark.asyncio
    async def test_cancel_cash_order_skips_quantity_release(
        self,
    ):
        """CASH order cancel does not touch quantity release."""
        from src.modules.orders.enums import SaleType

        order_id = uuid.uuid4()
        order = SimpleNamespace(
            id=order_id,
            status=OrderStatus.NEW,
            payment_method=PaymentMethod.CASH,
            contract_id=None,
            total_amount=20_000,
            quantities_reserved=False,
            items=[],
            sale_type=SaleType.DELIVERY,
            courier_id=None,
            client_id=uuid.uuid4(),
        )

        uow = _make_fake_uow()
        uow.orders.get_with_details = AsyncMock(
            return_value=order,
        )
        uow.orders.update_status = AsyncMock(
            return_value=order,
        )

        catalog_svc = _make_catalog_service([])
        user_svc = _make_user_service()
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )

        await svc.update_status(
            order_id=order_id,
            new_status=OrderStatus.CANCELLED,
        )
        uow.price_items.decrement_quantities_used.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_cart_raises(self):
        from src.core.exceptions import BadRequestError

        uow = _make_fake_uow()
        catalog_svc = _make_catalog_service([])
        user_svc = _make_user_service()
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )

        dto = OrderCreate(
            items=[
                Item(product_id=uuid.uuid4(), quantity=1),
            ],
            payment_method=PaymentMethod.CASH,
            client_inventory_id=uuid.uuid4(),
        )
        dto.items = []

        with pytest.raises(BadRequestError):
            await svc.create_order(
                client_id=uuid.uuid4(),
                dto=dto,
            )


# ─── Tests: double-cancel protection ─────────────────────


class TestDoubleCancelProtection:
    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_skips_release(
        self,
    ):
        """CANCELLED → CANCELLED (no-op) must NOT release
        quantities."""
        from src.modules.orders.enums import SaleType

        contract_id = uuid.uuid4()
        order_id = uuid.uuid4()

        order = SimpleNamespace(
            id=order_id,
            status=OrderStatus.CANCELLED,
            payment_method=PaymentMethod.CONTRACT,
            contract_id=contract_id,
            total_amount=50_000,
            quantities_reserved=False,  # already released
            items=[],
            sale_type=SaleType.DELIVERY,
            courier_id=None,
            client_id=uuid.uuid4(),
        )

        uow = _make_fake_uow()
        uow.orders.get_with_details = AsyncMock(
            return_value=order,
        )
        uow.orders.update_status = AsyncMock(
            return_value=order,
        )

        catalog_svc = _make_catalog_service([])
        user_svc = _make_user_service()
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )

        # CANCELLED → CANCELLED is a no-op (returns early)
        await svc.update_status(
            order_id=order_id,
            new_status=OrderStatus.CANCELLED,
        )

        uow.price_items.decrement_quantities_used.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cancel_with_quantities_not_reserved_skips(
        self,
    ):
        """If quantities_reserved=False (already released),
        cancel skips release."""
        from src.modules.orders.enums import SaleType

        contract_id = uuid.uuid4()
        order_id = uuid.uuid4()

        order = SimpleNamespace(
            id=order_id,
            status=OrderStatus.NEW,
            payment_method=PaymentMethod.CONTRACT,
            contract_id=contract_id,
            total_amount=50_000,
            quantities_reserved=False,
            items=[],
            sale_type=SaleType.DELIVERY,
            courier_id=None,
            client_id=uuid.uuid4(),
        )

        uow = _make_fake_uow()
        uow.orders.get_with_details = AsyncMock(
            return_value=order,
        )
        uow.orders.update_status = AsyncMock(
            return_value=order,
        )

        catalog_svc = _make_catalog_service([])
        user_svc = _make_user_service()
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )

        await svc.update_status(
            order_id=order_id,
            new_status=OrderStatus.CANCELLED,
        )

        # quantities_reserved=False → no release
        uow.price_items.decrement_quantities_used.assert_not_awaited()


# ─── Tests: quantities_reserved in create_order ──────────


class TestQuantitiesReserved:
    @pytest.mark.asyncio
    async def test_create_order_sets_quantities_reserved(self):
        """CONTRACT order sets quantities_reserved=True."""
        product = make_product(price=25_000)
        active = make_contract(status=ContractStatus.ACTIVE)
        pi = make_price_item(
            contract_id=active.id,
            product_id=product.id,
            price=25_000,
        )
        uow = _make_fake_uow(
            contract=active,
            price_items=[pi],
        )
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service(role=Role.CLIENT_B2B)
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[
                Item(product_id=product.id, quantity=2),
            ],
            payment_method=PaymentMethod.CONTRACT,
            client_inventory_id=uuid.uuid4(),
        )

        await svc.create_order(
            client_id=uuid.uuid4(),
            dto=dto,
        )

        order_add_call = uow.orders.add.call_args[0][0]
        assert order_add_call["quantities_reserved"] is True

    @pytest.mark.asyncio
    async def test_cash_order_has_false_quantities_reserved(
        self,
    ):
        """CASH order has quantities_reserved=False."""
        product = make_product()
        uow = _make_fake_uow(contract=None)
        catalog_svc = _make_catalog_service([product])

        user_svc = _make_user_service()
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[
                Item(product_id=product.id, quantity=1),
            ],
            payment_method=PaymentMethod.CASH,
            client_inventory_id=uuid.uuid4(),
        )

        await svc.create_order(
            client_id=uuid.uuid4(),
            dto=dto,
        )

        order_add_call = uow.orders.add.call_args[0][0]
        assert order_add_call["quantities_reserved"] is False


# ─── Tests: multi-product partial failure atomicity ──────


class TestMultiProductPartialFailure:
    @pytest.mark.asyncio
    async def test_multi_product_partial_failure_no_increment(
        self,
    ):
        """Product A has quota. Product B exceeds.
        Entire order fails. Product A quota unchanged."""
        product_a = make_product(price=20_000)
        product_b = make_product(price=20_000)
        active = make_contract(status=ContractStatus.ACTIVE)

        pi_a = make_price_item(
            contract_id=active.id,
            product_id=product_a.id,
            price=20_000,
            quantity=100,
            quantity_used=0,
        )
        pi_b = make_price_item(
            contract_id=active.id,
            product_id=product_b.id,
            price=20_000,
            quantity=5,
            quantity_used=5,  # fully used → 0 available
        )
        uow = _make_fake_uow(
            contract=active,
            price_items=[pi_a, pi_b],
        )
        catalog_svc = _make_catalog_service(
            [product_a, product_b],
        )

        user_svc = _make_user_service(role=Role.CLIENT_B2B)
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )
        dto = OrderCreate(
            items=[
                Item(product_id=product_a.id, quantity=3),
                Item(product_id=product_b.id, quantity=1),
            ],
            payment_method=PaymentMethod.CONTRACT,
            client_inventory_id=uuid.uuid4(),
        )

        with pytest.raises(QuantityLimitExceededError):
            await svc.create_order(
                client_id=uuid.uuid4(),
                dto=dto,
            )

        # No increments should have been called —
        # check fails before any reservation
        uow.price_items.increment_quantities_used.assert_not_awaited()


# ─── Tests: cancel delivered order ───────────────────────


class TestCancelDeliveredOrder:
    @pytest.mark.asyncio
    async def test_cancel_delivered_order_is_rejected(
        self,
    ):
        """DELIVERED → CANCELLED is rejected by status transition
        guard — quota is never touched."""
        from src.modules.orders.enums import SaleType
        from src.modules.orders.exceptions import (
            InvalidOrderStatusError,
        )

        contract_id = uuid.uuid4()
        order_id = uuid.uuid4()

        order = SimpleNamespace(
            id=order_id,
            status=OrderStatus.DELIVERED,
            payment_method=PaymentMethod.CONTRACT,
            contract_id=contract_id,
            total_amount=60_000,
            quantities_reserved=True,
            items=[],
            sale_type=SaleType.DELIVERY,
            courier_id=None,
            client_id=uuid.uuid4(),
        )

        uow = _make_fake_uow()
        uow.orders.get_with_details = AsyncMock(
            return_value=order,
        )
        uow.orders.update_status = AsyncMock(
            return_value=order,
        )
        uow.orders.update = AsyncMock()

        catalog_svc = _make_catalog_service([])
        user_svc = _make_user_service()
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )

        with pytest.raises(InvalidOrderStatusError):
            await svc.update_status(
                order_id=order_id,
                new_status=OrderStatus.CANCELLED,
            )

        # Transition rejected → no quota release attempted
        uow.price_items.decrement_quantities_used.assert_not_awaited()


# ─── Tests: add_product_to_order sets reserved flag ──────


class TestAddProductSetsReservedFlag:
    @pytest.mark.asyncio
    async def test_add_product_sets_quantities_reserved(self):
        """add_product_to_order on CONTRACT order sets
        quantities_reserved=True on the order."""
        product_id = uuid.uuid4()
        product = make_product(product_id=product_id, price=20_000)
        contract_id = uuid.uuid4()
        contract = make_contract(
            contract_id=contract_id,
            status=ContractStatus.ACTIVE,
        )
        pi = make_price_item(
            contract_id=contract_id,
            product_id=product_id,
            price=15_000,
            quantity=0,
            quantity_used=0,
        )

        order = make_order(
            status=OrderStatus.NEW,
            payment_method=PaymentMethod.CONTRACT,
            contract_id=contract_id,
            quantities_reserved=False,
            total_amount=0,
        )

        uow = _make_fake_uow()
        uow.orders.get_with_details = AsyncMock(
            return_value=order,
        )
        uow.contracts.get = AsyncMock(return_value=contract)
        uow.price_items.get_for_products_locked = AsyncMock(
            return_value=[pi],
        )
        uow.order_items.get_by_order_and_product = AsyncMock(
            return_value=None,
        )
        uow.order_items.add = AsyncMock()
        uow.orders.update = AsyncMock(return_value=order)

        catalog_svc = _make_catalog_service([product])
        user_svc = _make_user_service(role=Role.CLIENT_B2B)
        svc = BaseOrderService(
            uow=uow,
            catalog_service=catalog_svc,
            user_service=user_svc,
        )

        await svc.add_product_to_order(
            order_id=order.id,
            product_id=product_id,
            quantity=2,
        )

        # Verify quantities_reserved=True is in update call
        update_call = uow.orders.update.call_args
        assert update_call[0][1]["quantities_reserved"] is True

        # Verify increment was called
        uow.price_items.increment_quantities_used.assert_awaited_once()
