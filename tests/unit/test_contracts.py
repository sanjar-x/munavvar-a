"""Unit tests for ContractService business logic.

Uses AsyncMock/MagicMock — no database required.
"""
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.contracts.enums import ContractStatus
from src.modules.contracts.exceptions import (
    ContractAlreadyActiveError,
    ContractNotFoundError,
    ContractPriceItemNotFoundError,
    ContractStatusTransitionError,
)
from src.modules.contracts.schemas import (
    ContractCreate,
    ContractUpdate,
)
from src.modules.contracts.services import ContractService

# ─── Helpers ──────────────────────────────────────────────


def make_contract(
    status: ContractStatus = ContractStatus.DRAFT,
    client_id: uuid.UUID | None = None,
    credit_limit: int = 500_000,
    credit_used: int = 0,
    contract_id: uuid.UUID | None = None,
    end_date: date | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=contract_id or uuid.uuid4(),
        client_id=client_id or uuid.uuid4(),
        status=status,
        credit_limit=credit_limit,
        credit_used=credit_used,
        number="HOD-2025-001",
        start_date=date.today(),
        end_date=end_date,
    )


def make_price_item(
    contract_id: uuid.UUID,
    product_id: uuid.UUID,
    price: int = 15_000,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        contract_id=contract_id,
        product_id=product_id,
        price=price,
    )


class FakeContractRepo:
    """Fake synchronous-style repo wrapped by AsyncMock."""

    def __init__(self):
        self.get = AsyncMock(return_value=None)
        self.add = AsyncMock()
        self.update = AsyncMock()
        self.delete = AsyncMock()
        self.get_active_for_client = AsyncMock(return_value=None)
        self.get_with_price_items = AsyncMock(return_value=None)
        self.get_multi_with_client = AsyncMock(
            return_value=(0, [])
        )
        self.increment_credit_used = AsyncMock()
        self.decrement_credit_used = AsyncMock()
        self.get_price_map_for_products = AsyncMock(
            return_value={}
        )


class FakePriceItemRepo:
    def __init__(self):
        self.get = AsyncMock(return_value=None)
        self.add = AsyncMock()
        self.update = AsyncMock()
        self.delete = AsyncMock()
        self.get_by_contract_and_product = AsyncMock(
            return_value=None
        )


class FakeInvoiceRepo:
    def __init__(self):
        self.add = AsyncMock()
        self.get_multi = AsyncMock(return_value=[])


class FakeOrderRepo:
    def __init__(self):
        self.search_orders = AsyncMock(return_value=[])
        self.get_delivered_by_contract = AsyncMock(
            return_value=[]
        )


def make_uow(
    contracts: FakeContractRepo | None = None,
    price_items: FakePriceItemRepo | None = None,
    invoices: FakeInvoiceRepo | None = None,
    orders: FakeOrderRepo | None = None,
) -> MagicMock:
    """Build a fake IContractUnitOfWork."""
    uow = MagicMock()
    uow.contracts = contracts or FakeContractRepo()
    uow.price_items = price_items or FakePriceItemRepo()
    uow.invoices = invoices or FakeInvoiceRepo()
    uow.orders = orders or FakeOrderRepo()
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.flush = AsyncMock()
    # Make it an async context manager
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    return uow


# ─── Tests: lifecycle ─────────────────────────────────────


