# src/api/v1/backoffice/finances.py
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.finances.dependencies import get_billing_service
from src.modules.finances.enums import AccountType, TransactionStatus
from src.modules.finances.schemas import TransactionCreate
from src.modules.finances.services import BillingService

finances_router = APIRouter()


# ---------------------------------------------------------------
# 1. Dashboard
# ---------------------------------------------------------------


@finances_router.get("/dashboard")
async def get_dashboard(
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[
        BillingService, Depends(get_billing_service)
    ],
):
    """Финансовый дашборд: системные счета, итоги, pending."""
    return await billing_service.get_dashboard()


# ---------------------------------------------------------------
# 2. Accounts list
# ---------------------------------------------------------------


@finances_router.get("/accounts")
async def get_accounts(
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[
        BillingService, Depends(get_billing_service)
    ],
    type: Annotated[
        AccountType | None,
        Query(description="Фильтр по типу счёта"),
    ] = None,
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            description="Поиск по названию или имени владельца",
        ),
    ] = None,
    has_debt: Annotated[
        bool | None,
        Query(description="Только должники (balance > 0)"),
    ] = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
):
    """Список счетов с фильтрацией и пагинацией."""
    skip = (page - 1) * size
    return await billing_service.get_accounts(
        skip=skip,
        limit=size,
        type=type,
        search=search,
        has_debt=has_debt,
    )


# ---------------------------------------------------------------
# 3. Account detail
# ---------------------------------------------------------------


@finances_router.get("/accounts/{account_id}")
async def get_account_detail(
    account_id: Annotated[uuid.UUID, Path()],
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[
        BillingService, Depends(get_billing_service)
    ],
):
    """Детальная информация по счёту с последними транзакциями."""
    return await billing_service.get_account_detail(
        account_id=account_id,
    )


# ---------------------------------------------------------------
# 4. Account statement
# ---------------------------------------------------------------


@finances_router.get("/accounts/{account_id}/statement")
async def get_account_statement(
    account_id: Annotated[uuid.UUID, Path()],
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[
        BillingService, Depends(get_billing_service)
    ],
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
    billing_service: Annotated[
        BillingService, Depends(get_billing_service)
    ],
    status: Annotated[
        TransactionStatus | None,
        Query(description="Фильтр по статусу"),
    ] = None,
    account_id: Annotated[
        uuid.UUID | None,
        Query(description="Транзакции от/к этому счёту"),
    ] = None,
    order_id: Annotated[
        uuid.UUID | None,
        Query(description="Транзакции по заказу"),
    ] = None,
    date_from: Annotated[
        datetime | None,
        Query(description="Начало периода"),
    ] = None,
    date_to: Annotated[
        datetime | None,
        Query(description="Конец периода"),
    ] = None,
    min_amount: Annotated[
        int | None,
        Query(ge=0, description="Минимальная сумма"),
    ] = None,
    max_amount: Annotated[
        int | None,
        Query(ge=0, description="Максимальная сумма"),
    ] = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
):
    """Список транзакций с фильтрацией и пагинацией."""
    skip = (page - 1) * size
    return await billing_service.get_transactions(
        skip=skip,
        limit=size,
        status=status,
        account_id=account_id,
        order_id=order_id,
        date_from=date_from,
        date_to=date_to,
        min_amount=min_amount,
        max_amount=max_amount,
    )


# ---------------------------------------------------------------
# 6. Create manual transaction
# ---------------------------------------------------------------


@finances_router.post("/transactions", status_code=201)
async def create_transaction(
    dto: TransactionCreate,
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_WRITE]),
    ],
    billing_service: Annotated[
        BillingService, Depends(get_billing_service)
    ],
):
    """Создание ручной проводки (инкассация, возврат и т.д.)."""
    return await billing_service.create_transaction(
        dto=dto,
        created_by_id=current_user.id,
    )


# ---------------------------------------------------------------
# 7. Verify transaction
# ---------------------------------------------------------------


@finances_router.patch("/transactions/{transaction_id}/verify")
async def verify_transaction(
    transaction_id: Annotated[uuid.UUID, Path()],
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_WRITE]),
    ],
    billing_service: Annotated[
        BillingService, Depends(get_billing_service)
    ],
):
    """Верификация PENDING-транзакции (бухгалтер)."""
    return await billing_service.verify_transaction(
        transaction_id=transaction_id,
        verified_by_id=current_user.id,
    )


# ---------------------------------------------------------------
# 8. Reject transaction
# ---------------------------------------------------------------


@finances_router.patch("/transactions/{transaction_id}/reject")
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
    billing_service: Annotated[
        BillingService, Depends(get_billing_service)
    ],
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


@finances_router.get("/couriers/summary")
async def get_couriers_summary(
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[
        BillingService, Depends(get_billing_service)
    ],
):
    """Сводка по кассам курьеров: баланс, сборы, инкассация."""
    return await billing_service.get_couriers_summary()


# ---------------------------------------------------------------
# 10. Client debts
# ---------------------------------------------------------------


@finances_router.get("/clients/debts")
async def get_client_debts(
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.FINANCES_READ]),
    ],
    billing_service: Annotated[
        BillingService, Depends(get_billing_service)
    ],
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


@finances_router.post("/cashbox/accept-payment", status_code=201)
async def accept_payment(
    client_id: Annotated[
        uuid.UUID, Body(description="ID клиента")
    ],
    amount: Annotated[
        int, Body(gt=0, description="Сумма оплаты")
    ],
    payment_method: Annotated[
        str,
        Body(description="Способ оплаты: cash / card"),
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
    billing_service: Annotated[
        BillingService, Depends(get_billing_service)
    ],
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
