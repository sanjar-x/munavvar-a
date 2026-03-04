# src\application\order\dependencies.py
from typing import Annotated

from fastapi import Depends

from src.application.order.service import OrderService
from src.application.order.uow import (
    IOrderUnitOfWork,
    OrderUnitOfWork,
)
from src.infrastructure.database.session import async_session_maker


def get_order_uow() -> IOrderUnitOfWork:
    """Фабрика композитного UoW для доставки."""
    return OrderUnitOfWork(session_factory=async_session_maker)


def get_order_service(
    uow: Annotated[OrderUnitOfWork, Depends(get_order_uow)],
) -> OrderService:
    """Провайдер Оркестратора доставки."""
    return OrderService(uow=uow)
