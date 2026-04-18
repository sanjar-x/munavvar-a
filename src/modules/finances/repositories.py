import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload
from sqlalchemy.sql import Select

from src.common.repository import BaseRepository
from src.core.constants import SYSTEM_USER_ID
from src.infrastructure.database.models import Account, Transaction, User
from src.modules.contracts.models import Contract
from src.modules.finances.enums import AccountType, TransactionStatus
from src.modules.finances.schemas import (
    AccountFilter,
    AccountSummary,
    TransactionFilter,
    TransactionSummary,
)
from src.modules.finances.search import ilike_pattern, normalize_q
from src.modules.orders.models import Order


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
            user_id=SYSTEM_USER_ID,
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
                self.model.user_id == SYSTEM_USER_ID,
                self.model.is_active.is_(True),
            )
            .order_by(self.model.type)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    def _apply_account_filters(
        self,
        select_from: Select,
        user_alias,
        filters: AccountFilter,
    ) -> Select:
        """Наложить WHERE по фильтру счетов на готовый SELECT ... FROM ... ."""
        stmt = select_from.where(Account.is_active.is_(True))

        if filters.type_in:
            stmt = stmt.where(Account.type.in_(filters.type_in))

        if filters.user_id is not None:
            stmt = stmt.where(Account.user_id == filters.user_id)

        if filters.user_role_in:
            stmt = stmt.where(user_alias.role.in_(filters.user_role_in))

        if filters.balance_from is not None:
            stmt = stmt.where(Account.balance >= filters.balance_from)
        if filters.balance_to is not None:
            stmt = stmt.where(Account.balance <= filters.balance_to)

        if filters.is_in_credit is True:
            stmt = stmt.where(Account.balance < 0)
        elif filters.is_in_credit is False:
            stmt = stmt.where(Account.balance >= 0)

        if filters.zero_balance is True:
            stmt = stmt.where(Account.balance == 0)

        if filters.has_debt is True:
            stmt = stmt.where(
                and_(
                    Account.type == AccountType.CLIENT,
                    Account.balance > 0,
                )
            )

        if filters.created_from is not None:
            stmt = stmt.where(Account.created_at >= filters.created_from)
        if filters.created_to is not None:
            stmt = stmt.where(Account.created_at <= filters.created_to)

        q = normalize_q(filters.q)
        if q is not None:
            pat = ilike_pattern(q)
            stmt = stmt.where(
                or_(
                    Account.name.ilike(pat),
                    user_alias.username.ilike(pat),
                )
            )

        return stmt

    async def get_accounts_with_filters(
        self,
        filters: AccountFilter,
        skip: int,
        limit: int,
    ) -> tuple[int, Sequence[Account]]:
        """Пагинированный список счетов по новому фильтру."""
        user_alias = aliased(User)

        base = select(Account).join(
            user_alias, Account.user_id == user_alias.id
        )
        base = self._apply_account_filters(base, user_alias, filters)

        count_q = (
            select(func.count())
            .select_from(Account)
            .join(user_alias, Account.user_id == user_alias.id)
        )
        count_q = self._apply_account_filters(count_q, user_alias, filters)

        total = (await self.session.execute(count_q)).scalar() or 0

        query = (
            base.options(joinedload(Account.user))
            .order_by(Account.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return total, result.scalars().unique().all()

    async def get_accounts_summary(
        self,
        filters: AccountFilter,
    ) -> AccountSummary:
        """Агрегаты по тому же фильтру: SUM(balance), COUNT GROUP BY type."""
        user_alias = aliased(User)

        sum_q = (
            select(func.coalesce(func.sum(Account.balance), 0))
            .select_from(Account)
            .join(user_alias, Account.user_id == user_alias.id)
        )
        sum_q = self._apply_account_filters(sum_q, user_alias, filters)
        sum_balance = int((await self.session.execute(sum_q)).scalar() or 0)

        count_q = (
            select(Account.type, func.count())
            .select_from(Account)
            .join(user_alias, Account.user_id == user_alias.id)
        )
        count_q = self._apply_account_filters(
            count_q, user_alias, filters
        ).group_by(Account.type)
        rows = (await self.session.execute(count_q)).all()
        count_by_type: dict[str, int] = {
            str(r[0].value): int(r[1]) for r in rows
        }
        return AccountSummary(
            sum_balance=sum_balance,
            count_by_type=count_by_type,
        )

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

    def _apply_transaction_filters(
        self,
        stmt: Select,
        from_acc,
        to_acc,
        from_user,
        to_user,
        order_alias,
        contract_alias,
        filters: TransactionFilter,
    ) -> Select:
        """Наложить WHERE по фильтру транзакций.

        Все JOIN (aliased) должны быть применены к stmt _до_ вызова.
        """
        stmt = stmt.where(Transaction.is_active.is_(True))

        if filters.status_in:
            stmt = stmt.where(Transaction.status.in_(filters.status_in))

        if filters.account_id is not None:
            direction = filters.direction
            if direction == "incoming":
                stmt = stmt.where(Transaction.to_id == filters.account_id)
            elif direction == "outgoing":
                stmt = stmt.where(Transaction.from_id == filters.account_id)
            elif direction == "internal":
                stmt = stmt.where(
                    and_(
                        Transaction.from_id == filters.account_id,
                        Transaction.to_id == filters.account_id,
                    )
                )
            else:
                stmt = stmt.where(
                    or_(
                        Transaction.from_id == filters.account_id,
                        Transaction.to_id == filters.account_id,
                    )
                )

        if filters.from_account_id is not None:
            stmt = stmt.where(Transaction.from_id == filters.from_account_id)
        if filters.to_account_id is not None:
            stmt = stmt.where(Transaction.to_id == filters.to_account_id)

        if filters.from_account_type_in:
            stmt = stmt.where(from_acc.type.in_(filters.from_account_type_in))
        if filters.to_account_type_in:
            stmt = stmt.where(to_acc.type.in_(filters.to_account_type_in))

        if filters.order_id is not None:
            stmt = stmt.where(Transaction.order_id == filters.order_id)
        if filters.has_order is True:
            stmt = stmt.where(Transaction.order_id.is_not(None))
        elif filters.has_order is False:
            stmt = stmt.where(Transaction.order_id.is_(None))

        if filters.order_status_in:
            stmt = stmt.where(order_alias.status.in_(filters.order_status_in))
        if filters.order_payment_method_in:
            stmt = stmt.where(
                order_alias.payment_method.in_(filters.order_payment_method_in)
            )
        if filters.order_sale_type_in:
            stmt = stmt.where(
                order_alias.sale_type.in_(filters.order_sale_type_in)
            )

        if filters.contract_id is not None:
            stmt = stmt.where(order_alias.contract_id == filters.contract_id)
        if filters.contract_number:
            pat = ilike_pattern(filters.contract_number)
            stmt = stmt.where(contract_alias.number.ilike(pat))

        if filters.client_id is not None:
            stmt = stmt.where(
                or_(
                    from_acc.user_id == filters.client_id,
                    to_acc.user_id == filters.client_id,
                )
            )
        if filters.courier_id is not None:
            stmt = stmt.where(
                or_(
                    from_acc.user_id == filters.courier_id,
                    to_acc.user_id == filters.courier_id,
                )
            )

        if filters.user_role_in:
            stmt = stmt.where(
                or_(
                    from_user.role.in_(filters.user_role_in),
                    to_user.role.in_(filters.user_role_in),
                )
            )

        if filters.verified_by_id is not None:
            stmt = stmt.where(
                Transaction.verified_by_id == filters.verified_by_id
            )
        if filters.verified is True:
            stmt = stmt.where(Transaction.verified_by_id.is_not(None))
        elif filters.verified is False:
            stmt = stmt.where(Transaction.verified_by_id.is_(None))

        if filters.reason_search:
            pat = ilike_pattern(filters.reason_search.strip())
            stmt = stmt.where(Transaction.reason.ilike(pat))

        if filters.amount_eq is not None:
            stmt = stmt.where(Transaction.amount == filters.amount_eq)
        if filters.amount_from is not None:
            stmt = stmt.where(Transaction.amount >= filters.amount_from)
        if filters.amount_to is not None:
            stmt = stmt.where(Transaction.amount <= filters.amount_to)

        if filters.date_from is not None:
            stmt = stmt.where(Transaction.created_at >= filters.date_from)
        if filters.date_to is not None:
            stmt = stmt.where(Transaction.created_at <= filters.date_to)

        q = normalize_q(filters.q)
        if q is not None:
            pat = ilike_pattern(q)
            stmt = stmt.where(
                or_(
                    Transaction.reason.ilike(pat),
                    from_acc.name.ilike(pat),
                    to_acc.name.ilike(pat),
                    from_user.username.ilike(pat),
                    to_user.username.ilike(pat),
                )
            )

        return stmt

    def _transaction_base_joins(self):
        """Вернуть (aliases..., base_select) с применёнными JOIN.

        base_select = select(Transaction) с LEFT/INNER JOIN на:
          - from_acc / to_acc (aliased Account),
          - from_user / to_user (aliased User) — через accounts.user_id,
          - order_alias (aliased Order, LEFT),
          - contract_alias (aliased Contract, LEFT).
        """
        from_acc = aliased(Account)
        to_acc = aliased(Account)
        from_user = aliased(User)
        to_user = aliased(User)
        order_alias = aliased(Order)
        contract_alias = aliased(Contract)

        stmt = (
            select(Transaction)
            .join(from_acc, Transaction.from_id == from_acc.id)
            .join(to_acc, Transaction.to_id == to_acc.id)
            .join(from_user, from_acc.user_id == from_user.id)
            .join(to_user, to_acc.user_id == to_user.id)
            .outerjoin(order_alias, Transaction.order_id == order_alias.id)
            .outerjoin(
                contract_alias, order_alias.contract_id == contract_alias.id
            )
        )
        return (
            from_acc,
            to_acc,
            from_user,
            to_user,
            order_alias,
            contract_alias,
            stmt,
        )

    async def get_transactions_with_filters(
        self,
        filters: TransactionFilter,
        skip: int,
        limit: int,
    ) -> tuple[int, Sequence[Transaction]]:
        """Пагинированный список транзакций по новому фильтру."""
        (
            from_acc,
            to_acc,
            from_user,
            to_user,
            order_alias,
            contract_alias,
            base,
        ) = self._transaction_base_joins()

        base = self._apply_transaction_filters(
            base,
            from_acc,
            to_acc,
            from_user,
            to_user,
            order_alias,
            contract_alias,
            filters,
        )

        # COUNT отдельным подзапросом (не таскаем joinedload).
        count_stmt = select(func.count()).select_from(
            base.with_only_columns(Transaction.id).subquery()
        )
        total = (await self.session.execute(count_stmt)).scalar() or 0

        order_col = Transaction.created_at
        order_expr = (
            order_col.asc() if filters.order == "asc" else (order_col.desc())
        )

        query = (
            base.options(
                joinedload(Transaction.from_account).joinedload(Account.user),
                joinedload(Transaction.to_account).joinedload(Account.user),
                joinedload(Transaction.verified_by),
            )
            .order_by(order_expr, Transaction.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return total, result.scalars().unique().all()

    async def get_transactions_summary(
        self,
        filters: TransactionFilter,
    ) -> TransactionSummary:
        """Агрегаты по тому же фильтру (без пагинации)."""
        (
            from_acc,
            to_acc,
            from_user,
            to_user,
            order_alias,
            contract_alias,
            base,
        ) = self._transaction_base_joins()
        base = self._apply_transaction_filters(
            base,
            from_acc,
            to_acc,
            from_user,
            to_user,
            order_alias,
            contract_alias,
            filters,
        )

        agg_stmt = select(
            func.coalesce(func.sum(Transaction.amount), 0),
            func.count(
                case((Transaction.status == TransactionStatus.PENDING, 1))
            ),
            func.count(
                case((Transaction.status == TransactionStatus.COMPLETED, 1))
            ),
            func.count(
                case((Transaction.status == TransactionStatus.REJECTED, 1))
            ),
        ).select_from(base.subquery())
        row = (await self.session.execute(agg_stmt)).one()
        return TransactionSummary(
            sum_amount=int(row[0]),
            count_by_status={
                TransactionStatus.PENDING.value: int(row[1]),
                TransactionStatus.COMPLETED.value: int(row[2]),
                TransactionStatus.REJECTED.value: int(row[3]),
            },
        )

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
        today_start = datetime.now(tz=UTC).replace(
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

    # — Strict Ledger: финансовая история иммутабельна —

    async def archive(self, id: uuid.UUID) -> bool:
        raise NotImplementedError("Strict Ledger: Нельзя скрывать транзакции.")

    async def restore(self, id: uuid.UUID) -> bool:
        raise NotImplementedError(
            "Strict Ledger: Нельзя восстанавливать транзакции."
        )

    async def delete(self, id: uuid.UUID) -> bool:
        raise NotImplementedError("Strict Ledger: Нельзя удалять транзакции.")
