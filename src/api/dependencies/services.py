from typing import Annotated

from fastapi import Depends

from src.api.dependencies.database import get_uow
from src.common.uow import IUnitOfWork
from src.modules.auth.services import AuthService
from src.modules.catalog.services import CatalogService
from src.modules.users.services import UserService


def get_auth_service(
    uow: Annotated[IUnitOfWork, Depends(dependency=get_uow)],
) -> AuthService:
    """Инъекция сервиса аутентификации"""
    return AuthService(uow)


def get_user_service(
    uow: Annotated[IUnitOfWork, Depends(dependency=get_uow)],
) -> UserService:
    return UserService(uow=uow)


def get_catalog_service(
    uow: Annotated[IUnitOfWork, Depends(dependency=get_uow)],
) -> CatalogService:
    return CatalogService(uow=uow)
