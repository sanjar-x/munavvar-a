import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Security, status

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.users.dependencies import get_user_service
from src.modules.users.schemas import (
    UserAdminCreate,
    UserAdminUpdate,
    UserResponse,
)
from src.modules.users.services import UserService

users_router = APIRouter()


@users_router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать нового сотрудника или пользователя",
)
async def create_user(
    schema: UserAdminCreate,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """
    Создание пользователя вручную через админ-панель.
    """
    user = await user_service.register_local_user(schema)
    return user


@users_router.get(
    "/{id}",
    response_model=UserResponse,
    summary="Получить профиль пользователя по ID",
)
async def get_user(
    id: uuid.UUID,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_READ])
    ],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """
    Детальная информация о конкретном пользователе.
    Если пользователь не найден, сервис должен выбросить NotFoundError.
    """
    user = await user_service.get(id=id)
    return user


@users_router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Обновить данные пользователя",
)
async def update_user(
    user_id: uuid.UUID,
    schema: UserAdminUpdate,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    updated_user = await user_service.update(user_id, schema)
    return updated_user


@users_router.post(
    "/{user_id}/block",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Заблокировать пользователя",
)
async def block_user(
    user_id: uuid.UUID,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """
    Мягкое удаление / блокировка пользователя (is_active = False).
    """
    await user_service.archive(user_id)
