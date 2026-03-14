from typing import Annotated

from fastapi import Depends

from src.application.courier.service import CourierService
from src.application.courier.uow import CourierUnitOfWork
from src.infrastructure.database.session import async_session_maker


def get_courier_uow() -> CourierUnitOfWork:
    return CourierUnitOfWork(session_factory=async_session_maker)


def get_courier_service(
    uow: Annotated[CourierUnitOfWork, Depends(get_courier_uow)],
) -> CourierService:
    return CourierService(uow=uow)
