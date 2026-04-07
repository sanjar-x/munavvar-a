# src/api/v1/courier/finances.py
from typing import Annotated

from fastapi import APIRouter, Depends, Security

from src.core.exceptions import NotFoundError
from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_courier
from src.modules.finances.dependencies import get_finances_uow
from src.modules.finances.schemas import (
    CourierBalanceResponse,
    CourierTransactionEntry,
)
from src.modules.finances.uow import IFinancesUnitOfWork

finances_router = APIRouter()


@finances_router.get(
    "/my-balance",
    response_model=CourierBalanceResponse,
    summary="Касса курьера — баланс и операции за сегодня",
)
async def get_my_balance(
    courier: Annotated[
        User,
        Security(
            get_current_courier,
            scopes=[Scope.PAYMENTS_CREATE],
        ),
    ],
    uow: Annotated[
        IFinancesUnitOfWork,
        Depends(get_finances_uow),
    ],
):
    """Возвращает финансовую сводку курьера:
    текущий баланс, собранные и сданные за сегодня суммы,
    а также список операций за сегодня.
    """
    async with uow:
        account = await uow.accounts.get_courier_account(
            courier_id=courier.id,
        )
        if not account:
            raise NotFoundError(
                message="Счет курьера не найден.",
                error_code="COURIER_ACCOUNT_NOT_FOUND",
            )

        txns = await uow.transactions.get_today_transactions_for_account(
            account_id=account.id,
        )

    today_collected = 0
    today_deposited = 0
    entries: list[CourierTransactionEntry] = []

    for txn in txns:
        if txn.to_id == account.id:
            # Входящая: CLIENT -> COURIER (сбор оплаты)
            today_collected += txn.amount
            entries.append(
                CourierTransactionEntry(
                    direction="incoming",
                    amount=txn.amount,
                    reason=txn.reason,
                    order_id=txn.order_id,
                    created_at=txn.created_at,
                )
            )
        else:
            # Исходящая: COURIER -> CASH (сдача выручки)
            today_deposited += txn.amount
            entries.append(
                CourierTransactionEntry(
                    direction="outgoing",
                    amount=txn.amount,
                    reason=txn.reason,
                    order_id=txn.order_id,
                    created_at=txn.created_at,
                )
            )

    return CourierBalanceResponse(
        account_id=account.id,
        balance=account.balance,
        today_collected=today_collected,
        today_deposited=today_deposited,
        transactions_today=entries,
    )
