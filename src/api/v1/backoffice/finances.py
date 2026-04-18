# src/api/v1/backoffice/finances.py
import uuid
from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Body, Depends, Path, Query, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.finances.dependencies import get_billing_service
from src.modules.finances.enums import AccountType, TransactionStatus
from src.modules.finances.schemas import (
    AccountDetail,
    AccountFilter,
    AccountStatement,
    B2BContractDebtsResponse,
    ClientsDebtsResponse,
    CouriersSummaryResponse,
    DatePreset,
    FinanceDashboard,
    SortOrder,
    TransactionCreate,
    TransactionDirection,
    TransactionFilter,
    TransactionResponse,
)
from src.modules.finances.services import BillingService

finances_router = APIRouter()
logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------
# Dependency-builders (query params → Pydantic filter)
# ---------------------------------------------------------------


def build_account_filter(
    q: Annotated[
        str | None,
        Query(description="Поиск по названию/владельцу"),
    ] = None,
    type_in: Annotated[
        list[AccountType] | None,
        Query(description="Типы счётов"),
    ] = None,
    user_id: Annotated[uuid.UUID | None, Query()] = None,
    user_role_in: Annotated[list[str] | None, Query()] = None,
    balance_from: Annotated[int | None, Query()] = None,
    balance_to: Annotated[int | None, Query()] = None,
    is_in_credit: Annotated[bool | None, Query()] = None,
    zero_balance: Annotated[bool | None, Query()] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    # deprecated aliases
    type: Annotated[
        AccountType | None,
        Query(
            deprecated=True,
            description="[deprecated] используйте type_in",
        ),
    ] = None,
    search: Annotated[
        str | None,
        Query(
            deprecated=True,
            description="[deprecated] используйте q",
        ),
    ] = None,
    has_debt: Annotated[
        bool | None,
        Query(description="Только должники (balance > 0, CLIENT)"),
    ] = None,
) -> AccountFilter:
    """Собрать `AccountFilter` из query-параметров.

    Новые параметры приоритетнее, но `has_debt` оставлен как основной
    API-параметр.
    """
    effective_q = q if q is not None else search
    if q is not None and search is not None:
        logger.warning(
            "finances.accounts: both q and search provided, using q",
            has_q=True,
            has_search=True,
        )

    effective_type_in: list[AccountType] | None = type_in
    if not type_in and type is not None:
        effective_type_in = [type]
    elif type_in and type is not None:
        logger.warning(
            "finances.accounts: both type_in and type provided, using type_in",
        )

    return AccountFilter(
        q=effective_q,
        type_in=effective_type_in,
        user_id=user_id,
        user_role_in=user_role_in,
        balance_from=balance_from,
        balance_to=balance_to,
        is_in_credit=is_in_credit,
        zero_balance=zero_balance,
        has_debt=has_debt,
        created_from=created_from,
        created_to=created_to,
    )


