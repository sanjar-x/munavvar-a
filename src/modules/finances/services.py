# src/modules/finances/services.py
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from src.modules.finances.enums import (
    AccountType,
    TransactionStatus,
)
from src.modules.finances.exceptions import (
    AccountNotFoundError,
    AmountConflictError,
    AmountRangeInvalidError,
    DatePresetConflictError,
    DateRangeInvalidError,
    InvalidTransactionStatusError,
    PaginationTooDeepError,
    SelfTransferError,
    TransactionNotFoundError,
)
from src.modules.finances.schemas import (
    AccountDetail,
    AccountFilter,
    AccountResponse,
    AccountShort,
    AccountStatement,
    B2BContractDebt,
    B2BContractDebtsResponse,
    ClientDebt,
    ClientsDebtsResponse,
    CourierFinanceSummary,
    CouriersSummaryResponse,
    DashboardTotals,
    FinanceDashboard,
    OffsetPaginationMeta,
    StatementEntry,
    StatementPeriod,
    SystemAccountSummary,
    TransactionCreate,
    TransactionDetail,
    TransactionFilter,
    TransactionResponse,
)
from src.modules.finances.uow import FinancesUnitOfWork

MAX_PAGE_DEPTH = 10_000


def _check_pagination(page: int, size: int) -> None:
    if page * size > MAX_PAGE_DEPTH:
        raise PaginationTooDeepError(page=page, size=size)


def _total_pages(total: int, size: int) -> int:
    if size <= 0:
        return 0
    return (total + size - 1) // size


def _validate_transaction_filter(f: TransactionFilter) -> None:
    if f.amount_eq is not None and (
        f.amount_from is not None or f.amount_to is not None
    ):
        raise AmountConflictError()
    if (
        f.amount_from is not None
        and f.amount_to is not None
        and f.amount_from > f.amount_to
    ):
        raise AmountRangeInvalidError()
    if f.date_preset is not None and (
        f.date_from is not None or f.date_to is not None
    ):
        raise DatePresetConflictError()
    if (
        f.date_from is not None
        and f.date_to is not None
        and f.date_from > f.date_to
    ):
        raise DateRangeInvalidError()


def _account_short(acc) -> AccountShort:
    """Построить AccountShort из ORM Account с подгруженным user."""
    data = AccountShort.model_validate(acc)
    try:
        data.user_name = acc.user.username if acc.user else None
    except Exception:
        data.user_name = None
    return data


def _build_transaction_detail(t) -> TransactionDetail:
    """Обогатить TransactionDetail связанными данными (from/to/verified_by)."""
    verified_by_name: str | None = None
    try:
        if t.verified_by is not None:
            verified_by_name = t.verified_by.username
    except Exception:
        verified_by_name = None

    order_short_id: str | None = None
    if t.order_id is not None:
        order_short_id = str(t.order_id)[-8:]

    return TransactionDetail(
        id=t.id,
        from_account=_account_short(t.from_account),
        to_account=_account_short(t.to_account),
        amount=t.amount,
        status=t.status,
        reason=t.reason,
        order_id=t.order_id,
        order_short_id=order_short_id,
        verified_by_id=t.verified_by_id,
        verified_by_name=verified_by_name,
        created_at=t.created_at,
    )


