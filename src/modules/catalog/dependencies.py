# src/modules/catalog/dependencies.py
from typing import Annotated

from fastapi import Depends

from src.infrastructure.database.session import async_session_maker
from src.modules.catalog.services import CatalogService
from src.modules.catalog.uow import CatalogUnitOfWork


def get_catalog_uow() -> CatalogUnitOfWork:
    return CatalogUnitOfWork(session_factory=async_session_maker)


def get_catalog_service(
    uow: Annotated[CatalogUnitOfWork, Depends(get_catalog_uow)],
) -> CatalogService:
    return CatalogService(uow=uow)
