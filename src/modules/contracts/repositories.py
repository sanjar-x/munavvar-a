# src/modules/contracts/repositories.py
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from src.common.repository import BaseRepository
from src.modules.contracts.enums import ContractStatus, InvoiceStatus
from src.modules.contracts.models import (
    Contract,
    ContractAmendment,
    ContractPriceItem,
    ContractStatusLog,
    Invoice,
)

log = structlog.get_logger(__name__)


class ContractRepository(BaseRepository[Contract]):
    def __init__(self, session: Any):
        super().__init__(model=Contract, session=session)

    async def get_active_for_client(
        self,
        client_id: uuid.UUID,
        with_for_update: bool = False,
    ) -> Contract | None:
        """Активный договор клиента.
        with_for_update=True — при проверке кредитного лимита
        для предотвращения race condition (TOCTOU).
        """
        query = select(Contract).where(
            Contract.client_id == client_id,
            Contract.status == ContractStatus.ACTIVE,
            Contract.is_active.is_(True),
        )
        if with_for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_with_price_items(
        self,
        contract_id: uuid.UUID,
    ) -> Contract | None:
        """Договор с eager-loaded прайс-листом (для API ответа)."""
        query = (
            select(Contract)
            .options(selectinload(Contract.price_items))
            .where(
                Contract.id == contract_id,
                Contract.is_active.is_(True),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_price_map_for_products(
        self,
        contract_id: uuid.UUID,
        product_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, int]:
        """Возвращает {product_id: price} из договорного прайс-листа.
        Только для запрошенных product_ids.
        Используется в create_order() для override каталожных цен.
        """
        if not product_ids:
            return {}
        query = select(ContractPriceItem).where(
            ContractPriceItem.contract_id == contract_id,
            ContractPriceItem.product_id.in_(product_ids),
            ContractPriceItem.is_active.is_(True),
        )
        result = await self.session.execute(query)
        items = result.scalars().all()
        return {item.product_id: item.price for item in items}

    async def get_with_client(
        self,
        contract_id: uuid.UUID,
    ) -> Contract | None:
        """Договор с eager-loaded client (для актов сверки)."""
        query = (
            select(Contract)
            .options(joinedload(Contract.client))
            .where(
                Contract.id == contract_id,
                Contract.is_active.is_(True),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_multi_with_client(
        self,
        status: ContractStatus | None,
        client_id: uuid.UUID | None,
        skip: int,
        limit: int,
    ) -> tuple[int, Sequence[Contract]]:
        """Пагинированный список договоров (backoffice)."""
        base = (
            select(Contract)
            .options(joinedload(Contract.client))
            .where(Contract.is_active.is_(True))
        )
        count_q = (
            sa.select(sa.func.count())
            .select_from(Contract)
            .where(Contract.is_active.is_(True))
        )
        if status:
            base = base.where(Contract.status == status)
            count_q = count_q.where(Contract.status == status)
        if client_id:
            base = base.where(Contract.client_id == client_id)
            count_q = count_q.where(Contract.client_id == client_id)

        total = (await self.session.execute(count_q)).scalar() or 0
        result = await self.session.execute(
            base.order_by(Contract.created_at.desc()).offset(skip).limit(limit)
        )
        return total, result.scalars().unique().all()

    async def increment_credit_used(
        self,
        contract_id: uuid.UUID,
        amount: int,
    ) -> None:
        """Атомарный инкремент credit_used при создании заказа.
        Вызывается ПОСЛЕ lock на строку договора (with_for_update=True).
        """
        stmt = (
            sa.update(Contract)
            .where(Contract.id == contract_id)
            .values(credit_used=Contract.credit_used + amount)
        )
        await self.session.execute(stmt)
        log.info(
            "credit_reserved",
            contract_id=str(contract_id),
            amount=amount,
        )

    async def decrement_credit_used(
        self,
        contract_id: uuid.UUID,
        amount: int,
    ) -> None:
        """Уменьшение credit_used при завершении доставки/отмене.
        Долг переходит с credit_used на account.balance (через триггер).
        """
        # Проверяем текущее значение для обнаружения аномалий
        current = await self.session.scalar(
            sa.select(Contract.credit_used).where(Contract.id == contract_id)
        )
        if current is not None and current < amount:
            log.warning(
                "credit_underflow_detected",
                contract_id=str(contract_id),
                current_credit_used=current,
                decrement_amount=amount,
                deficit=amount - current,
            )
        stmt = (
            sa.update(Contract)
            .where(Contract.id == contract_id)
            .values(
                credit_used=sa.func.greatest(Contract.credit_used - amount, 0)
            )
        )
        await self.session.execute(stmt)
        log.info(
            "credit_released",
            contract_id=str(contract_id),
            amount=amount,
        )

    async def get_expirable(self) -> Sequence[Contract]:
        """ACTIVE договоры с истёкшим end_date (кандидаты → EXPIRED).

        Выбирает только договоры с явно указанным end_date
        (NULL = бессрочный договор, не истекает).
        """
        today = datetime.now(tz=UTC).date()
        query = select(Contract).where(
            Contract.status == ContractStatus.ACTIVE,
            Contract.is_active.is_(True),
            Contract.end_date.is_not(None),
            Contract.end_date < today,
        )
        result = await self.session.execute(query)
        return result.scalars().all()


class ContractPriceItemRepository(BaseRepository[ContractPriceItem]):
    def __init__(self, session: Any):
        super().__init__(model=ContractPriceItem, session=session)

    async def get_by_contract_and_product(
        self,
        contract_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> ContractPriceItem | None:
        return await self.get_by(
            contract_id=contract_id,
            product_id=product_id,
        )


class InvoiceRepository(BaseRepository[Invoice]):
    def __init__(self, session: Any):
        super().__init__(model=Invoice, session=session)

    async def get_by_contract(
        self,
        contract_id: uuid.UUID,
    ) -> Sequence[Invoice]:
        """Все инвойсы по договору, от новых к старым."""
        query = (
            select(Invoice)
            .where(
                Invoice.contract_id == contract_id,
                Invoice.is_active.is_(True),
            )
            .order_by(Invoice.created_at.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_for_period(
        self,
        contract_id: uuid.UUID,
        period_from: date,
        period_to: date,
    ) -> Invoice | None:
        """Проверка дубля: уже есть не-CANCELLED инвойс за этот период?"""
        query = select(Invoice).where(
            Invoice.contract_id == contract_id,
            Invoice.period_from == period_from,
            Invoice.period_to == period_to,
            Invoice.status != InvoiceStatus.CANCELLED,
            Invoice.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_overdue_candidates(self) -> Sequence[Invoice]:
        """ISSUED инвойсы с истёкшим due_date (кандидаты → OVERDUE)."""
        today = datetime.now(tz=UTC).date()
        query = select(Invoice).where(
            Invoice.status == InvoiceStatus.ISSUED,
            Invoice.is_active.is_(True),
            Invoice.due_date.is_not(None),
            Invoice.due_date < today,
        )
        result = await self.session.execute(query)
        return result.scalars().all()


class ContractStatusLogRepository(BaseRepository[ContractStatusLog]):
    def __init__(self, session: Any):
        super().__init__(model=ContractStatusLog, session=session)

    async def get_by_contract(
        self,
        contract_id: uuid.UUID,
    ) -> Sequence[ContractStatusLog]:
        """История переходов статуса по договору (хронологически)."""
        query = (
            select(ContractStatusLog)
            .where(ContractStatusLog.contract_id == contract_id)
            .order_by(ContractStatusLog.created_at.asc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()


class ContractAmendmentRepository(BaseRepository[ContractAmendment]):
    def __init__(self, session: Any):
        super().__init__(model=ContractAmendment, session=session)

    async def get_by_contract(
        self,
        contract_id: uuid.UUID,
    ) -> Sequence[ContractAmendment]:
        """Все ДС по договору (от ранних к поздним)."""
        query = (
            select(ContractAmendment)
            .where(ContractAmendment.contract_id == contract_id)
            .order_by(ContractAmendment.effective_date.asc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_number(
        self,
        contract_id: uuid.UUID,
        number: str,
    ) -> ContractAmendment | None:
        """Проверка уникальности номера ДС в рамках договора."""
        query = select(ContractAmendment).where(
            ContractAmendment.contract_id == contract_id,
            ContractAmendment.number == number,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
