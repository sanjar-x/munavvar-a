# src/modules/orders/dependencies.py
from typing import Annotated

from fastapi import Depends

from src.infrastructure.database.session import async_session_maker
from src.modules.catalog.dependencies import get_catalog_service
from src.modules.catalog.public import CatalogService
from src.modules.orders.services import BaseOrderService
from src.modules.orders.uow import BaseOrderUnitOfWork
from src.modules.users.dependencies import get_user_service
from src.modules.users.services import UserService


def get_base_order_uow() -> BaseOrderUnitOfWork:
    """
    Фабрика UoW для домена заказов.
    Просто возвращает неинициализированный объект.
    Сессия БД будет открыта внутри сервиса через `async with self.uow`.
    """
    return BaseOrderUnitOfWork(session_factory=async_session_maker)


def get_base_order_service(
    uow: Annotated[
        BaseOrderUnitOfWork, Depends(dependency=get_base_order_uow)
    ],
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> BaseOrderService:
    """
    Провайдер сервиса заказов.
    Готов к внедрению в роутеры слоя API (например, в backoffice/orders.py).
    """

    return BaseOrderService(
        uow=uow,
        catalog_service=catalog_service,
        user_service=user_service,
    )
