# src/api/v1/client/finances.py
from typing import Annotated

from fastapi import APIRouter, Depends, Security

from src.core.exceptions import NotFoundError
from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.finances.dependencies import get_finances_uow
from src.modules.finances.schemas import (
    ClientBalanceResponse,
    ClientPaymentEntry,
)
from src.modules.finances.uow import IFinancesUnitOfWork

finances_router = APIRouter()


@finances_router.get(
    "/my-balance",
    response_model=ClientBalanceResponse,
    summary="Баланс клиента и последние платежи",
)
async def get_my_balance(
    client: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.ORDERS_READ],
        ),
    ],
    uow: Annotated[
        IFinancesUnitOfWork,
        Depends(get_finances_uow),
    ],
):
    """Возвращает текущий баланс клиента
    и список последних 20 платежей.
    """
    async with uow:
        account = await uow.accounts.get_client_account(
            client_id=client.id,
        )
        if not account:
            raise NotFoundError(
                message="Лицевой счет клиента не найден.",
                error_code="CLIENT_ACCOUNT_NOT_FOUND",
            )

        txns = await uow.transactions.get_recent_for_account(
            account_id=account.id,
            limit=20,
        )

    payments: list[ClientPaymentEntry] = [
        ClientPaymentEntry(
            amount=txn.amount,
            status=txn.status,
            reason=txn.reason,
            created_at=txn.created_at,
        )
        for txn in txns
    ]

    return ClientBalanceResponse(
        account_id=account.id,
        balance=account.balance,
        recent_payments=payments,
    )
