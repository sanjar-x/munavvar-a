# src/modules/finances/dependencies.py
from typing import Annotated

from fastapi import Depends

from src.infrastructure.database.session import async_session_maker
from src.modules.finances.services import BillingService
from src.modules.finances.uow import FinancesUnitOfWork, IFinancesUnitOfWork


def get_finances_uow() -> IFinancesUnitOfWork:
    return FinancesUnitOfWork(session_factory=async_session_maker)


def get_billing_service(
    uow: Annotated[FinancesUnitOfWork, Depends(get_finances_uow)],
) -> BillingService:
    return BillingService(uow=uow)
