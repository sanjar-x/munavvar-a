# src/modules/finances/schemas.py
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.modules.finances.enums import AccountType, TransactionStatus


class AccountBase(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        title="Название счета",
        examples=[
            "Личный счет Клиента",
            "Касса Курьера Ивана",
            "Основной Банковский Счет",
        ],
    )
    type: AccountType = Field(
        ...,
        title="Тип счета",
        description="Определяет системное назначение счета",
    )


class AccountCreate(AccountBase):
    """Создание нового счета.
    Обрати внимание: поля `balance` здесь НЕТ!
    Все новые счета рождаются с балансом 0.
    """

    user_id: uuid.UUID = Field(
        ...,
        title="Владелец счета (Пользователь или Система)",
    )


class AccountUpdate(BaseModel):
    """Единственное, что можно изменить у существующего счета
    — это его название.
    Менять владельца или тип счета после создания строго
    запрещено аудитом.
    """

    name: str = Field(..., min_length=2, max_length=255)


class AccountResponse(AccountBase):
    """Модель ответа для фронтенда и админки."""

    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str | None = None
    balance: int = Field(
        title="Текущий баланс",
        description=(
            "В сумах (UZS), целое число. Может быть отрицательным (долг)."
        ),
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountShort(BaseModel):
    """Краткая информация о счёте (для вложения в транзакции)."""

    id: uuid.UUID
    name: str
    type: AccountType
    user_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


# =====================================================================
# 2. ТРАНЗАКЦИИ (TRANSACTIONS)
# =====================================================================


class TransactionCreate(BaseModel):
    """Схема для ручных проводок (Например: Бухгалтер принимает
    наличные от курьера).
    Для заказов (Checkout) эта схема не используется, так как
    UseCase будет генерировать проводки автоматически внутри
    Python-кода.
    """

    from_id: uuid.UUID = Field(
        ...,
        title="Счет списания (Дебет)",
        description="Откуда уходят деньги",
    )
    to_id: uuid.UUID = Field(
        ...,
        title="Счет зачисления (Кредит)",
        description="Куда приходят деньги",
    )
    amount: int = Field(
        ...,
        gt=0,
        title="Сумма перевода",
        examples=[150000],
    )
    reason: str = Field(
        ...,
        min_length=3,
        max_length=255,
        title="Основание платежа",
        examples=[
            "Сдача выручки курьером",
            "Пополнение баланса через Payme",
        ],
    )

    order_id: uuid.UUID | None = Field(default=None)


class TransactionResponse(BaseModel):
    """Ответ для мутационных операций (create/verify/reject).

    Содержит все поля, необходимые фронтенду для отображения
    транзакции без дополнительного запроса.
    """

    id: uuid.UUID
    from_id: uuid.UUID
    to_id: uuid.UUID
    from_account: AccountShort | None = None
    to_account: AccountShort | None = None
    order_id: uuid.UUID | None
    amount: int
    status: TransactionStatus
    reason: str
    verified_by_id: uuid.UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =====================================================================
# 3. ДАШБОРД (DASHBOARD)
# =====================================================================


class SystemAccountSummary(BaseModel):
    id: uuid.UUID
    balance: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class DashboardTotals(BaseModel):
    total_revenue: int
    total_cash_in_hand: int
    total_card_pending: int
    total_client_debt: int
    total_courier_cash: int
    total_b2b_settled_debt: int = 0


class FinanceDashboard(BaseModel):
    system_accounts: dict[str, SystemAccountSummary]
    totals: DashboardTotals
    pending_transactions_count: int


# =====================================================================
# 4. ОБОГАЩЁННЫЕ ТРАНЗАКЦИИ (ENRICHED TRANSACTIONS)
# =====================================================================


class TransactionDetail(BaseModel):
    id: uuid.UUID
    from_account: AccountShort
    to_account: AccountShort
    amount: int
    status: TransactionStatus
    reason: str
    order_id: uuid.UUID | None
    order_short_id: str | None = None
    verified_by_id: uuid.UUID | None
    verified_by_name: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =====================================================================
# 5. ВЫПИСКА (STATEMENT)
# =====================================================================


class StatementPeriod(BaseModel):
    date_from: date
    date_to: date
    opening_balance: int
    closing_balance: int
    total_incoming: int
    total_outgoing: int


class StatementEntry(BaseModel):
    id: uuid.UUID
    direction: str  # "incoming" or "outgoing"
    counterparty: AccountShort
    amount: int
    running_balance: int
    status: TransactionStatus
    reason: str
    order_id: uuid.UUID | None
    created_at: datetime


class AccountStatement(BaseModel):
    account: AccountShort
    period: StatementPeriod
    transactions: list[StatementEntry]


# =====================================================================
# 6. ДЕТАЛЬНЫЙ СЧЁТ (ACCOUNT DETAIL)
# =====================================================================


class AccountDetail(AccountResponse):
    recent_transactions: list[TransactionDetail] = []


# =====================================================================
# 7. СВОДКА ПО КУРЬЕРАМ (COURIER SUMMARY)
# =====================================================================


class CourierFinanceSummary(BaseModel):
    courier_id: uuid.UUID
    courier_name: str
    account_id: uuid.UUID
    cash_balance: int
    today_collected: int
    today_deposited: int
    pending_deposit: int


class CouriersSummaryResponse(BaseModel):
    couriers: list[CourierFinanceSummary]
    total_courier_cash: int
    total_pending_deposit: int


# =====================================================================
# 8. ДОЛГИ КЛИЕНТОВ (CLIENT DEBTS)
# =====================================================================


class ClientDebt(BaseModel):
    client_id: uuid.UUID
    client_name: str
    role: str
    phone: str | None
    account_id: uuid.UUID
    balance: int
    last_payment_date: datetime | None


class ClientsDebtsResponse(BaseModel):
    total_debt: int
    debtors_count: int
    clients: list[ClientDebt]


# =====================================================================
# 9B. B2B ДЕБИТОРКА (B2B CONTRACT DEBTS)
# =====================================================================


class B2BContractDebt(BaseModel):
    client_id: uuid.UUID
    client_name: str
    contract_id: uuid.UUID
    contract_number: str
    account_balance: int
    due_date_status: str  # "ok" | "overdue"


class B2BContractDebtsResponse(BaseModel):
    items: list[B2BContractDebt]
    total_debt: int


# =====================================================================
# 10. КАССА (CASHBOX)
# =====================================================================


class AcceptPaymentRequest(BaseModel):
    client_id: uuid.UUID
    amount: int = Field(gt=0)
    payment_method: str = Field(pattern="^(cash|card|bank)$")
    reason: str = Field(min_length=3, max_length=255)
    order_id: uuid.UUID | None = None


# =====================================================================
# 10. ФИЛЬТРЫ (FILTERS)
# =====================================================================


DatePreset = Literal[
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
]
TransactionDirection = Literal["incoming", "outgoing", "internal"]
SortOrder = Literal["asc", "desc"]


class TransactionFilter(BaseModel):
    """Фильтры для `GET /backoffice/finances/transactions`.

    Использовать напрямую в сервисе/репозитории. Сбор из query-параметров
    — в отдельной dependency (`build_transaction_filter`).
    """

    model_config = ConfigDict(extra="ignore")

    q: str | None = None

    status_in: list[TransactionStatus] | None = None
    direction: TransactionDirection | None = None

    account_id: uuid.UUID | None = None
    from_account_id: uuid.UUID | None = None
    to_account_id: uuid.UUID | None = None
    from_account_type_in: list[AccountType] | None = None
    to_account_type_in: list[AccountType] | None = None

    order_id: uuid.UUID | None = None
    order_status_in: list[str] | None = None
    order_payment_method_in: list[str] | None = None
    order_sale_type_in: list[str] | None = None
    has_order: bool | None = None

    contract_id: uuid.UUID | None = None
    contract_number: str | None = None

    client_id: uuid.UUID | None = None
    courier_id: uuid.UUID | None = None
    user_role_in: list[str] | None = None

    verified_by_id: uuid.UUID | None = None
    verified: bool | None = None

    reason_search: str | None = None

    amount_eq: int | None = None
    amount_from: int | None = None
    amount_to: int | None = None

    date_preset: DatePreset | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    sort: Literal["created_at"] = "created_at"
    order: SortOrder = "desc"


class AccountFilter(BaseModel):
    """Фильтры для `GET /backoffice/finances/accounts`."""

    model_config = ConfigDict(extra="ignore")

    q: str | None = None

    type_in: list[AccountType] | None = None
    user_id: uuid.UUID | None = None
    user_role_in: list[str] | None = None

    balance_from: int | None = None
    balance_to: int | None = None
    is_in_credit: bool | None = None
    zero_balance: bool | None = None
    has_debt: bool | None = None  # legacy alias

    created_from: datetime | None = None
    created_to: datetime | None = None


class PaginationParams(BaseModel):
    page: int = 1
    size: int = 50


class OffsetPaginationMeta(BaseModel):
    mode: Literal["offset"] = "offset"
    page: int
    size: int
    total_count: int
    total_pages: int


class TransactionSummary(BaseModel):
    sum_amount: int
    count_by_status: dict[str, int]


class AccountSummary(BaseModel):
    sum_balance: int
    count_by_type: dict[str, int]


# =====================================================================
# 11. SELF-SERVICE: КУРЬЕР / КЛИЕНТ (COURIER / CLIENT BALANCE)
# =====================================================================


class CourierTransactionEntry(BaseModel):
    direction: str  # "incoming" or "outgoing"
    amount: int
    reason: str
    order_id: uuid.UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CourierBalanceResponse(BaseModel):
    account_id: uuid.UUID
    balance: int
    today_collected: int
    today_deposited: int
    transactions_today: list[CourierTransactionEntry]


class ClientPaymentEntry(BaseModel):
    amount: int
    status: TransactionStatus
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientBalanceResponse(BaseModel):
    account_id: uuid.UUID
    balance: int
    recent_payments: list[ClientPaymentEntry]
