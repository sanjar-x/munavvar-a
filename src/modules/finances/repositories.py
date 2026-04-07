import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from src.common.repository import BaseRepository
from src.core.config import settings
from src.infrastructure.database.models import Account, Transaction, User
from src.modules.finances.enums import AccountType, TransactionStatus


class AccountRepository(BaseRepository[Account]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Account, session=session)

    async def create(
        self,
        user_id: uuid.UUID,
        account_type: AccountType,
        name: str,
    ) -> Account:
        account = self.model(user_id=user_id, type=account_type, name=name)
        self.session.add(account)
        await self.session.flush()
        return account

    async def create_client_account(
        self,
        client_id: uuid.UUID,
        client_name: str,
    ) -> Account:
        return await self.create(
            user_id=client_id,
            account_type=AccountType.CLIENT,
            name=f"Лицевой счет клиента: {client_name}",
        )

    async def create_courier_account(
        self,
        courier_id: uuid.UUID,
        courier_name: str,
    ) -> Account:
        return await self.create(
            user_id=courier_id,
            account_type=AccountType.COURIER,
            name=f"Касса курьера: {courier_name}",
        )

    async def create_system_accounts(
        self,
        system_user_id: uuid.UUID,
    ) -> list[Account]:
        accounts = []
        system_map = {
            AccountType.REVENUE: "Системный счет выручки",
            AccountType.CASH: "Центральная касса (Наличные)",
            AccountType.CARD: "Счет эквайринга (Карты)",
            AccountType.BANK: "Расчетный счет (Банк)",
        }

        for acc_type, acc_name in system_map.items():
            acc = await self.create(
                user_id=system_user_id,
                account_type=acc_type,
                name=acc_name,
            )
            accounts.append(acc)

        return accounts

    async def get_user_account_by_type(
        self,
        user_id: uuid.UUID,
        account_type: AccountType,
    ) -> Account | None:
        query = select(self.model).where(
            self.model.user_id == user_id,
            self.model.type == account_type,
            self.model.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_system_account(
        self,
        account_type: AccountType,
    ) -> Account | None:
        return await self.get_user_account_by_type(
            user_id=settings.SYSTEM_USER_ID,
            account_type=account_type,
        )

    async def get_system_revenue_account(
        self,
    ) -> Account | None:
        return await self.get_system_account(account_type=AccountType.REVENUE)

    async def get_system_cash_account(
        self,
    ) -> Account | None:
        return await self.get_system_account(account_type=AccountType.CASH)

    async def get_system_card_account(
        self,
    ) -> Account | None:
        return await self.get_system_account(account_type=AccountType.CARD)

    async def get_system_bank_account(
        self,
    ) -> Account | None:
        return await self.get_system_account(account_type=AccountType.BANK)

    async def get_courier_account(
        self,
        courier_id: uuid.UUID,
    ) -> Account | None:
        return await self.get_user_account_by_type(
            user_id=courier_id,
            account_type=AccountType.COURIER,
        )

    async def get_client_account(self, client_id: uuid.UUID) -> Account | None:
        return await self.get_user_account_by_type(
            user_id=client_id,
            account_type=AccountType.CLIENT,
        )

    # --- Новые методы для BillingService ---

    async def get_all_system_accounts(
        self,
    ) -> Sequence[Account]:
        """Все счета, принадлежащие SYSTEM_USER_ID."""
        query = (
            select(self.model)
            .where(
                self.model.user_id == settings.SYSTEM_USER_ID,
                self.model.is_active.is_(True),
            )
            .order_by(self.model.type)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_accounts_with_filters(
        self,
        type: AccountType | None,
        search: str | None,
        has_debt: bool | None,
        skip: int,
        limit: int,
    ) -> tuple[int, Sequence[Account]]:
        """Пагинированный список счетов с фильтрами.

        JOIN User для поиска по имени пользователя.
        """
        base = (
            select(Account)
            .join(User, Account.user_id == User.id)
            .where(Account.is_active.is_(True))
        )
        count_q = (
            select(func.count())
            .select_from(Account)
            .join(User, Account.user_id == User.id)
            .where(Account.is_active.is_(True))
        )

        if type is not None:
            base = base.where(Account.type == type)
            count_q = count_q.where(Account.type == type)

        if search:
            pattern = f"%{search}%"
            search_cond = or_(
                Account.name.ilike(pattern),
                User.username.ilike(pattern),
            )
            base = base.where(search_cond)
            count_q = count_q.where(search_cond)

        if has_debt is True:
            debt_cond = and_(
                Account.type == AccountType.CLIENT,
                Account.balance > 0,
            )
            base = base.where(debt_cond)
            count_q = count_q.where(debt_cond)

        total = (await self.session.execute(count_q)).scalar() or 0

        query = (
            base.options(joinedload(Account.user))
            .order_by(Account.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        accounts = result.scalars().unique().all()

        return total, accounts

    async def get_total_client_debt(self) -> int:
        """Сумма balance для всех CLIENT-счетов где balance > 0."""
        query = select(func.coalesce(func.sum(Account.balance), 0)).where(
            Account.type == AccountType.CLIENT,
            Account.balance > 0,
            Account.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_total_courier_cash(self) -> int:
        """Сумма balance для всех COURIER-счетов где balance > 0."""
        query = select(func.coalesce(func.sum(Account.balance), 0)).where(
            Account.type == AccountType.COURIER,
            Account.balance > 0,
            Account.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_courier_accounts_with_users(
        self,
    ) -> Sequence[Account]:
        """Все COURIER-счета с eager-loaded user для сводки."""
        query = (
            select(Account)
            .options(joinedload(Account.user))
            .where(
                Account.type == AccountType.COURIER,
                Account.is_active.is_(True),
            )
            .order_by(Account.balance.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().unique().all()

    async def get_client_debtors(
        self,
        min_debt: int,
        skip: int,
        limit: int,
    ) -> tuple[int, Sequence[Account]]:
        """CLIENT-счета с balance > 0, eager-load user."""
        base_cond = [
            Account.type == AccountType.CLIENT,
            Account.balance > 0,
            Account.is_active.is_(True),
        ]
        if min_debt > 0:
            base_cond.append(Account.balance >= min_debt)

        count_q = select(func.count()).select_from(Account).where(*base_cond)
        total = (await self.session.execute(count_q)).scalar() or 0

        query = (
            select(Account)
            .options(joinedload(Account.user).joinedload(User.identities))
            .where(*base_cond)
            .order_by(Account.balance.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        accounts = result.scalars().unique().all()

        return total, accounts


class TransactionRepository(BaseRepository[Transaction]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Transaction, session=session)

    async def get_for_update(
        self,
        transaction_id: uuid.UUID,
    ) -> Transaction | None:
        query = (
            select(Transaction)
            .where(Transaction.id == transaction_id)
            .with_for_update()
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_with_accounts(
        self,
        transaction_id: uuid.UUID,
    ) -> Transaction | None:
        """Загрузить транзакцию с eager-load from/to_account."""
        query = (
            select(Transaction)
            .options(
                joinedload(Transaction.from_account),
                joinedload(Transaction.to_account),
            )
            .where(Transaction.id == transaction_id)
        )
        result = await self.session.execute(query)
        return result.scalars().unique().one_or_none()

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
        self,
        account_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Transaction]:
        query = (
            select(Transaction)
            .where(
                or_(
                    Transaction.from_id == account_id,
                    Transaction.to_id == account_id,
                ),
            )
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    # --- Новые методы для BillingService ---

    async def get_transactions_with_filters(
        self,
        filters: dict,
        skip: int,
        limit: int,
    ) -> tuple[int, Sequence[Transaction]]:
        """Пагинированные транзакции с фильтрами.

        Eager-load from_account и to_account.
        """
        base = select(Transaction).where(Transaction.is_active.is_(True))
        count_q = (
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.is_active.is_(True))
        )

        if filters.get("status") is not None:
            cond = Transaction.status == filters["status"]
            base = base.where(cond)
            count_q = count_q.where(cond)

        if filters.get("account_id") is not None:
            acc_id = filters["account_id"]
            cond = or_(
                Transaction.from_id == acc_id,
                Transaction.to_id == acc_id,
            )
            base = base.where(cond)
            count_q = count_q.where(cond)

        if filters.get("order_id") is not None:
            cond = Transaction.order_id == filters["order_id"]
            base = base.where(cond)
            count_q = count_q.where(cond)

        if filters.get("date_from") is not None:
            cond = Transaction.created_at >= filters["date_from"]
            base = base.where(cond)
            count_q = count_q.where(cond)

        if filters.get("date_to") is not None:
            cond = Transaction.created_at <= filters["date_to"]
            base = base.where(cond)
            count_q = count_q.where(cond)

        if filters.get("min_amount") is not None:
            cond = Transaction.amount >= filters["min_amount"]
            base = base.where(cond)
            count_q = count_q.where(cond)

        if filters.get("max_amount") is not None:
            cond = Transaction.amount <= filters["max_amount"]
            base = base.where(cond)
            count_q = count_q.where(cond)

        total = (await self.session.execute(count_q)).scalar() or 0

        query = (
            base.options(
                joinedload(Transaction.from_account),
                joinedload(Transaction.to_account),
            )
            .order_by(Transaction.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        transactions = result.scalars().unique().all()

        return total, transactions

    async def get_pending_count(self) -> int:
        """Количество PENDING-транзакций."""
        query = (
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.status == TransactionStatus.PENDING,
                Transaction.is_active.is_(True),
            )
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_pending_card_total(self, card_account_id: uuid.UUID) -> int:
        """Сумма PENDING-транзакций, где to_id = card_account_id."""
        query = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.to_id == card_account_id,
            Transaction.status == TransactionStatus.PENDING,
            Transaction.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_today_transactions_for_account(
        self,
        account_id: uuid.UUID,
    ) -> Sequence[Transaction]:
        """Все COMPLETED-транзакции за сегодня для счета."""
        today_start = datetime.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        query = (
            select(Transaction)
            .where(
                Transaction.status == TransactionStatus.COMPLETED,
                Transaction.created_at >= today_start,
                Transaction.is_active.is_(True),
                or_(
                    Transaction.from_id == account_id,
                    Transaction.to_id == account_id,
                ),
            )
            .order_by(Transaction.created_at.asc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_account_transactions_in_period(
        self,
        account_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
        skip: int,
        limit: int,
    ) -> Sequence[Transaction]:
        """Транзакции для счета в диапазоне дат (выписка)."""
        query = (
            select(Transaction)
            .options(
                joinedload(Transaction.from_account),
                joinedload(Transaction.to_account),
            )
            .where(
                Transaction.is_active.is_(True),
                Transaction.status == TransactionStatus.COMPLETED,
                Transaction.created_at >= date_from,
                Transaction.created_at <= date_to,
                or_(
                    Transaction.from_id == account_id,
                    Transaction.to_id == account_id,
                ),
            )
            .order_by(Transaction.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().unique().all()

    async def get_opening_balance_data(
        self,
        account_id: uuid.UUID,
        before_date: datetime,
    ) -> tuple[int, int]:
        """Суммы входящих и исходящих COMPLETED-транзакций до даты.

        Возвращает (total_incoming, total_outgoing) для расчёта
        opening balance.
        """
        # Входящие: to_id = account_id
        incoming_q = select(
            func.coalesce(func.sum(Transaction.amount), 0),
        ).where(
            Transaction.to_id == account_id,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.created_at < before_date,
            Transaction.is_active.is_(True),
        )
        # Исходящие: from_id = account_id
        outgoing_q = select(
            func.coalesce(func.sum(Transaction.amount), 0),
        ).where(
            Transaction.from_id == account_id,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.created_at < before_date,
            Transaction.is_active.is_(True),
        )

        incoming_result = await self.session.execute(incoming_q)
        outgoing_result = await self.session.execute(outgoing_q)

        total_incoming = incoming_result.scalar() or 0
        total_outgoing = outgoing_result.scalar() or 0

        return total_incoming, total_outgoing

    async def get_recent_for_account(
        self,
        account_id: uuid.UUID,
        limit: int = 10,
    ) -> Sequence[Transaction]:
        """Последние транзакции для счета с eager-load."""
        query = (
            select(Transaction)
            .options(
                joinedload(Transaction.from_account),
                joinedload(Transaction.to_account),
            )
            .where(
                Transaction.is_active.is_(True),
                or_(
                    Transaction.from_id == account_id,
                    Transaction.to_id == account_id,
                ),
            )
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().unique().all()

    async def get_bank_payments_for_client(
        self,
        client_id: uuid.UUID,
        from_dt: datetime,
        to_dt: datetime,
    ) -> Sequence[Transaction]:
        """COMPLETED платежи клиента на банковский счёт за период.

        Используется в акте сверки (reconciliation).
        CLIENT-счёт → BANK-счёт системы.
        """
        from_acc = aliased(Account)
        to_acc = aliased(Account)
        query = (
            select(Transaction)
            .join(from_acc, Transaction.from_id == from_acc.id)
            .join(to_acc, Transaction.to_id == to_acc.id)
            .where(
                from_acc.user_id == client_id,
                from_acc.type == AccountType.CLIENT,
                to_acc.type == AccountType.BANK,
                Transaction.status == TransactionStatus.COMPLETED,
                Transaction.created_at >= from_dt,
                Transaction.created_at < to_dt,
                Transaction.is_active.is_(True),
            )
            .order_by(Transaction.created_at)
        )
        result = await self.session.execute(query)
        return result.scalars().all()