class TestContractLifecycle:
    @pytest.mark.asyncio
    async def test_create_contract_inserts_draft(self):
        contracts_repo = FakeContractRepo()
        # No existing active contract
        contracts_repo.get_active_for_client.return_value = None
        expected = make_contract(status=ContractStatus.DRAFT)
        contracts_repo.add.return_value = expected

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        dto = ContractCreate(
            number="HOD-2025-001",
            start_date=date.today(),
            credit_limit=0,
            payment_due_days=30,
            legal_name="ООО Рога и Копыта",
            inn="123456789012",
        )
        result = await service.create_contract(
            client_id=expected.client_id, dto=dto
        )

        contracts_repo.add.assert_awaited_once()
        call_data = contracts_repo.add.call_args[0][0]
        assert call_data["status"] == ContractStatus.DRAFT
        assert result is expected

    @pytest.mark.asyncio
    async def test_create_contract_blocks_if_active_exists(
        self,
    ):
        client_id = uuid.uuid4()
        existing = make_contract(
            status=ContractStatus.ACTIVE,
            client_id=client_id,
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get_active_for_client.return_value = (
            existing
        )

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        dto = ContractCreate(
            number="HOD-2025-002",
            start_date=date.today(),
            credit_limit=0,
            payment_due_days=30,
            legal_name="ООО Рога и Копыта",
            inn="123456789012",
        )
        with pytest.raises(ContractAlreadyActiveError):
            await service.create_contract(
                client_id=client_id, dto=dto
            )

    @pytest.mark.asyncio
    async def test_activate_draft_transitions_to_active(self):
        contract_id = uuid.uuid4()
        draft = make_contract(
            contract_id=contract_id,
            status=ContractStatus.DRAFT,
        )
        activated = make_contract(
            contract_id=contract_id,
            status=ContractStatus.ACTIVE,
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = draft
        contracts_repo.get_active_for_client.return_value = None
        contracts_repo.update.return_value = activated

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        result = await service.activate_contract(
            contract_id=contract_id,
            signed_by_id=uuid.uuid4(),
        )

        contracts_repo.update.assert_awaited_once()
        update_data = contracts_repo.update.call_args[0][1]
        assert update_data["status"] == ContractStatus.ACTIVE
        assert "signed_at" in update_data
        assert result is activated

    @pytest.mark.asyncio
    async def test_activate_raises_if_not_draft(self):
        contract_id = uuid.uuid4()
        active_contract = make_contract(
            contract_id=contract_id,
            status=ContractStatus.ACTIVE,
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = active_contract

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        with pytest.raises(ContractStatusTransitionError):
            await service.activate_contract(
                contract_id=contract_id,
                signed_by_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_activate_raises_if_client_already_has_active(
        self,
    ):
        client_id = uuid.uuid4()
        contract_id = uuid.uuid4()
        existing_active_id = uuid.uuid4()

        draft = make_contract(
            contract_id=contract_id,
            client_id=client_id,
            status=ContractStatus.DRAFT,
        )
        other_active = make_contract(
            contract_id=existing_active_id,
            client_id=client_id,
            status=ContractStatus.ACTIVE,
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = draft
        contracts_repo.get_active_for_client.return_value = (
            other_active
        )

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        with pytest.raises(ContractAlreadyActiveError) as exc:
            await service.activate_contract(
                contract_id=contract_id,
                signed_by_id=uuid.uuid4(),
            )
        assert exc.value.error_code == "CONTRACT_ALREADY_ACTIVE"

    @pytest.mark.asyncio
    async def test_suspend_active_sets_reason(self):
        contract_id = uuid.uuid4()
        active = make_contract(
            contract_id=contract_id,
            status=ContractStatus.ACTIVE,
        )
        suspended = make_contract(
            contract_id=contract_id,
            status=ContractStatus.SUSPENDED,
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = active
        contracts_repo.update.return_value = suspended

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        reason = "Нарушение условий оплаты"
        result = await service.suspend_contract(
            contract_id=contract_id, reason=reason
        )

        update_data = contracts_repo.update.call_args[0][1]
        assert update_data["status"] == ContractStatus.SUSPENDED
        assert update_data["suspension_reason"] == reason
        assert result is suspended

    @pytest.mark.asyncio
    async def test_suspend_raises_if_not_active(self):
        contract_id = uuid.uuid4()
        draft = make_contract(
            contract_id=contract_id,
            status=ContractStatus.DRAFT,
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = draft

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        with pytest.raises(ContractStatusTransitionError):
            await service.suspend_contract(
                contract_id=contract_id,
                reason="test",
            )

    @pytest.mark.asyncio
    async def test_reinstate_suspended_sets_active(self):
        contract_id = uuid.uuid4()
        suspended = make_contract(
            contract_id=contract_id,
            status=ContractStatus.SUSPENDED,
        )
        reinstated = make_contract(
            contract_id=contract_id,
            status=ContractStatus.ACTIVE,
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = suspended
        contracts_repo.get_active_for_client.return_value = None
        contracts_repo.update.return_value = reinstated

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        result = await service.reinstate_contract(
            contract_id=contract_id
        )

        update_data = contracts_repo.update.call_args[0][1]
        assert update_data["status"] == ContractStatus.ACTIVE
        assert update_data["suspended_at"] is None
        assert result is reinstated

    @pytest.mark.asyncio
    async def test_reinstate_raises_if_not_suspended(self):
        contract_id = uuid.uuid4()
        terminated = make_contract(
            contract_id=contract_id,
            status=ContractStatus.TERMINATED,
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = terminated

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        with pytest.raises(ContractStatusTransitionError):
            await service.reinstate_contract(
                contract_id=contract_id
            )

    @pytest.mark.asyncio
    async def test_terminate_active_sets_terminated(self):
        contract_id = uuid.uuid4()
        active = make_contract(
            contract_id=contract_id,
            status=ContractStatus.ACTIVE,
        )
        terminated = make_contract(
            contract_id=contract_id,
            status=ContractStatus.TERMINATED,
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = active
        contracts_repo.update.return_value = terminated

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        result = await service.terminate_contract(
            contract_id=contract_id, reason="Расторжение по ст.23"
        )

        update_data = contracts_repo.update.call_args[0][1]
        assert update_data["status"] == ContractStatus.TERMINATED
        assert update_data["termination_reason"] == (
            "Расторжение по ст.23"
        )
        assert result is terminated

    @pytest.mark.asyncio
    async def test_terminate_raises_if_already_terminated(self):
        contract_id = uuid.uuid4()
        already = make_contract(
            contract_id=contract_id,
            status=ContractStatus.TERMINATED,
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = already

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        with pytest.raises(ContractStatusTransitionError):
            await service.terminate_contract(
                contract_id=contract_id, reason="test"
            )

    @pytest.mark.asyncio
    async def test_get_active_contract_returns_none_when_absent(
        self,
    ):
        contracts_repo = FakeContractRepo()
        contracts_repo.get_active_for_client.return_value = None

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        result = await service.get_active_contract(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_contract_not_found_raises(self):
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = None

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        with pytest.raises(ContractNotFoundError):
            await service.terminate_contract(
                contract_id=uuid.uuid4(), reason="test"
            )


# ─── Tests: credit guard ──────────────────────────────────


class TestContractCreditGuard:
    """
    These tests invoke update_contract() to verify credit_limit
    validation (the service rejects new_limit < credit_used).
    """

    @pytest.mark.asyncio
    async def test_update_limit_below_used_raises(self):
        from src.core.exceptions import BadRequestError

        contract_id = uuid.uuid4()
        contract = make_contract(
            contract_id=contract_id,
            credit_limit=500_000,
            credit_used=300_000,
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = contract

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        dto = ContractUpdate(credit_limit=100_000)
        with pytest.raises(BadRequestError) as exc:
            await service.update_contract(
                contract_id=contract_id, dto=dto
            )
        assert exc.value.error_code == "CREDIT_LIMIT_BELOW_USED"

    @pytest.mark.asyncio
    async def test_update_limit_equal_to_used_succeeds(self):
        contract_id = uuid.uuid4()
        contract = make_contract(
            contract_id=contract_id,
            credit_limit=300_000,
            credit_used=300_000,
        )
        updated = make_contract(
            contract_id=contract_id,
            credit_limit=300_000,
            credit_used=300_000,
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = contract
        contracts_repo.update.return_value = updated

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        dto = ContractUpdate(credit_limit=300_000)
        result = await service.update_contract(
            contract_id=contract_id, dto=dto
        )
        assert result is updated

    @pytest.mark.asyncio
    async def test_unlimited_contract_zero_limit_ignores_check(
        self,
    ):
        """credit_limit=0 means unlimited — any new_limit=0 is OK."""
        contract_id = uuid.uuid4()
        contract = make_contract(
            contract_id=contract_id,
            credit_limit=0,
            credit_used=9_999_999,
        )
        updated = make_contract(
            contract_id=contract_id, credit_limit=0
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = contract
        contracts_repo.update.return_value = updated

        uow = make_uow(contracts=contracts_repo)
        service = ContractService(uow=uow)

        # Setting limit to 0 (unlimited) should never raise
        dto = ContractUpdate(credit_limit=0)
        result = await service.update_contract(
            contract_id=contract_id, dto=dto
        )
        assert result is updated


# ─── Tests: price items ───────────────────────────────────


class TestContractPriceItems:
    @pytest.mark.asyncio
    async def test_set_price_item_creates_new_if_absent(self):
        contract_id = uuid.uuid4()
        product_id = uuid.uuid4()
        expected_item = make_price_item(
            contract_id, product_id, price=15_000
        )

        price_items_repo = FakePriceItemRepo()
        price_items_repo.get_by_contract_and_product.return_value = (
            None
        )
        price_items_repo.add.return_value = expected_item

        uow = make_uow(price_items=price_items_repo)
        service = ContractService(uow=uow)

        result = await service.set_price_item(
            contract_id=contract_id,
            product_id=product_id,
            price=15_000,
        )

        price_items_repo.add.assert_awaited_once()
        call_data = price_items_repo.add.call_args[0][0]
        assert call_data["price"] == 15_000
        assert result is expected_item

    @pytest.mark.asyncio
    async def test_set_price_item_updates_existing(self):
        contract_id = uuid.uuid4()
        product_id = uuid.uuid4()
        existing = make_price_item(
            contract_id, product_id, price=10_000
        )
        updated = make_price_item(
            contract_id, product_id, price=12_000
        )

        price_items_repo = FakePriceItemRepo()
        price_items_repo.get_by_contract_and_product.return_value = (
            existing
        )
        price_items_repo.update.return_value = updated

        uow = make_uow(price_items=price_items_repo)
        service = ContractService(uow=uow)

        result = await service.set_price_item(
            contract_id=contract_id,
            product_id=product_id,
            price=12_000,
        )

        price_items_repo.update.assert_awaited_once_with(
            existing.id, {"price": 12_000}
        )
        price_items_repo.add.assert_not_awaited()
        assert result is updated

    @pytest.mark.asyncio
    async def test_remove_price_item_raises_if_not_found(self):
        price_items_repo = FakePriceItemRepo()
        price_items_repo.get_by_contract_and_product.return_value = (
            None
        )

        uow = make_uow(price_items=price_items_repo)
        service = ContractService(uow=uow)

        with pytest.raises(ContractPriceItemNotFoundError):
            await service.remove_price_item(
                contract_id=uuid.uuid4(),
                product_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_remove_price_item_calls_delete(self):
        contract_id = uuid.uuid4()
        product_id = uuid.uuid4()
        item = make_price_item(contract_id, product_id)

        price_items_repo = FakePriceItemRepo()
        price_items_repo.get_by_contract_and_product.return_value = (
            item
        )

        uow = make_uow(price_items=price_items_repo)
        service = ContractService(uow=uow)

        await service.remove_price_item(
            contract_id=contract_id, product_id=product_id
        )

        price_items_repo.delete.assert_awaited_once_with(item.id)
