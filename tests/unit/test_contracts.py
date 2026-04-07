"""Unit tests for ContractService business logic.

Uses AsyncMock/MagicMock — no database required.
"""
import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.contracts.enums import ContractStatus, InvoiceStatus
from src.modules.contracts.exceptions import (
    ContractAlreadyActiveError,
    ContractNotFoundError,
    ContractPriceItemNotFoundError,
    ContractStatusTransitionError,
    DuplicateInvoicePeriodError,
    InvalidInvoiceTransitionError,
    InvoiceNotFoundError,
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
        self.get = AsyncMock(return_value=None)
        self.update = AsyncMock()
        self.get_multi = AsyncMock(return_value=[])
        self.get_by_contract = AsyncMock(return_value=[])
        self.get_for_period = AsyncMock(return_value=None)


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
    uow.accounts = MagicMock()
    uow.transactions = MagicMock()
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


# ─── Tests: Invoice lifecycle ─────────────────────────────


def make_invoice(
    contract_id: uuid.UUID,
    status: InvoiceStatus = InvoiceStatus.DRAFT,
    period_from: date | None = None,
    period_to: date | None = None,
    invoice_id: uuid.UUID | None = None,
    payment_due_days: int = 30,
) -> SimpleNamespace:
    pf = period_from or date(2025, 1, 1)
    pt = period_to or date(2025, 1, 31)
    return SimpleNamespace(
        id=invoice_id or uuid.uuid4(),
        contract_id=contract_id,
        status=status,
        period_from=pf,
        period_to=pt,
        amount=100_000,
        due_date=pt + timedelta(days=payment_due_days),
        issued_at=None,
        paid_at=None,
    )


def make_contract_with_payment_days(
    contract_id: uuid.UUID | None = None,
    payment_due_days: int = 30,
    status: ContractStatus = ContractStatus.ACTIVE,
) -> SimpleNamespace:
    c = make_contract(
        contract_id=contract_id or uuid.uuid4(),
        status=status,
    )
    c.payment_due_days = payment_due_days
    return c


class TestInvoiceLifecycle:
    @pytest.mark.asyncio
    async def test_generate_invoice_creates_draft(self):
        contract_id = uuid.uuid4()
        contract = make_contract_with_payment_days(
            contract_id=contract_id
        )
        invoice_repo = FakeInvoiceRepo()
        invoice_repo.get_for_period.return_value = None
        invoice_repo.get_by_contract.return_value = []
        expected_invoice = make_invoice(
            contract_id=contract_id,
            status=InvoiceStatus.DRAFT,
        )
        invoice_repo.add.return_value = expected_invoice
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = contract
        order_repo = FakeOrderRepo()
        order_repo.get_delivered_by_contract.return_value = []

        uow = make_uow(
            contracts=contracts_repo,
            invoices=invoice_repo,
            orders=order_repo,
        )
        service = ContractService(uow=uow)

        result = await service.generate_invoice(
            contract_id=contract_id,
            period_from=date(2025, 1, 1),
            period_to=date(2025, 1, 31),
        )

        invoice_repo.add.assert_awaited_once()
        call_data = invoice_repo.add.call_args[0][0]
        assert call_data["status"] == InvoiceStatus.DRAFT
        assert result is expected_invoice

    @pytest.mark.asyncio
    async def test_generate_invoice_calculates_due_date(self):
        contract_id = uuid.uuid4()
        period_to = date(2025, 1, 31)
        contract = make_contract_with_payment_days(
            contract_id=contract_id, payment_due_days=14
        )
        invoice_repo = FakeInvoiceRepo()
        invoice_repo.get_for_period.return_value = None
        invoice_repo.get_by_contract.return_value = []
        invoice_repo.add.return_value = make_invoice(
            contract_id=contract_id
        )
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = contract
        order_repo = FakeOrderRepo()
        order_repo.get_delivered_by_contract.return_value = []

        uow = make_uow(
            contracts=contracts_repo,
            invoices=invoice_repo,
            orders=order_repo,
        )
        service = ContractService(uow=uow)

        await service.generate_invoice(
            contract_id=contract_id,
            period_from=date(2025, 1, 1),
            period_to=period_to,
        )

        call_data = invoice_repo.add.call_args[0][0]
        expected_due = period_to + timedelta(days=14)
        assert call_data["due_date"] == expected_due

    @pytest.mark.asyncio
    async def test_generate_invoice_duplicate_period_rejected(self):
        contract_id = uuid.uuid4()
        contract = make_contract_with_payment_days(
            contract_id=contract_id
        )
        existing_invoice = make_invoice(contract_id=contract_id)
        invoice_repo = FakeInvoiceRepo()
        # Simulate existing non-CANCELLED invoice for period
        invoice_repo.get_for_period.return_value = existing_invoice
        contracts_repo = FakeContractRepo()
        contracts_repo.get.return_value = contract

        uow = make_uow(
            contracts=contracts_repo, invoices=invoice_repo
        )
        service = ContractService(uow=uow)

        with pytest.raises(DuplicateInvoicePeriodError):
            await service.generate_invoice(
                contract_id=contract_id,
                period_from=date(2025, 1, 1),
                period_to=date(2025, 1, 31),
            )

    @pytest.mark.asyncio
    async def test_issue_invoice_draft_to_issued(self):
        contract_id = uuid.uuid4()
        invoice_id = uuid.uuid4()
        draft = make_invoice(
            contract_id=contract_id,
            status=InvoiceStatus.DRAFT,
            invoice_id=invoice_id,
        )
        issued = make_invoice(
            contract_id=contract_id,
            status=InvoiceStatus.ISSUED,
            invoice_id=invoice_id,
        )
        invoice_repo = FakeInvoiceRepo()
        invoice_repo.get.return_value = draft
        invoice_repo.update.return_value = issued

        uow = make_uow(invoices=invoice_repo)
        service = ContractService(uow=uow)

        result = await service.issue_invoice(
            contract_id=contract_id,
            invoice_id=invoice_id,
        )

        invoice_repo.update.assert_awaited_once()
        update_data = invoice_repo.update.call_args[0][1]
        assert update_data["status"] == InvoiceStatus.ISSUED
        assert update_data["issued_at"] is not None
        assert result is issued

    @pytest.mark.asyncio
    async def test_issue_invoice_wrong_status_raises(self):
        contract_id = uuid.uuid4()
        invoice_id = uuid.uuid4()
        paid_invoice = make_invoice(
            contract_id=contract_id,
            status=InvoiceStatus.PAID,
            invoice_id=invoice_id,
        )
        invoice_repo = FakeInvoiceRepo()
        invoice_repo.get.return_value = paid_invoice

        uow = make_uow(invoices=invoice_repo)
        service = ContractService(uow=uow)

        with pytest.raises(InvalidInvoiceTransitionError):
            await service.issue_invoice(
                contract_id=contract_id,
                invoice_id=invoice_id,
            )

    @pytest.mark.asyncio
    async def test_mark_invoice_paid(self):
        contract_id = uuid.uuid4()
        invoice_id = uuid.uuid4()
        issued = make_invoice(
            contract_id=contract_id,
            status=InvoiceStatus.ISSUED,
            invoice_id=invoice_id,
        )
        paid = make_invoice(
            contract_id=contract_id,
            status=InvoiceStatus.PAID,
            invoice_id=invoice_id,
        )
        invoice_repo = FakeInvoiceRepo()
        invoice_repo.get.return_value = issued
        invoice_repo.update.return_value = paid

        uow = make_uow(invoices=invoice_repo)
        service = ContractService(uow=uow)

        result = await service.mark_invoice_paid(
            contract_id=contract_id,
            invoice_id=invoice_id,
        )

        update_data = invoice_repo.update.call_args[0][1]
        assert update_data["status"] == InvoiceStatus.PAID
        assert update_data["paid_at"] is not None
        assert result is paid

    @pytest.mark.asyncio
    async def test_cancel_invoice_draft(self):
        contract_id = uuid.uuid4()
        invoice_id = uuid.uuid4()
        draft = make_invoice(
            contract_id=contract_id,
            status=InvoiceStatus.DRAFT,
            invoice_id=invoice_id,
        )
        cancelled = make_invoice(
            contract_id=contract_id,
            status=InvoiceStatus.CANCELLED,
            invoice_id=invoice_id,
        )
        invoice_repo = FakeInvoiceRepo()
        invoice_repo.get.return_value = draft
        invoice_repo.update.return_value = cancelled

        uow = make_uow(invoices=invoice_repo)
        service = ContractService(uow=uow)

        result = await service.cancel_invoice(
            contract_id=contract_id,
            invoice_id=invoice_id,
        )

        update_data = invoice_repo.update.call_args[0][1]
        assert update_data["status"] == InvoiceStatus.CANCELLED
        assert result is cancelled

    @pytest.mark.asyncio
    async def test_cancel_paid_invoice_rejected(self):
        contract_id = uuid.uuid4()
        invoice_id = uuid.uuid4()
        paid = make_invoice(
            contract_id=contract_id,
            status=InvoiceStatus.PAID,
            invoice_id=invoice_id,
        )
        invoice_repo = FakeInvoiceRepo()
        invoice_repo.get.return_value = paid

        uow = make_uow(invoices=invoice_repo)
        service = ContractService(uow=uow)

        with pytest.raises(InvalidInvoiceTransitionError):
            await service.cancel_invoice(
                contract_id=contract_id,
                invoice_id=invoice_id,
            )

    @pytest.mark.asyncio
    async def test_get_invoice_idor_guard(self):
        """Invoice belonging to a different contract raises NotFound."""
        contract_id = uuid.uuid4()
        other_contract_id = uuid.uuid4()
        invoice_id = uuid.uuid4()
        # Invoice belongs to other_contract_id
        invoice = make_invoice(
            contract_id=other_contract_id,
            invoice_id=invoice_id,
        )
        invoice_repo = FakeInvoiceRepo()
        invoice_repo.get.return_value = invoice

        uow = make_uow(invoices=invoice_repo)
        service = ContractService(uow=uow)

        with pytest.raises(InvoiceNotFoundError):
            await service.get_invoice(
                contract_id=contract_id,
                invoice_id=invoice_id,
            )
