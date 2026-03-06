import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.repository import BaseRepository
from src.core.config import settings
from src.modules.finances.enums import AccountType, TransactionStatus
from src.modules.finances.models import Account, Transaction


class AccountRepository(BaseRepository[Account]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Account, session=session)

    async def create(
        self, user_id: uuid.UUID, account_type: AccountType, name: str
    ) -> Account:
        account = self.model(user_id=user_id, type=account_type, name=name)
        self.session.add(account)
        await self.session.flush()
        return account

    async def create_client_account(
        self, client_id: uuid.UUID, client_name: str
    ) -> Account:
        return await self.create(
            user_id=client_id,
            account_type=AccountType.CLIENT,
            name=f"Лицевой счет клиента: {client_name}",
        )

    async def create_courier_account(
        self, courier_id: uuid.UUID, courier_name: str
    ) -> Account:
        return await self.create(
            user_id=courier_id,
            account_type=AccountType.COURIER,
            name=f"Касса курьера: {courier_name}",
        )

    async def create_system_accounts(self, system_user_id: uuid.UUID) -> list[Account]:
        accounts = []
        system_map = {
            AccountType.REVENUE: "Системный счет выручки",
            AccountType.CASH: "Центральная касса (Наличные)",
            AccountType.CARD: "Счет эквайринга (Карты)",
            AccountType.BANK: "Расчетный счет (Банк)",
        }

        for acc_type, acc_name in system_map.items():
            acc = await self.create(
                user_id=system_user_id, account_type=acc_type, name=acc_name
            )
            accounts.append(acc)

        return accounts

    async def get_user_account_by_type(
        self, user_id: uuid.UUID, account_type: AccountType
    ) -> Account:
        query = select(self.model).where(
            self.model.user_id == user_id,
            self.model.type == account_type,
            self.model.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_system_account(self, account_type: AccountType) -> Account:
        return await self.get_user_account_by_type(
            user_id=settings.SYSTEM_USER_ID, account_type=account_type
        )

    async def get_system_revenue_account(self) -> Account:
        return await self.get_system_account(account_type=AccountType.REVENUE)

    async def get_system_cash_account(self) -> Account:
        return await self.get_system_account(account_type=AccountType.CASH)

    async def get_system_card_account(self) -> Account:
        return await self.get_system_account(account_type=AccountType.CARD)

    async def get_system_bank_account(self) -> Account:
        return await self.get_system_account(account_type=AccountType.BANK)

    async def get_courier_account(self, courier_id: uuid.UUID) -> Account:
        return await self.get_user_account_by_type(
            user_id=courier_id, account_type=AccountType.COURIER
        )

    async def get_client_account(self, client_id: uuid.UUID) -> Account:
        return await self.get_user_account_by_type(
            user_id=client_id, account_type=AccountType.CLIENT
        )


class TransactionRepository(BaseRepository[Transaction]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Transaction, session=session)

    async def get_for_update(self, transaction_id: uuid.UUID) -> Transaction | None:
        query = (
            select(Transaction)
            .where(Transaction.id == transaction_id)
            .with_for_update()
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def change_status(
        self,
        transaction_id: uuid.UUID,
        new_status: TransactionStatus,
        verified_by_id: uuid.UUID | None = None,
    ) -> Transaction | None:
        transaction = await self.get_for_update(transaction_id)

        if not transaction:
            return None

        if transaction.status == new_status:
            return transaction

        transaction.status = new_status

        if verified_by_id is not None:
            transaction.verified_by_id = verified_by_id

        await self.session.flush()
        return transaction

    async def get_by_order(self, order_id: uuid.UUID) -> Sequence[Transaction]:
        query = select(Transaction).where(Transaction.order_id == order_id)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_account_history(
        self, account_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> Sequence[Transaction]:
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
        result = await self.session.execute(query)
        return result.scalars().all()
