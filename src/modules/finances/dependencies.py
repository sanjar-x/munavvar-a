# src/modules/finances/dependencies.py
# src/modules/finances/dependencies.py
from typing import Annotated

from fastapi import Depends

from src.infrastructure.database.session import async_session_maker
from src.modules.finances.services import BillingService
from src.modules.finances.uow import FinancesUnitOfWork, IFinancesUnitOfWork
from src.modules.users.dependencies import get_user_service
from src.modules.users.services import UserService


def get_finances_uow() -> IFinancesUnitOfWork:
    """
    Fabrika (Factory) za UoW u domenu finansija.
    Vraća interfejs IFinancesUnitOfWork u skladu sa principom inverzije zavisnosti.
    """
    return FinancesUnitOfWork(session_factory=async_session_maker)


def get_billing_service(
    uow: Annotated[FinancesUnitOfWork, Depends(get_finances_uow)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> BillingService:
    return BillingService(uow=uow, user_service=user_service)
