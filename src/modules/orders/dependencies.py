# src/modules/orders/dependencies.py
from typing import Annotated

from fastapi import Depends

from src.infrastructure.database.session import async_session_maker
from src.modules.catalog.dependencies import get_catalog_service
from src.modules.catalog.services import CatalogService
from src.modules.orders.services import OrderService
from src.modules.orders.uow import OrderUnitOfWork


def get_order_uow() -> OrderUnitOfWork:
    """
    Фабрика UoW для домена заказов.
    Просто возвращает неинициализированный объект.
    Сессия БД будет открыта внутри сервиса через `async with self.uow`.
    """
    return OrderUnitOfWork(session_factory=async_session_maker)


def get_order_service(
    uow: Annotated[OrderUnitOfWork, Depends(dependency=get_order_uow)],
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> OrderService:
    """
    Провайдер сервиса заказов.
    Готов к внедрению в роутеры слоя API (например, в backoffice/orders.py).
    """

    return OrderService(uow=uow, catalog_service=catalog_service)
