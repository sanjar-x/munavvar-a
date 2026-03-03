# src/modules/users/dependencies.py
from typing import Annotated

from fastapi import Depends

from src.infrastructure.database.session import async_session_maker
from src.modules.users.services import UserService
from src.modules.users.uow import UserUnitOfWork


# 1. Провайдер UoW
def get_user_uow() -> UserUnitOfWork:
    return UserUnitOfWork(session_factory=async_session_maker)


# 2. Провайдер Сервиса
def get_user_service(
    uow: Annotated[UserUnitOfWork, Depends(dependency=get_user_uow)],
) -> UserService:
    return UserService(uow=uow)
