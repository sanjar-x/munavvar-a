import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Result, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.repository import BaseRepository
from src.modules.finances.models import (
    Account,
    AccountType,
    Transaction,
    TransactionStatus,
)


class AccountRepository(BaseRepository[Account]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Account, session=session)

    async def get_for_update(self, account_id: uuid.UUID) -> Account | None:
        query = (
            select(Account).where(Account.id == account_id).with_for_update()
        )
        result: Result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_many_for_update(
        self, account_ids: list[uuid.UUID]
    ) -> list[Account]:
        query = (
            select(Account)
            .where(Account.id.in_(account_ids))
            .order_by(Account.id)
            .with_for_update()
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_system_account(
        self, account_type: AccountType, system_user_id: uuid.UUID
    ) -> Account:
        query = select(self.model).where(
            self.model.type == account_type,
            self.model.user_id == system_user_id,
            self.model.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_system_revenue_account(
        self, system_user_id: uuid.UUID
    ) -> Account:
        return await self.get_system_account(
            account_type=AccountType.REVENUE, system_user_id=system_user_id
        )

    async def get_system_cash_account(
        self, system_user_id: uuid.UUID
    ) -> Account:
        return await self.get_system_account(
            account_type=AccountType.CASH, system_user_id=system_user_id
        )

    async def get_system_card_account(
        self, system_user_id: uuid.UUID
    ) -> Account:
        return await self.get_system_account(
            account_type=AccountType.CARD, system_user_id=system_user_id
        )

    async def get_system_bank_account(
        self, system_user_id: uuid.UUID
    ) -> Account:
        return await self.get_system_account(
            account_type=AccountType.BANK, system_user_id=system_user_id
        )

    async def get_account(
        self, account_type: AccountType, user_id: uuid.UUID
    ) -> Account | None:
        query = select(self.model).where(
            self.model.type == account_type,
            self.model.user_id == user_id,
            self.model.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_client_account(self, client_id: uuid.UUID) -> Account | None:
        """Получает лицевой счет клиента для биллинга."""
        return await self.get_account(
            account_type=AccountType.CLIENT, user_id=client_id
        )

    async def get_courier_account(
        self, courier_id: uuid.UUID
    ) -> Account | None:
        """Получает счет курьера (например, для учета принятых наличных)."""
        return await self.get_account(
            account_type=AccountType.COURIER, user_id=courier_id
        )

    async def get_all_by_user(self, user_id: uuid.UUID) -> Sequence[Account]:
        query = select(Account).where(
            Account.user_id == user_id,
            Account.is_active.is_(True),
        )
        result: Result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_all_by_type(
        self, account_type: AccountType
    ) -> Sequence[Account]:
        query = select(Account).where(
            Account.type == account_type,
            Account.is_active.is_(True),
        )
        result: Result = await self.session.execute(query)
        return list(result.scalars().all())


class TransactionRepository(BaseRepository[Transaction]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Transaction, session=session)

    async def get_for_update(
        self, transaction_id: uuid.UUID
    ) -> Transaction | None:
        query = (
            select(Transaction)
            .where(Transaction.id == transaction_id)
            .with_for_update()
        )
        result: Result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_order_id(
        self, order_id: uuid.UUID
    ) -> Sequence[Transaction]:
        """
        Получить все финансовые движения по конкретному заказу (Аудит).
        """
        query = select(Transaction).where(Transaction.order_id == order_id)
        result: Result[Any] = await self.session.execute(query)
        return result.scalars().all()

    async def get_account_history(
        self, account_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> Sequence[Transaction]:
        """
        Получить выписку по счету (историю операций) с пагинацией.
        """
        query = (
            select(Transaction)
            .where(
                or_(
                    Transaction.from_id == account_id,
                    Transaction.to_id == account_id,
                )
            )
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result: Result[Any] = await self.session.execute(query)
        return result.scalars().all()

    async def calculate_balance(self, account_id: uuid.UUID) -> int:

        query = select(
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.to_id == account_id, Transaction.amount),
                        (
                            Transaction.from_id == account_id,
                            -Transaction.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            )
        ).where(
            or_(
                Transaction.from_id == account_id,
                Transaction.to_id == account_id,
            ),
            Transaction.status == TransactionStatus.COMPLETED,
        )

        result: Result[Any] = await self.session.execute(query)
        return result.scalar_one()  # Вернет int (сумму в копейках/тиыйнах)
