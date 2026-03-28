# src\application\order\dependencies.py
from typing import Annotated

from fastapi import Depends

from src.application.client.service import ClientService
from src.application.client.uow import ClientUnitOfWork, IClientUnitOfWork
from src.infrastructure.database.session import async_session_maker
from src.modules.catalog.dependencies import get_catalog_service
from src.modules.catalog.public import CatalogService


def get_client_uow() -> IClientUnitOfWork:
    """
    Фабрика для кросс-доменного UoW Клиентов.
    """
    return ClientUnitOfWork(session_factory=async_session_maker)


def get_client_service(
    uow: Annotated[ClientUnitOfWork, Depends(get_client_uow)],
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> ClientService:
    return ClientService(uow=uow, catalog_service=catalog_service)
