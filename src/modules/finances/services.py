# src/modules/finances/services.py
import uuid
from datetime import datetime

from src.modules.finances.enums import (
    AccountType,
    TransactionStatus,
)
from src.modules.finances.exceptions import (
    AccountNotFoundError,
    InvalidTransactionStatusError,
    SelfTransferError,
    TransactionNotFoundError,
)
from src.modules.finances.schemas import (
    AccountDetail,
    AccountResponse,
    AccountShort,
    AccountStatement,
    ClientDebt,
    ClientsDebtsResponse,
    CourierFinanceSummary,
    CouriersSummaryResponse,
    DashboardTotals,
    FinanceDashboard,
    StatementEntry,
    StatementPeriod,
    SystemAccountSummary,
    TransactionCreate,
    TransactionDetail,
    TransactionResponse,
)
from src.modules.finances.uow import FinancesUnitOfWork


class BillingService:
    def __init__(self, uow: FinancesUnitOfWork):
        self.uow: FinancesUnitOfWork = uow

    # ----------------------------------------------------------
    # Dashboard
    # ----------------------------------------------------------

    async def get_dashboard(self) -> FinanceDashboard:
        """Получение финансового дашборда с итогами."""
        async with self.uow:
            system_accounts = await self.uow.accounts.get_all_system_accounts()

            # Формируем словарь системных счетов по типу
            accounts_map: dict[str, SystemAccountSummary] = {}
            revenue_balance = 0
            cash_balance = 0
            card_account_id: uuid.UUID | None = None

            for acc in system_accounts:
                summary = SystemAccountSummary(
                    id=acc.id,
                    balance=acc.balance,
                    name=acc.name,
                )
                accounts_map[acc.type.value] = summary

                if acc.type == AccountType.REVENUE:
                    revenue_balance = acc.balance
                elif acc.type == AccountType.CASH:
                    cash_balance = acc.balance
                elif acc.type == AccountType.CARD:
                    card_account_id = acc.id

            # Считаем агрегаты
            total_card_pending = 0
            if card_account_id is not None:
                total_card_pending = (
                    await self.uow.transactions.get_pending_card_total(
                        card_account_id,
                    )
                )

            total_client_debt = await self.uow.accounts.get_total_client_debt()
            total_courier_cash = (
                await self.uow.accounts.get_total_courier_cash()
            )
            pending_count = await self.uow.transactions.get_pending_count()

            totals = DashboardTotals(
                # revenue всегда отрицательный, показываем
                # как положительное число
                total_revenue=-revenue_balance,
                total_cash_in_hand=cash_balance,
                total_card_pending=total_card_pending,
                total_client_debt=total_client_debt,
                total_courier_cash=total_courier_cash,
            )

            return FinanceDashboard(
                system_accounts=accounts_map,
                totals=totals,
                pending_transactions_count=pending_count,
            )

    # ----------------------------------------------------------
    # Accounts
    # ----------------------------------------------------------

    async def get_accounts(
        self,
        skip: int,
        limit: int,
        type: AccountType | None = None,
        search: str | None = None,
        has_debt: bool | None = None,
    ) -> dict:
        """Пагинированный список счетов с фильтрами."""
        async with self.uow:
            total, items = (
                await self.uow.accounts.get_accounts_with_filters(
                    type=type,
                    search=search,
                    has_debt=has_debt,
                    skip=skip,
                    limit=limit,
                )
            )
            accounts = [
                AccountResponse.model_validate(acc)
                for acc in items
            ]
            return {
                "total_count": total,
                "accounts": accounts,
            }

    async def get_account_detail(self, account_id: uuid.UUID) -> AccountDetail:
        """Детальная информация о счете с последними транзакциями."""
        async with self.uow:
            account = await self.uow.accounts.get(account_id)
            if not account:
                raise AccountNotFoundError(account_id=account_id)

            # Подгружаем user через отдельный запрос
            # (отношение может быть lazy="raise")
            from sqlalchemy import select
            from sqlalchemy.orm import joinedload

            from src.modules.finances.models import (
                Account as AccountModel,
            )

            q = (
                select(AccountModel)
                .options(joinedload(AccountModel.user))
                .where(AccountModel.id == account_id)
            )
            res = await self.uow.session.execute(q)
            account = res.scalars().unique().one()

            # Последние транзакции
            recent_txns = await self.uow.transactions.get_recent_for_account(
                account_id=account_id,
                limit=10,
            )

            txn_details = [
                TransactionDetail(
                    id=t.id,
                    from_account=AccountShort.model_validate(t.from_account),
                    to_account=AccountShort.model_validate(t.to_account),
                    amount=t.amount,
                    status=t.status,
                    reason=t.reason,
                    order_id=t.order_id,
                    verified_by_id=t.verified_by_id,
                    created_at=t.created_at,
                )
                for t in recent_txns
            ]

            user_name = account.user.username if account.user else None

            return AccountDetail(
                id=account.id,
                user_id=account.user_id,
                name=account.name,
                type=account.type,
                balance=account.balance,
                created_at=account.created_at,
                updated_at=account.updated_at,
                user_name=user_name,
                recent_transactions=txn_details,
            )

    # ----------------------------------------------------------
    # Statement
    # ----------------------------------------------------------

    async def get_account_statement(
        self,
        account_id: uuid.UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> AccountStatement:
        """Выписка по счету за период с running balance."""
        async with self.uow:
            account = await self.uow.accounts.get(account_id)
            if not account:
                raise AccountNotFoundError(account_id=account_id)

            now = datetime.now()
            if date_from is None:
                date_from = now.replace(
                    day=1, hour=0, minute=0,
                    second=0, microsecond=0,
                )
            if date_to is None:
                date_to = now

            dt_from = date_from.replace(
                hour=0, minute=0, second=0, microsecond=0,
            )
            dt_to = date_to.replace(
                hour=23, minute=59, second=59, microsecond=0,
            )

            # Opening balance = incoming - outgoing до начала
            (
                incoming_before,
                outgoing_before,
            ) = await self.uow.transactions.get_opening_balance_data(
                account_id=account_id,
                before_date=dt_from,
            )
            opening_balance = incoming_before - outgoing_before

            # Транзакции за период
            transactions = (
                await self.uow.transactions.get_account_transactions_in_period(
                    account_id=account_id,
                    date_from=dt_from,
                    date_to=dt_to,
                    skip=skip,
                    limit=limit,
                )
            )

            # Формируем записи выписки с running balance
            entries: list[StatementEntry] = []
            running = opening_balance
            total_incoming = 0
            total_outgoing = 0

            for txn in transactions:
                is_incoming = txn.to_id == account_id
                direction = "incoming" if is_incoming else "outgoing"

                if is_incoming:
                    running += txn.amount
                    total_incoming += txn.amount
                    counterparty_acc = txn.from_account
                else:
                    running -= txn.amount
                    total_outgoing += txn.amount
                    counterparty_acc = txn.to_account

                entries.append(
                    StatementEntry(
                        id=txn.id,
                        direction=direction,
                        counterparty=AccountShort.model_validate(
                            counterparty_acc,
                        ),
                        amount=txn.amount,
                        running_balance=running,
                        status=txn.status,
                        reason=txn.reason,
                        order_id=txn.order_id,
                        created_at=txn.created_at,
                    ),
                )

            closing_balance = running

            account_short = AccountShort(
                id=account.id,
                name=account.name,
                type=account.type,
            )

            period = StatementPeriod(
                date_from=dt_from.date(),
                date_to=dt_to.date(),
                opening_balance=opening_balance,
                closing_balance=closing_balance,
                total_incoming=total_incoming,
                total_outgoing=total_outgoing,
            )

            return AccountStatement(
                account=account_short,
                period=period,
                transactions=entries,
            )

    # ----------------------------------------------------------
    # Transactions
    # ----------------------------------------------------------

    async def get_transactions(
        self,
        skip: int,
        limit: int,
        status: TransactionStatus | None = None,
        account_id: uuid.UUID | None = None,
        order_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_amount: int | None = None,
        max_amount: int | None = None,
    ) -> dict:
        """Пагинированный список транзакций с фильтрами."""
        filters = {
            "status": status,
            "account_id": account_id,
            "order_id": order_id,
            "date_from": date_from,
            "date_to": date_to,
            "min_amount": min_amount,
            "max_amount": max_amount,
        }
        async with self.uow:
            (
                total,
                items,
            ) = (
                await self.uow.transactions
                .get_transactions_with_filters(
                    filters=filters,
                    skip=skip,
                    limit=limit,
                )
            )
            transactions = [
                TransactionDetail(
                    id=t.id,
                    from_account=AccountShort.model_validate(
                        t.from_account,
                    ),
                    to_account=AccountShort.model_validate(
                        t.to_account,
                    ),
                    amount=t.amount,
                    status=t.status,
                    reason=t.reason,
                    order_id=t.order_id,
                    verified_by_id=t.verified_by_id,
                    created_at=t.created_at,
                )
                for t in items
            ]
            return {
                "total_count": total,
                "transactions": transactions,
            }

    async def create_transaction(
        self,
        dto: TransactionCreate,
        created_by_id: uuid.UUID,
    ) -> TransactionResponse:
        """Ручная проводка (COMPLETED немедленно).

        Валидация: from != to, amount > 0, оба счета существуют.
        """
        if dto.from_id == dto.to_id:
            raise SelfTransferError(account_id=dto.from_id)

        async with self.uow:
            from_account = await self.uow.accounts.get(dto.from_id)
            if not from_account:
                raise AccountNotFoundError(
                    account_id=dto.from_id,
                    message=(
                        "Счет списания не найден:"
                        f" {dto.from_id}"
                    ),
                )

            to_account = await self.uow.accounts.get(dto.to_id)
            if not to_account:
                raise AccountNotFoundError(
                    account_id=dto.to_id,
                    message=(
                        "Счет зачисления не найден:"
                        f" {dto.to_id}"
                    ),
                )

            txn_data = {
                "from_id": dto.from_id,
                "to_id": dto.to_id,
                "amount": dto.amount,
                "reason": dto.reason,
                "order_id": dto.order_id,
                "status": TransactionStatus.COMPLETED,
                "verified_by_id": created_by_id,
            }
            txn = await self.uow.transactions.add(txn_data)
            await self.uow.commit()

            return TransactionResponse.model_validate(txn)

    async def verify_transaction(
        self,
        transaction_id: uuid.UUID,
        verified_by_id: uuid.UUID,
    ) -> TransactionResponse:
        """PENDING -> COMPLETED. Устанавливает verified_by_id."""
        async with self.uow:
            txn = await self.uow.transactions.get_for_update(
                transaction_id,
            )
            if not txn:
                raise TransactionNotFoundError(
                    transaction_id=transaction_id,
                )

            if txn.status != TransactionStatus.PENDING:
                raise InvalidTransactionStatusError(
                    transaction_id=transaction_id,
                    current_status=txn.status,
                )

            txn.status = TransactionStatus.COMPLETED
            txn.verified_by_id = verified_by_id
            await self.uow.flush()
            await self.uow.commit()

            return TransactionResponse.model_validate(txn)

    async def reject_transaction(
        self,
        transaction_id: uuid.UUID,
        verified_by_id: uuid.UUID,
        reason: str | None = None,
    ) -> TransactionResponse:
        """PENDING -> REJECTED. Устанавливает verified_by_id."""
        async with self.uow:
            txn = await self.uow.transactions.get_for_update(
                transaction_id,
            )
            if not txn:
                raise TransactionNotFoundError(
                    transaction_id=transaction_id,
                )

            if txn.status != TransactionStatus.PENDING:
                raise InvalidTransactionStatusError(
                    transaction_id=transaction_id,
                    current_status=txn.status,
                )

            txn.status = TransactionStatus.REJECTED
            txn.verified_by_id = verified_by_id
            if reason:
                txn.reason = (
                    f"{txn.reason} | Отклонено: {reason}"
                )
            await self.uow.flush()
            await self.uow.commit()

            return TransactionResponse.model_validate(txn)

    # ----------------------------------------------------------
    # Courier summary
    # ----------------------------------------------------------

    async def get_couriers_summary(
        self,
    ) -> CouriersSummaryResponse:
        """Сводка по всем курьерам: баланс, сборы, инкассация."""
        async with self.uow:
            courier_accounts = (
                await self.uow.accounts.get_courier_accounts_with_users()
            )

            couriers: list[CourierFinanceSummary] = []
            total_courier_cash = 0
            total_pending_deposit = 0

            for acc in courier_accounts:
                txn_repo = self.uow.transactions
                today_txns = await txn_repo.get_today_transactions_for_account(
                    account_id=acc.id,
                )

                today_collected = 0
                today_deposited = 0

                for t in today_txns:
                    # Входящие: CLIENT -> COURIER
                    if t.to_id == acc.id:
                        today_collected += t.amount
                    # Исходящие: COURIER -> CASH
                    if t.from_id == acc.id:
                        today_deposited += t.amount

                pending_deposit = acc.balance

                courier_name = (
                    acc.user.username if acc.user else "Неизвестный курьер"
                )

                couriers.append(
                    CourierFinanceSummary(
                        courier_id=acc.user_id,
                        courier_name=courier_name,
                        account_id=acc.id,
                        cash_balance=acc.balance,
                        today_collected=today_collected,
                        today_deposited=today_deposited,
                        pending_deposit=pending_deposit,
                    ),
                )

                if acc.balance > 0:
                    total_courier_cash += acc.balance
                    total_pending_deposit += pending_deposit

            return CouriersSummaryResponse(
                couriers=couriers,
                total_courier_cash=total_courier_cash,
                total_pending_deposit=total_pending_deposit,
            )

    # ----------------------------------------------------------
    # Client debts
    # ----------------------------------------------------------

    async def get_client_debts(
        self,
        min_debt: int = 0,
        skip: int = 0,
        limit: int = 50,
    ) -> ClientsDebtsResponse:
        """Клиенты с положительным балансом (долгом)."""
        async with self.uow:
            total_debt = await self.uow.accounts.get_total_client_debt()

            (
                debtors_count,
                debtor_accounts,
            ) = await self.uow.accounts.get_client_debtors(
                min_debt=min_debt,
                skip=skip,
                limit=limit,
            )

            clients: list[ClientDebt] = []
            for acc in debtor_accounts:
                user = acc.user
                user_name = user.username if user else "Неизвестный клиент"
                user_role = user.role.value if user else "unknown"
                phone = user.phone if user else None

                # Ищем последний платёж (исходящая транзакция
                # со счёта клиента, COMPLETED)
                last_payment_date = await self._get_last_payment_date(acc.id)

                clients.append(
                    ClientDebt(
                        client_id=acc.user_id,
                        client_name=user_name,
                        role=user_role,
                        phone=phone,
                        account_id=acc.id,
                        balance=acc.balance,
                        last_payment_date=last_payment_date,
                    ),
                )

            return ClientsDebtsResponse(
                total_debt=total_debt,
                debtors_count=debtors_count,
                clients=clients,
            )

    async def _get_last_payment_date(
        self,
        account_id: uuid.UUID,
    ) -> datetime | None:
        """Дата последнего исходящего COMPLETED-платежа."""
        from sqlalchemy import select

        from src.modules.finances.models import (
            Transaction as TxnModel,
        )

        q = (
            select(TxnModel.created_at)
            .where(
                TxnModel.from_id == account_id,
                TxnModel.status == TransactionStatus.COMPLETED,
                TxnModel.is_active.is_(True),
            )
            .order_by(TxnModel.created_at.desc())
            .limit(1)
        )
        result = await self.uow.session.execute(q)
        row = result.scalar_one_or_none()
        return row

    # ----------------------------------------------------------
    # Cashbox
    # ----------------------------------------------------------

    async def accept_payment(
        self,
        client_id: uuid.UUID,
        amount: int,
        payment_method: str,
        reason: str,
        accepted_by_id: uuid.UUID,
        order_id: uuid.UUID | None = None,
    ) -> TransactionResponse:
        """Касса: приём оплаты от клиента.

        cash: CLIENT -> CASH (COMPLETED)
        card: CLIENT -> CARD (PENDING)
        """
        async with self.uow:
            client_account = (
                await self.uow.accounts.get_client_account(
                    client_id,
                )
            )
            if not client_account:
                raise AccountNotFoundError(
                    message=(
                        "Лицевой счет клиента"
                        f" не найден: {client_id}"
                    ),
                )

            if payment_method == "cash":
                target = (
                    await self.uow.accounts
                    .get_system_cash_account()
                )
                status = TransactionStatus.COMPLETED
            else:
                target = (
                    await self.uow.accounts
                    .get_system_card_account()
                )
                status = TransactionStatus.PENDING

            if not target:
                raise AccountNotFoundError(
                    message=(
                        "Системный счёт для метода"
                        " оплаты "
                        f"'{payment_method}'"
                        " не найден."
                    ),
                )

            txn_data = {
                "from_id": client_account.id,
                "to_id": target.id,
                "amount": amount,
                "reason": reason,
                "order_id": order_id,
                "status": status,
                "verified_by_id": (
                    accepted_by_id
                    if status == TransactionStatus.COMPLETED
                    else None
                ),
            }

            txn = await self.uow.transactions.add(txn_data)
            await self.uow.commit()

            return TransactionResponse.model_validate(txn)
