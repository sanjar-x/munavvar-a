# src/modules/contracts/services.py
import uuid
from datetime import UTC, date, datetime

from src.modules.contracts.enums import ContractStatus, InvoiceStatus
from src.modules.contracts.exceptions import (
    ContractAlreadyActiveError,
    ContractNotFoundError,
    ContractPriceItemNotFoundError,
    ContractStatusTransitionError,
)
from src.modules.contracts.models import Contract, ContractPriceItem
from src.modules.contracts.schemas import ContractCreate, ContractUpdate
from src.modules.contracts.uow import IContractUnitOfWork


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
                    "bank_account_number": dto.bank_account_number,
                    "bank_name": dto.bank_name,
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
                contract.client_id
            )
            if existing and existing.id != contract_id:
                raise ContractAlreadyActiveError(
                    client_id=contract.client_id,
                    existing_contract_id=existing.id,
                )

            updated = await self.uow.contracts.update(
                contract_id,
                {
                    "status": ContractStatus.ACTIVE,
                    "signed_at": datetime.now(tz=UTC),
                    "signed_by_id": signed_by_id,
                },
            )
            await self.uow.commit()
            return updated

    async def suspend_contract(
        self,
        contract_id: uuid.UUID,
        reason: str,
    ) -> Contract:
        """ACTIVE → SUSPENDED."""
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
            updated = await self.uow.contracts.update(
                contract_id,
                {
                    "status": ContractStatus.SUSPENDED,
                    "suspended_at": datetime.now(tz=UTC),
                    "suspension_reason": reason,
                },
            )
            await self.uow.commit()
            return updated

    async def reinstate_contract(self, contract_id: uuid.UUID) -> Contract:
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
            # Проверяем коллизию: мог появиться другой ACTIVE
            existing = await self.uow.contracts.get_active_for_client(
                contract.client_id
            )
            if existing and existing.id != contract_id:
                raise ContractAlreadyActiveError(
                    client_id=contract.client_id,
                    existing_contract_id=existing.id,
                )
            updated = await self.uow.contracts.update(
                contract_id,
                {
                    "status": ContractStatus.ACTIVE,
                    "suspended_at": None,
                    "suspension_reason": None,
                },
            )
            await self.uow.commit()
            return updated

    async def terminate_contract(
        self,
        contract_id: uuid.UUID,
        reason: str,
    ) -> Contract:
        """ACTIVE/SUSPENDED → TERMINATED."""
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
            updated = await self.uow.contracts.update(
                contract_id,
                {
                    "status": ContractStatus.TERMINATED,
                    "terminated_at": datetime.now(tz=UTC),
                    "termination_reason": reason,
                },
            )
            await self.uow.commit()
            return updated

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
    ):
        """Сформировать счёт-фактуру за период."""
        async with self.uow:
            contract = await self.uow.contracts.get(contract_id)
            if not contract:
                raise ContractNotFoundError(contract_id)

            delivered_orders = await self.uow.orders.get_delivered_by_contract(
                contract_id=contract_id,
                date_from=period_from,
                date_to=period_to,
            )
            total_amount = sum(o.total_amount for o in delivered_orders)

            # Порядковый номер инвойса по договору
            existing = await self.uow.invoices.get_multi(
                contract_id=contract_id
            )
            sequence = len(existing) + 1
            number = (
                f"{contract.number}"
                f"/{period_from.year}"
                f"-{period_from.month:02d}"
                f"-{sequence:03d}"
            )

            invoice = await self.uow.invoices.add(
                {
                    "contract_id": contract_id,
                    "number": number,
                    "status": InvoiceStatus.ISSUED,
                    "period_from": period_from,
                    "period_to": period_to,
                    "amount": total_amount,
                    "due_date": None,
                    "issued_at": datetime.now(UTC),
                }
            )
            await self.uow.commit()
            return invoice