def _resolve_date_preset(f: TransactionFilter) -> TransactionFilter:
    """Развернуть `date_preset` в конкретные `date_from` / `date_to`.

    Возвращает новый объект фильтра (неизменяющая операция).
    Все границы считаются в TZ `Asia/Tashkent`.
    """
    if f.date_preset is None:
        return f
    try:
        from zoneinfo import ZoneInfo
    except ImportError:  # pragma: no cover
        return f

    tz = ZoneInfo("Asia/Tashkent")
    now_local = datetime.now(tz)
    today = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    start_local: datetime
    end_local: datetime
    preset = f.date_preset
    if preset == "today":
        start_local = today
        end_local = today + timedelta(days=1)
    elif preset == "yesterday":
        start_local = today - timedelta(days=1)
        end_local = today
    elif preset == "this_week":
        start_local = today - timedelta(days=today.weekday())
        end_local = start_local + timedelta(days=7)
    elif preset == "last_week":
        this_monday = today - timedelta(days=today.weekday())
        start_local = this_monday - timedelta(days=7)
        end_local = this_monday
    elif preset == "this_month":
        start_local = today.replace(day=1)
        if start_local.month == 12:
            end_local = start_local.replace(year=start_local.year + 1, month=1)
        else:
            end_local = start_local.replace(month=start_local.month + 1)
    elif preset == "last_month":
        first_this = today.replace(day=1)
        if first_this.month == 1:
            start_local = first_this.replace(
                year=first_this.year - 1, month=12
            )
        else:
            start_local = first_this.replace(month=first_this.month - 1)
        end_local = first_this
    else:
        return f

    return f.model_copy(
        update={
            "date_preset": None,
            "date_from": start_local.astimezone(UTC),
            "date_to": end_local.astimezone(UTC),
        }
    )


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
                **await self._get_b2b_totals(),
            )

            return FinanceDashboard(
                system_accounts=accounts_map,
                totals=totals,
                pending_transactions_count=pending_count,
            )

    async def _get_b2b_totals(self) -> dict:
        """Возвращает B2B-агрегаты для DashboardTotals.

        Выполняется внутри уже открытого UoW-контекста через
        raw SQL, чтобы не импортировать модели contracts в finances.
        """
        sql = text(
            """
            SELECT
                COALESCE(SUM(a.balance), 0) AS settled_debt
            FROM contracts c
            JOIN accounts a ON a.user_id = c.client_id
                AND a.type = 'client'
            WHERE c.status = 'active'
              AND c.is_active = TRUE
            """
        )
        row = (await self.uow.session.execute(sql)).one()
        return {
            "total_b2b_settled_debt": int(row.settled_debt),
        }

    # ----------------------------------------------------------
    # B2B Дебиторка
    # ----------------------------------------------------------

    async def get_b2b_contract_debts(self) -> B2BContractDebtsResponse:
        """Список B2B-долгов по активным договорам.

        JOIN: contracts → users → accounts (CLIENT).
        """
        async with self.uow:
            sql = text(
                """
                SELECT
                    u.id                AS client_id,
                    u.username          AS client_name,
                    c.id                AS contract_id,
                    c.number            AS contract_number,
                    a.balance           AS account_balance,
                    c.payment_due_days
                FROM contracts c
                JOIN users u ON u.id = c.client_id
                JOIN accounts a ON a.user_id = c.client_id
                    AND a.type = 'client'
                WHERE c.status = 'active'
                  AND c.is_active = TRUE
                ORDER BY a.balance DESC
                """
            )
            rows = (await self.uow.session.execute(sql)).all()

            items = []
            total_debt = 0
            for r in rows:
                balance = int(r.account_balance)
                total_debt += balance
                due_date_status = (
                    "overdue"
                    if balance > 0 and int(r.payment_due_days) == 0
                    else "ok"
                )
                items.append(
                    B2BContractDebt(
                        client_id=r.client_id,
                        client_name=r.client_name,
                        contract_id=r.contract_id,
                        contract_number=r.contract_number,
                        account_balance=balance,
                        due_date_status=due_date_status,
                    )
                )
            return B2BContractDebtsResponse(
                items=items,
                total_debt=total_debt,
            )

    # ----------------------------------------------------------
    # Accounts
    # ----------------------------------------------------------

    async def get_accounts(
        self,
        filters: AccountFilter,
        page: int,
        size: int,
    ) -> dict:
        """Пагинированный список счетов с фильтрами + summary.

        Возвращает dict с ключами:
          - `items`       — list[AccountResponse]
          - `pagination`  — OffsetPaginationMeta
          - `summary`     — AccountSummary
          - `accounts`    — alias для items (deprecated)
          - `total_count` — alias для pagination.total_count (deprecated)
        """
        _check_pagination(page, size)
        skip = (page - 1) * size
        async with self.uow:
            total, items = await self.uow.accounts.get_accounts_with_filters(
                filters=filters,
                skip=skip,
                limit=size,
            )
            summary = await self.uow.accounts.get_accounts_summary(
                filters=filters,
            )
            accounts: list[AccountResponse] = []
            for acc in items:
                resp = AccountResponse.model_validate(acc)
                resp.user_name = acc.user.username if acc.user else None
                accounts.append(resp)

            pagination = OffsetPaginationMeta(
                page=page,
                size=size,
                total_count=total,
                total_pages=_total_pages(total, size),
            )
            return {
                "items": accounts,
                "pagination": pagination,
                "summary": summary,
                # backward-compat
                "accounts": accounts,
                "total_count": total,
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

            now = datetime.now(tz=UTC)
            if date_from is None:
                date_from = now.replace(
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            if date_to is None:
                date_to = now

            dt_from = date_from.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            dt_to = date_to.replace(
                hour=23,
                minute=59,
                second=59,
                microsecond=0,
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
        filters: TransactionFilter,
        page: int,
        size: int,
    ) -> dict:
        """Пагинированный список транзакций + summary по тем же фильтрам."""
        _validate_transaction_filter(filters)
        filters = _resolve_date_preset(filters)
        _check_pagination(page, size)
        skip = (page - 1) * size
        async with self.uow:
            (
                total,
                items,
            ) = await self.uow.transactions.get_transactions_with_filters(
                filters=filters,
                skip=skip,
                limit=size,
            )
            summary = await self.uow.transactions.get_transactions_summary(
                filters=filters,
            )
            transactions = [_build_transaction_detail(t) for t in items]
            pagination = OffsetPaginationMeta(
                page=page,
                size=size,
                total_count=total,
                total_pages=_total_pages(total, size),
            )
            return {
                "items": transactions,
                "pagination": pagination,
                "summary": summary,
                # backward-compat
                "transactions": transactions,
                "total_count": total,
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
            from_account = await self.uow.accounts.get(
                dto.from_id,
            )
            if not from_account:
                raise AccountNotFoundError(
                    account_id=dto.from_id,
                    message=(f"Счет списания не найден: {dto.from_id}"),
                )

            to_account = await self.uow.accounts.get(
                dto.to_id,
            )
            if not to_account:
                raise AccountNotFoundError(
                    account_id=dto.to_id,
                    message=(f"Счет зачисления не найден: {dto.to_id}"),
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

            return await self._load_transaction_response(
                txn.id,
            )

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

            return await self._load_transaction_response(
                transaction_id,
            )

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
                txn.reason = f"{txn.reason} | Отклонено: {reason}"
            await self.uow.flush()
            await self.uow.commit()

            return await self._load_transaction_response(
                transaction_id,
            )

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
        min_debt: int | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> ClientsDebtsResponse:
        """Клиенты с положительным балансом (долгом)."""
        effective_min_debt = min_debt or 0
        async with self.uow:
            total_debt = await self.uow.accounts.get_total_client_debt()

            (
                debtors_count,
                debtor_accounts,
            ) = await self.uow.accounts.get_client_debtors(
                min_debt=effective_min_debt,
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

    async def _load_transaction_response(
        self,
        transaction_id: uuid.UUID,
    ) -> TransactionResponse:
        """Перезагрузить транзакцию с from/to_account после commit.

        После commit() SQLAlchemy помечает атрибуты ORM-объекта
        как expired. Повторная загрузка с eager-load гарантирует
        корректную сериализацию.
        """
        txn = await self.uow.transactions.get_with_accounts(
            transaction_id,
        )
        if not txn:
            raise TransactionNotFoundError(
                transaction_id=transaction_id,
            )
        return TransactionResponse(
            id=txn.id,
            from_id=txn.from_id,
            to_id=txn.to_id,
            from_account=AccountShort.model_validate(
                txn.from_account,
            ),
            to_account=AccountShort.model_validate(
                txn.to_account,
            ),
            order_id=txn.order_id,
            amount=txn.amount,
            status=txn.status,
            reason=txn.reason,
            verified_by_id=txn.verified_by_id,
            created_at=txn.created_at,
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
            client_account = await self.uow.accounts.get_client_account(
                client_id,
            )
            if not client_account:
                raise AccountNotFoundError(
                    message=(f"Лицевой счет клиента не найден: {client_id}"),
                )

            if payment_method == "cash":
                target = await self.uow.accounts.get_system_cash_account()
                status = TransactionStatus.COMPLETED
            elif payment_method == "card":
                target = await self.uow.accounts.get_system_card_account()
                status = TransactionStatus.PENDING
            else:  # bank
                target = await self.uow.accounts.get_system_bank_account()
                status = TransactionStatus.COMPLETED

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

            return await self._load_transaction_response(
                txn.id,
            )