def build_transaction_filter(
    q: Annotated[str | None, Query(description="Free-text поиск")] = None,
    status_in: Annotated[
        list[TransactionStatus] | None,
        Query(description="Фильтр по статусам"),
    ] = None,
    direction: Annotated[TransactionDirection | None, Query()] = None,
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    from_account_id: Annotated[uuid.UUID | None, Query()] = None,
    to_account_id: Annotated[uuid.UUID | None, Query()] = None,
    from_account_type_in: Annotated[list[AccountType] | None, Query()] = None,
    to_account_type_in: Annotated[list[AccountType] | None, Query()] = None,
    order_id: Annotated[uuid.UUID | None, Query()] = None,
    order_status_in: Annotated[list[str] | None, Query()] = None,
    order_payment_method_in: Annotated[list[str] | None, Query()] = None,
    order_sale_type_in: Annotated[list[str] | None, Query()] = None,
    has_order: Annotated[bool | None, Query()] = None,
    contract_id: Annotated[uuid.UUID | None, Query()] = None,
    contract_number: Annotated[str | None, Query()] = None,
    client_id: Annotated[uuid.UUID | None, Query()] = None,
    courier_id: Annotated[uuid.UUID | None, Query()] = None,
    user_role_in: Annotated[list[str] | None, Query()] = None,
    verified_by_id: Annotated[uuid.UUID | None, Query()] = None,
    verified: Annotated[bool | None, Query()] = None,
    reason_search: Annotated[str | None, Query(min_length=2)] = None,
    amount_eq: Annotated[int | None, Query(ge=0)] = None,
    amount_from: Annotated[int | None, Query(ge=0)] = None,
    amount_to: Annotated[int | None, Query(ge=0)] = None,
    date_preset: Annotated[DatePreset | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    order: Annotated[SortOrder, Query()] = "desc",
    # deprecated aliases
    status: Annotated[
        TransactionStatus | None,
        Query(deprecated=True, description="[deprecated] status_in"),
    ] = None,
    min_amount: Annotated[
        int | None,
        Query(ge=0, deprecated=True, description="[deprecated] amount_from"),
    ] = None,
    max_amount: Annotated[
        int | None,
        Query(ge=0, deprecated=True, description="[deprecated] amount_to"),
    ] = None,
) -> TransactionFilter:
    """Собрать `TransactionFilter` из query-параметров.

    Deprecated aliases (`status`, `min_amount`, `max_amount`) применяются
    только если соответствующие новые параметры отсутствуют.
    """
    effective_status_in: list[TransactionStatus] | None = status_in
    if not status_in and status is not None:
        effective_status_in = [status]
    elif status_in and status is not None:
        logger.warning(
            "finances.transactions: both status_in and status provided",
        )

    effective_amount_from = (
        amount_from if amount_from is not None else min_amount
    )
    if amount_from is not None and min_amount is not None:
        logger.warning(
            "finances.transactions: both amount_from and min_amount provided",
        )

    effective_amount_to = amount_to if amount_to is not None else max_amount
    if amount_to is not None and max_amount is not None:
        logger.warning(
            "finances.transactions: both amount_to and max_amount provided",
        )

    return TransactionFilter(
        q=q,
        status_in=effective_status_in,
        direction=direction,
        account_id=account_id,
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        from_account_type_in=from_account_type_in,
        to_account_type_in=to_account_type_in,
        order_id=order_id,
        order_status_in=order_status_in,
        order_payment_method_in=order_payment_method_in,
        order_sale_type_in=order_sale_type_in,
        has_order=has_order,
        contract_id=contract_id,
        contract_number=contract_number,
        client_id=client_id,
        courier_id=courier_id,
        user_role_in=user_role_in,
        verified_by_id=verified_by_id,
        verified=verified,
        reason_search=reason_search,
        amount_eq=amount_eq,
        amount_from=effective_amount_from,
        amount_to=effective_amount_to,
        date_preset=date_preset,
        date_from=date_from,
        date_to=date_to,
        order=order,
    )


# ---------------------------------------------------------------
# 1. Dashboard
# ---------------------------------------------------------------


@finances_router.get("/dashboard", response_model=FinanceDashboard)
async def get_dashboard(
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
):
    """Финансовый дашборд: системные счета, итоги, pending."""
    return await billing_service.get_dashboard()


@finances_router.get(
    "/b2b-debts",
    response_model=B2BContractDebtsResponse,
    summary="Дебиторка B2B-клиентов по активным договорам",
)
async def get_b2b_debts(
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.CONTRACTS_READ]),
    ],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
):
    return await billing_service.get_b2b_contract_debts()


# ---------------------------------------------------------------
# 2. Accounts list
# ---------------------------------------------------------------


@finances_router.get("/accounts")
async def get_accounts(
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
    filters: Annotated[AccountFilter, Depends(build_account_filter)],
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
):
    """Список счетов с фильтрацией, поиском и пагинацией.

    Новые параметры: `q`, `type_in`, `user_role_in`, `balance_from/to`,
    `is_in_credit`, `zero_balance`, `created_from/to`.
    Deprecated: `type`, `search` (принимаются, но логируются).
    Ответ: `{items, pagination, summary, accounts (alias),
    total_count (legacy)}`.
    """
    return await billing_service.get_accounts(
        filters=filters,
        page=page,
        size=size,
    )


# ---------------------------------------------------------------
# 3. Account detail
# ---------------------------------------------------------------


@finances_router.get("/accounts/{account_id}", response_model=AccountDetail)
async def get_account_detail(
    account_id: Annotated[uuid.UUID, Path()],
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
):
    """Детальная информация по счёту с последними транзакциями."""
    return await billing_service.get_account_detail(
        account_id=account_id,
    )


# ---------------------------------------------------------------
# 4. Account statement
# ---------------------------------------------------------------


@finances_router.get(
    "/accounts/{account_id}/statement",
    response_model=AccountStatement,
)
async def get_account_statement(
    account_id: Annotated[uuid.UUID, Path()],
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
    date_from: Annotated[
        datetime | None,
        Query(description="Начало периода"),
    ] = None,
    date_to: Annotated[
        datetime | None,
        Query(description="Конец периода"),
    ] = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
):
    """Выписка по счёту за период."""
    skip = (page - 1) * size
    return await billing_service.get_account_statement(
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=size,
    )


# ---------------------------------------------------------------
# 5. Transactions list
# ---------------------------------------------------------------


