# src/modules/contracts/services.py
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import structlog

from src.modules.contracts.enums import ContractStatus, InvoiceStatus
from src.modules.contracts.exceptions import (
    ContractAlreadyActiveError,
    ContractNotFoundError,
    ContractPriceItemNotFoundError,
    ContractStatusTransitionError,
    DuplicateAmendmentNumberError,
    DuplicateInvoicePeriodError,
    InvalidInvoiceTransitionError,
    InvoiceNotFoundError,
)
from src.modules.contracts.models import (
    Contract,
    ContractAmendment,
    ContractPriceItem,
    ContractStatusLog,
    Invoice,
)
from src.modules.contracts.schemas import (
    AmendmentCreate,
    ContractCreate,
    ContractUpdate,
    ReconciliationOrderItem,
    ReconciliationPaymentItem,
    ReconciliationResponse,
)
from src.modules.contracts.uow import IContractUnitOfWork
from src.modules.orders.enums import OrderStatus

log = structlog.get_logger(__name__)


class ContractService:
    """Управление договорами с юридическими лицами.

    Бизнес-инварианты:
    - Один клиент → один ACTIVE договор (partial unique index)
    - credit_used: обновляется приложением (не триггером)
    - credit_limit == 0 → безлимитный договор
    - Только ACTIVE договоры разрешают создание заказов
    - Snapshot pricing: цена фиксируется в OrderItem.unit_price
    """

    def __init__(self, uow: IContractUnitOfWork):
        self.uow = uow

    # ─── LIFECYCLE ───────────────────────────────────────────────

    async def create_contract(
        self,
        client_id: uuid.UUID,
        dto: ContractCreate,
    ) -> Contract:
        """Создать договор в статусе DRAFT.
        DRAFT-дубликаты разрешены (обсуждение условий).
        """
        async with self.uow:
            existing = await self.uow.contracts.get_active_for_client(
                client_id
            )
            if existing:
                raise ContractAlreadyActiveError(
                    client_id=client_id,
                    existing_contract_id=existing.id,
                )
            contract = await self.uow.contracts.add(
                {
                    "client_id": client_id,
                    "number": dto.number,
                    "status": ContractStatus.DRAFT,
                    "start_date": dto.start_date,
                    "end_date": dto.end_date,
                    "credit_limit": dto.credit_limit,
                    "payment_due_days": dto.payment_due_days,
                    "legal_name": dto.legal_name,
                    "inn": dto.inn,
                    "legal_address": dto.legal_address,
                    "notes": dto.notes,
                }
            )
            await self.uow.commit()
            return contract

    async def activate_contract(
        self,
        contract_id: uuid.UUID,
        signed_by_id: uuid.UUID,
    ) -> Contract:
        """DRAFT → ACTIVE. Подписание договора."""
        async with self.uow:
            contract = await self.uow.contracts.get(
                contract_id, with_for_update=True
            )
            if not contract:
                raise ContractNotFoundError(contract_id)

            if contract.status != ContractStatus.DRAFT:
                raise ContractStatusTransitionError(
                    contract_id=contract_id,
                    current=contract.status,
                    target=ContractStatus.ACTIVE,
                )

            existing = await self.uow.contracts.get_active_for_client(
                contract.client_id, with_for_update=True
            )
            if existing and existing.id != contract_id:
                raise ContractAlreadyActiveError(
                    client_id=contract.client_id,
                    existing_contract_id=existing.id,
                )

            old_status = contract.status
            updated = await self.uow.contracts.update(
                contract_id,
                {
                    "status": ContractStatus.ACTIVE,
                    "signed_at": datetime.now(tz=UTC),
                    "signed_by_id": signed_by_id,
                },
            )
            await self.uow.status_logs.add(
                {
                    "contract_id": contract_id,
                    "from_status": old_status,
                    "to_status": ContractStatus.ACTIVE,
                    "changed_by_id": signed_by_id,
                    "reason": None,
                }
            )
            await self.uow.commit()
            return updated

    async def suspend_contract(
        self,
        contract_id: uuid.UUID,
        reason: str,
        changed_by_id: uuid.UUID | None = None,
    ) -> Contract:
        """ACTIVE → SUSPENDED.
        Отменяет все NEW/ASSIGNED заказы по договору и возвращает
        зарезервированный кредит. IN_TRANSIT/ARRIVED заказы
        завершаются штатно.
        """
        async with self.uow:
            contract = await self.uow.contracts.get(
                contract_id, with_for_update=True
            )
            if not contract:
                raise ContractNotFoundError(contract_id)
            if contract.status != ContractStatus.ACTIVE:
                raise ContractStatusTransitionError(
                    contract_id=contract_id,
                    current=contract.status,
                    target=ContractStatus.SUSPENDED,
                )
            old_status = contract.status
            updated = await self.uow.contracts.update(
                contract_id,
                {
                    "status": ContractStatus.SUSPENDED,
                    "suspended_at": datetime.now(tz=UTC),
                    "suspension_reason": reason,
                },
            )

            # Отмена незавершённых заказов и возврат кредита
            await self._cancel_inflight_orders(
                contract_id,
                reason="Приостановка договора",
            )

            await self.uow.status_logs.add(
                {
                    "contract_id": contract_id,
                    "from_status": old_status,
                    "to_status": ContractStatus.SUSPENDED,
                    "changed_by_id": changed_by_id,
                    "reason": reason,
                }
            )
            await self.uow.commit()
            return updated

    async def reinstate_contract(
        self,
        contract_id: uuid.UUID,
        changed_by_id: uuid.UUID | None = None,
    ) -> Contract:
        """SUSPENDED → ACTIVE."""
        async with self.uow:
            contract = await self.uow.contracts.get(
                contract_id, with_for_update=True
            )
            if not contract:
                raise ContractNotFoundError(contract_id)
            if contract.status != ContractStatus.SUSPENDED:
                raise ContractStatusTransitionError(
                    contract_id=contract_id,
                    current=contract.status,
                    target=ContractStatus.ACTIVE,
                )
            # Проверяем коллизию: мог появиться другой ACTIVE.
            # with_for_update=True предотвращает race condition.
            existing = await self.uow.contracts.get_active_for_client(
                contract.client_id, with_for_update=True
            )
            if existing and existing.id != contract_id:
                raise ContractAlreadyActiveError(
                    client_id=contract.client_id,
                    existing_contract_id=existing.id,
                )
            old_status = contract.status
            updated = await self.uow.contracts.update(
                contract_id,
                {
                    "status": ContractStatus.ACTIVE,
                    "suspended_at": None,
                    "suspension_reason": None,
                },
            )
            await self.uow.status_logs.add(
                {
                    "contract_id": contract_id,
                    "from_status": old_status,
                    "to_status": ContractStatus.ACTIVE,
                    "changed_by_id": changed_by_id,
                    "reason": None,
                }
            )
            await self.uow.commit()
            return updated

    async def terminate_contract(
        self,
        contract_id: uuid.UUID,
        reason: str,
        changed_by_id: uuid.UUID | None = None,
    ) -> Contract:
        """ACTIVE/SUSPENDED → TERMINATED.
        Отменяет все NEW/ASSIGNED заказы по договору.
        """
        async with self.uow:
            contract = await self.uow.contracts.get(
                contract_id, with_for_update=True
            )
            if not contract:
                raise ContractNotFoundError(contract_id)
            if contract.status not in (
                ContractStatus.ACTIVE,
                ContractStatus.SUSPENDED,
            ):
                raise ContractStatusTransitionError(
                    contract_id=contract_id,
                    current=contract.status,
                    target=ContractStatus.TERMINATED,
                )
            old_status = contract.status
            updated = await self.uow.contracts.update(
                contract_id,
                {
                    "status": ContractStatus.TERMINATED,
                    "terminated_at": datetime.now(tz=UTC),
                    "termination_reason": reason,
                },
            )

            # Отмена незавершённых заказов и возврат кредита
            await self._cancel_inflight_orders(
                contract_id,
                reason="Расторжение договора",
            )

            await self.uow.status_logs.add(
                {
                    "contract_id": contract_id,
                    "from_status": old_status,
                    "to_status": ContractStatus.TERMINATED,
                    "changed_by_id": changed_by_id,
                    "reason": reason,
                }
            )
            await self.uow.commit()
            return updated

    async def _cancel_inflight_orders(
        self,
        contract_id: uuid.UUID,
        reason: str = "Отмена по договору",
    ) -> None:
        """Отмена NEW/ASSIGNED заказов и возврат кредита.

        Вызывается при suspend/terminate/expire внутри
        открытого UoW. IN_TRANSIT/ARRIVED заказы не
        отменяются (товар в пути).

        Для каждого заказа пишет:
        - cancellation_reason на заказ
        - OrderStatusLog (аудит перехода)
        """
        cancelled = await self.uow.orders.bulk_cancel_by_contract(contract_id)
        total_released = 0
        for order_id, old_status, reserved in cancelled:
            if reserved and reserved > 0:
                total_released += reserved

            # Аудит: причина + лог перехода
            await self.uow.orders.update(
                order_id,
                {"cancellation_reason": reason},
            )
            await self.uow.order_status_logs.log_transition(
                order_id=order_id,
                old_status=old_status,
                new_status=OrderStatus.CANCELLED,
                changed_by_id=None,
                reason=reason,
            )

        if total_released > 0:
            await self.uow.contracts.decrement_credit_used(
                contract_id, total_released
            )
        if cancelled:
            log.info(
                "inflight_orders_cancelled",
                contract_id=str(contract_id),
                cancelled_count=len(cancelled),
                credit_released=total_released,
            )

        # Предупреждение о заказах в пути
        surviving = await self.uow.orders.count_inflight_by_contract(
            contract_id
        )
        if surviving > 0:
            log.warning(
                "surviving_inflight_orders",
                contract_id=str(contract_id),
                in_transit_count=surviving,
            )

    async def update_contract(
        self,
        contract_id: uuid.UUID,
        dto: ContractUpdate,
    ) -> Contract:
        """Обновить условия договора (кроме смены статуса)."""
        async with self.uow:
            contract = await self.uow.contracts.get(contract_id)
            if not contract:
                raise ContractNotFoundError(contract_id)
            data = dto.model_dump(exclude_unset=True)
            if not data:
                return contract
            # Защита от credit_limit < credit_used
            new_limit = data.get("credit_limit")
            if (
                new_limit is not None
                and new_limit > 0
                and new_limit < contract.credit_used
            ):
                from src.core.exceptions import BadRequestError

                raise BadRequestError(
                    message=(
                        "Новый кредитный лимит меньше текущего "
                        "зарезервированного объёма. "
                        "Дождитесь завершения заказов."
                    ),
                    error_code="CREDIT_LIMIT_BELOW_USED",
                    details={
                        "new_limit": new_limit,
                        "credit_used": contract.credit_used,
                    },
                )
            updated = await self.uow.contracts.update(contract_id, data)
            await self.uow.commit()
            return updated

    # ─── ЦЕНООБРАЗОВАНИЕ ─────────────────────────────────────────

    async def set_price_item(
        self,
        contract_id: uuid.UUID,
        product_id: uuid.UUID,
        price: int,
    ) -> ContractPriceItem:
        """Установить/обновить договорную цену на товар (upsert)."""
        async with self.uow:
            existing = await self.uow.price_items.get_by_contract_and_product(
                contract_id, product_id
            )
            if existing:
                item = await self.uow.price_items.update(
                    existing.id, {"price": price}
                )
            else:
                item = await self.uow.price_items.add(
                    {
                        "contract_id": contract_id,
                        "product_id": product_id,
                        "price": price,
                    }
                )
            await self.uow.commit()
            return item

    async def remove_price_item(
        self,
        contract_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> None:
        """Удалить позицию из прайс-листа → фолбэк на каталог."""
        async with self.uow:
            item = await self.uow.price_items.get_by_contract_and_product(
                contract_id, product_id
            )
            if not item:
                raise ContractPriceItemNotFoundError(contract_id, product_id)
            await self.uow.price_items.delete(item.id)
            await self.uow.commit()

    # ─── QUERY ───────────────────────────────────────────────────

    async def get_active_contract(
        self, client_id: uuid.UUID
    ) -> Contract | None:
        async with self.uow:
            return await self.uow.contracts.get_active_for_client(client_id)

    async def get_contract_with_prices(
        self, contract_id: uuid.UUID
    ) -> Contract:
        async with self.uow:
            contract = await self.uow.contracts.get_with_price_items(
                contract_id
            )
            if not contract:
                raise ContractNotFoundError(contract_id)
            return contract

    async def list_contracts(
        self,
        status: ContractStatus | None = None,
        client_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Contract]:
        async with self.uow:
            _total, items = await self.uow.contracts.get_multi_with_client(
                status=status,
                client_id=client_id,
                skip=skip,
                limit=limit,
            )
            return list(items)

    async def list_contract_orders(
        self,
        contract_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list:
        """Все заказы по договору (для backoffice)."""
        async with self.uow:
            contract = await self.uow.contracts.get(contract_id)
            if not contract:
                raise ContractNotFoundError(contract_id)
            orders = await self.uow.orders.search_orders(
                contract_id=contract_id,
                skip=skip,
                limit=limit,
            )
            return list(orders)

    async def generate_invoice(
        self,
        contract_id: uuid.UUID,
        period_from: date,
        period_to: date,
    ) -> Invoice:
        """Сформировать черновик счёта-фактуры за период.

        Бизнес-правила:
        - Создаётся в статусе DRAFT (не ISSUED).
        - due_date = period_to + payment_due_days.
        - Один не-CANCELLED инвойс за период — запрещён дубль.
        """
        async with self.uow:
            # Lock contract row to prevent concurrent invoice number races
            contract = await self.uow.contracts.get(
                contract_id, with_for_update=True
            )
            if not contract:
                raise ContractNotFoundError(contract_id)

            # Проверка дубля
            duplicate = await self.uow.invoices.get_for_period(
                contract_id=contract_id,
                period_from=period_from,
                period_to=period_to,
            )
            if duplicate:
                raise DuplicateInvoicePeriodError(
                    contract_id=contract_id,
                    period_from=period_from,
                    period_to=period_to,
                )

            delivered_orders = await self.uow.orders.get_delivered_by_contract(
                contract_id=contract_id,
                date_from=period_from,
                date_to=period_to,
            )
            total_amount = sum(o.total_amount for o in delivered_orders)

            # Порядковый номер инвойса по договору
            existing = await self.uow.invoices.get_by_contract(contract_id)
            sequence = len(existing) + 1
            number = (
                f"{contract.number}"
                f"/{period_from.year}"
                f"-{period_from.month:02d}"
                f"-{sequence:03d}"
            )

            due_date = period_to + timedelta(days=contract.payment_due_days)
            invoice = await self.uow.invoices.add(
                {
                    "contract_id": contract_id,
                    "number": number,
                    "status": InvoiceStatus.DRAFT,
                    "period_from": period_from,
                    "period_to": period_to,
                    "amount": total_amount,
                    "due_date": due_date,
                    "issued_at": None,
                }
            )
            await self.uow.commit()
            return invoice

    async def list_invoices(
        self,
        contract_id: uuid.UUID,
    ) -> Sequence[Invoice]:
        """Список инвойсов по договору (backoffice и B2B-клиент)."""
        async with self.uow:
            contract = await self.uow.contracts.get(contract_id)
            if not contract:
                raise ContractNotFoundError(contract_id)
            return await self.uow.invoices.get_by_contract(contract_id)

    async def get_invoice(
        self,
        contract_id: uuid.UUID,
        invoice_id: uuid.UUID,
    ) -> Invoice:
        """Один инвойс. Проверяет принадлежность договору (IDOR-guard)."""
        async with self.uow:
            invoice = await self.uow.invoices.get(invoice_id)
            if not invoice or invoice.contract_id != contract_id:
                raise InvoiceNotFoundError(invoice_id)
            return invoice

    async def issue_invoice(
        self,
        contract_id: uuid.UUID,
        invoice_id: uuid.UUID,
    ) -> Invoice:
        """DRAFT → ISSUED. Устанавливает issued_at = now(UTC)."""
        async with self.uow:
            invoice = await self.uow.invoices.get(invoice_id)
            if not invoice or invoice.contract_id != contract_id:
                raise InvoiceNotFoundError(invoice_id)
            if invoice.status != InvoiceStatus.DRAFT:
                raise InvalidInvoiceTransitionError(
                    invoice_id=invoice_id,
                    current_status=invoice.status,
                    expected_statuses=[InvoiceStatus.DRAFT],
                )
            invoice = await self.uow.invoices.update(
                invoice_id,
                {
                    "status": InvoiceStatus.ISSUED,
                    "issued_at": datetime.now(UTC),
                },
            )
            await self.uow.commit()
            return invoice

    async def mark_invoice_paid(
        self,
        contract_id: uuid.UUID,
        invoice_id: uuid.UUID,
    ) -> Invoice:
        """ISSUED | OVERDUE → PAID. Устанавливает paid_at = now(UTC).

        Логирует предупреждение, если для контракта нет
        финансовых транзакций, покрывающих сумму счёта.
        """
        async with self.uow:
            invoice = await self.uow.invoices.get(invoice_id)
            if not invoice or invoice.contract_id != contract_id:
                raise InvoiceNotFoundError(invoice_id)
            allowed = {InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE}
            if invoice.status not in allowed:
                raise InvalidInvoiceTransitionError(
                    invoice_id=invoice_id,
                    current_status=invoice.status,
                    expected_statuses=list(allowed),
                )

            # Аудит: проверяем наличие оплаты на счёте
            contract = await self.uow.contracts.get(contract_id)
            if contract:
                account = await self.uow.accounts.get_client_account(
                    contract.client_id,
                )
                if account and account.balance >= 0:
                    log.warning(
                        "invoice_marked_paid_no_payment",
                        invoice_id=str(invoice_id),
                        contract_id=str(contract_id),
                        invoice_amount=invoice.amount,
                        account_balance=account.balance,
                        hint=(
                            "Счёт отмечен оплаченным, но "
                            "баланс клиента ≥ 0 (нет долга)"
                        ),
                    )

            invoice = await self.uow.invoices.update(
                invoice_id,
                {
                    "status": InvoiceStatus.PAID,
                    "paid_at": datetime.now(UTC),
                },
            )
            await self.uow.commit()
            return invoice

    async def cancel_invoice(
        self,
        contract_id: uuid.UUID,
        invoice_id: uuid.UUID,
    ) -> Invoice:
        """DRAFT | ISSUED → CANCELLED. PAID/OVERDUE нельзя аннулировать."""
        async with self.uow:
            invoice = await self.uow.invoices.get(invoice_id)
            if not invoice or invoice.contract_id != contract_id:
                raise InvoiceNotFoundError(invoice_id)
            allowed = {InvoiceStatus.DRAFT, InvoiceStatus.ISSUED}
            if invoice.status not in allowed:
                raise InvalidInvoiceTransitionError(
                    invoice_id=invoice_id,
                    current_status=invoice.status,
                    expected_statuses=list(allowed),
                )
            invoice = await self.uow.invoices.update(
                invoice_id,
                {"status": InvoiceStatus.CANCELLED},
            )
            await self.uow.commit()
            return invoice

    async def get_reconciliation(
        self,
        contract_id: uuid.UUID,
        date_from: date,
        date_to: date,
    ) -> ReconciliationResponse:
        """Акт сверки: заказы + платежи клиента за период."""
        async with self.uow:
            contract = await self.uow.contracts.get_with_client(contract_id)
            if not contract:
                raise ContractNotFoundError(contract_id)

            # Временные границы (включающий диапазон)
            from_dt = datetime.combine(date_from, datetime.min.time()).replace(
                tzinfo=UTC
            )
            to_dt = datetime.combine(
                date_to + timedelta(days=1), datetime.min.time()
            ).replace(tzinfo=UTC)

            delivered_orders = await self.uow.orders.get_delivered_by_contract(
                contract_id=contract_id,
                date_from=date_from,
                date_to=date_to,
            )
            order_items = [
                ReconciliationOrderItem(
                    order_id=o.id,
                    created_at=o.created_at,
                    total_amount=o.total_amount,
                )
                for o in delivered_orders
            ]
            total_billed = sum(i.total_amount for i in order_items)

            payments = (
                await self.uow.transactions.get_bank_payments_for_client(
                    client_id=contract.client_id,
                    from_dt=from_dt,
                    to_dt=to_dt,
                )
            )
            payment_items = [
                ReconciliationPaymentItem(
                    transaction_id=p.id,
                    created_at=p.created_at,
                    amount=p.amount,
                    reason=p.reason,
                )
                for p in payments
            ]
            total_paid = sum(i.amount for i in payment_items)

            return ReconciliationResponse(
                contract_id=contract.id,
                contract_number=contract.number,
                client_name=contract.client.username,
                period_from=date_from,
                period_to=date_to,
                orders=order_items,
                total_billed=total_billed,
                payments=payment_items,
                total_paid=total_paid,
                balance=total_billed - total_paid,
            )

    # ─── АУДИТ СТАТУСОВ ──────────────────────────────────────────

    async def list_status_history(
        self,
        contract_id: uuid.UUID,
    ) -> Sequence[ContractStatusLog]:
        """История переходов статуса договора (хронологически)."""
        async with self.uow:
            contract = await self.uow.contracts.get(contract_id)
            if not contract:
                raise ContractNotFoundError(contract_id)
            return await self.uow.status_logs.get_by_contract(contract_id)

    # ─── ДОППСОГЛАШЕНИЯ ──────────────────────────────────────────

    async def create_amendment(
        self,
        contract_id: uuid.UUID,
        dto: AmendmentCreate,
        created_by_id: uuid.UUID | None = None,
    ) -> ContractAmendment:
        """Создать доп. соглашение к договору.

        Бизнес-правила:
        - Договор должен существовать.
        - Номер ДС уникален в рамках договора.
        """
        async with self.uow:
            contract = await self.uow.contracts.get(contract_id)
            if not contract:
                raise ContractNotFoundError(contract_id)

            existing = await self.uow.amendments.get_by_number(
                contract_id=contract_id,
                number=dto.number,
            )
            if existing:
                raise DuplicateAmendmentNumberError(
                    contract_id=contract_id,
                    number=dto.number,
                )

            amendment = await self.uow.amendments.add(
                {
                    "contract_id": contract_id,
                    "number": dto.number,
                    "description": dto.description,
                    "effective_date": dto.effective_date,
                    "created_by_id": created_by_id,
                }
            )
            await self.uow.commit()
            return amendment

    async def list_amendments(
        self,
        contract_id: uuid.UUID,
    ) -> Sequence[ContractAmendment]:
        """Все ДС по договору (от ранних к поздним)."""
        async with self.uow:
            contract = await self.uow.contracts.get(contract_id)
            if not contract:
                raise ContractNotFoundError(contract_id)
            return await self.uow.amendments.get_by_contract(contract_id)

    # ─── JOB-МЕТОДЫ (авто-статусы) ───────────────────────────────

    async def run_overdue_job(self) -> int:
        """Переводит ISSUED → OVERDUE инвойсы с истёкшим due_date.

        Идемпотентен: повторный вызов = 0 обновлений.
        Возвращает количество обновлённых записей.
        """
        async with self.uow:
            candidates = await self.uow.invoices.get_overdue_candidates()
            for invoice in candidates:
                await self.uow.invoices.update(
                    invoice.id,
                    {"status": InvoiceStatus.OVERDUE},
                )
            await self.uow.commit()
            return len(candidates)

    async def run_expire_job(self) -> int:
        """Переводит ACTIVE → EXPIRED договоры с истёкшим end_date.

        Для каждого истёкшего договора:
        - Отменяет NEW/ASSIGNED заказы и возвращает кредит
        - Логирует переход в ContractStatusLog

        Идемпотентен: повторный вызов = 0 обновлений.
        Возвращает количество обновлённых договоров.
        """
        async with self.uow:
            candidates = await self.uow.contracts.get_expirable()
            for contract in candidates:
                await self._cancel_inflight_orders(
                    contract.id,
                    reason="Истёк срок действия договора",
                )
                await self.uow.contracts.update(
                    contract.id,
                    {"status": ContractStatus.EXPIRED},
                )
                await self.uow.status_logs.add(
                    {
                        "contract_id": contract.id,
                        "from_status": ContractStatus.ACTIVE,
                        "to_status": ContractStatus.EXPIRED,
                        "changed_by_id": None,
                        "reason": ("Истёк срок действия договора"),
                    }
                )
            await self.uow.commit()
            return len(candidates)