@finances_router.get("/transactions")
async def get_transactions(
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
    filters: Annotated[TransactionFilter, Depends(build_transaction_filter)],
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
):
    """Список транзакций с расширенной фильтрацией, поиском и пагинацией.

    Новые параметры: `q`, `status_in`, `direction`, `from_account_id`,
    `to_account_id`, `from_account_type_in`, `to_account_type_in`,
    `order_status_in`, `order_payment_method_in`, `order_sale_type_in`,
    `has_order`, `contract_id`, `contract_number`, `client_id`,
    `courier_id`, `user_role_in`, `verified_by_id`, `verified`,
    `reason_search`, `amount_eq`, `amount_from`, `amount_to`,
    `date_preset`, `order`.
    Deprecated: `status`, `min_amount`, `max_amount`.
    Ответ: `{items, pagination, summary, transactions (alias),
    total_count (legacy)}`.
    """
    return await billing_service.get_transactions(
        filters=filters,
        page=page,
        size=size,
    )


# ---------------------------------------------------------------
# 6. Create manual transaction
# ---------------------------------------------------------------


@finances_router.post(
    "/transactions",
    status_code=201,
    response_model=TransactionResponse,
)
async def create_transaction(
    dto: TransactionCreate,
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_WRITE]),
    ],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
):
    """Создание ручной проводки (инкассация, возврат и т.д.)."""
    return await billing_service.create_transaction(
        dto=dto,
        created_by_id=current_user.id,
    )


# ---------------------------------------------------------------
# 7. Verify transaction
# ---------------------------------------------------------------


@finances_router.patch(
    "/transactions/{transaction_id}/verify",
    response_model=TransactionResponse,
)
async def verify_transaction(
    transaction_id: Annotated[uuid.UUID, Path()],
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_WRITE]),
    ],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
):
    """Верификация PENDING-транзакции (бухгалтер)."""
    return await billing_service.verify_transaction(
        transaction_id=transaction_id,
        verified_by_id=current_user.id,
    )


# ---------------------------------------------------------------
# 8. Reject transaction
# ---------------------------------------------------------------


@finances_router.patch(
    "/transactions/{transaction_id}/reject",
    response_model=TransactionResponse,
)
async def reject_transaction(
    transaction_id: Annotated[uuid.UUID, Path()],
    reason: Annotated[
        str,
        Body(
            min_length=3,
            max_length=255,
            embed=True,
            description="Причина отклонения",
        ),
    ],
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_WRITE]),
    ],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
):
    """Отклонение PENDING-транзакции с указанием причины."""
    return await billing_service.reject_transaction(
        transaction_id=transaction_id,
        verified_by_id=current_user.id,
        reason=reason,
    )


# ---------------------------------------------------------------
# 9. Couriers summary
# ---------------------------------------------------------------


@finances_router.get(
    "/couriers/summary",
    response_model=CouriersSummaryResponse,
)
async def get_couriers_summary(
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
):
    """Сводка по кассам курьеров: баланс, сборы, инкассация."""
    return await billing_service.get_couriers_summary()


# ---------------------------------------------------------------
# 10. Client debts
# ---------------------------------------------------------------


@finances_router.get(
    "/clients/debts",
    response_model=ClientsDebtsResponse,
)
async def get_client_debts(
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
    min_debt: Annotated[
        int | None,
        Query(ge=0, description="Минимальный долг"),
    ] = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
):
    """Список клиентов-должников."""
    skip = (page - 1) * size
    return await billing_service.get_client_debts(
        skip=skip,
        limit=size,
        min_debt=min_debt,
    )


# ---------------------------------------------------------------
# 11. Cashbox — accept payment
# ---------------------------------------------------------------


@finances_router.post(
    "/cashbox/accept-payment",
    status_code=201,
    response_model=TransactionResponse,
)
async def accept_payment(
    client_id: Annotated[uuid.UUID, Body(description="ID клиента")],
    amount: Annotated[int, Body(gt=0, description="Сумма оплаты")],
    payment_method: Annotated[
        str,
        Body(description="Способ оплаты: cash / card / bank"),
    ],
    reason: Annotated[
        str,
        Body(
            min_length=3,
            max_length=255,
            description="Основание платежа",
        ),
    ],
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.PAYMENTS_CREATE]),
    ],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
    order_id: Annotated[
        uuid.UUID | None,
        Body(description="ID заказа (опционально)"),
    ] = None,
):
    """Приём оплаты кассиром (наличные или карта)."""
    return await billing_service.accept_payment(
        client_id=client_id,
        amount=amount,
        payment_method=payment_method,
        reason=reason,
        order_id=order_id,
        accepted_by_id=current_user.id,
    )
