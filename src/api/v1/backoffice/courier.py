import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security, status

from src.core.security.permissions import Scope
from src.modules.auth.dependencies import get_current_user
from src.modules.finances.dependencies import get_billing_service
from src.modules.finances.services import BillingService
from src.modules.users.dependencies import get_user_service
from src.modules.users.models import Role, User
from src.modules.users.schemas import (
    CouriersResponse,
    UserAdminCreate,
    UserAdminUpdate,
    UserResponse,
)
from src.modules.users.services import UserService

# Создаем выделенный роутер
couriers_router = APIRouter()


@couriers_router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Зарегистрировать нового курьера",
)
async def create_courier(
    schema: UserAdminCreate,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    user_service: Annotated[UserService, Depends(get_user_service)],
    billing_service: Annotated[
        BillingService, Depends(get_billing_service)
    ],  # <-- ИНЪЕКЦИЯ
):
    """
    Создание курьера. Роль принудительно устанавливается в COURIER,
    чтобы избежать случайного создания других типов пользователей.
    """
    schema.role = Role.COURIER
    courier = await user_service.register_local_user(schema)
    await billing_service.get_or_add_courier_account(courier_id=courier.id)
    return courier


# src/api/v1/backoffice/couriers.py
@couriers_router.get(
    "/",
    response_model=CouriersResponse,
    summary="Список всех курьеров",
)
async def get_couriers(
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_READ])
    ],
    user_service: Annotated[UserService, Depends(get_user_service)],
    page: Annotated[int, Query(ge=1, description="Номер страницы")] = 1,
    size: Annotated[
        int, Query(ge=1, le=100, description="Размер страницы")
    ] = 50,
    search: Annotated[
        str | None, Query(description="Поиск по ФИО курьера")
    ] = None,
):
    """
    Выводит список курьеров с привязанными к ним активными счетами (Account)
    и складами/машинами (Inventory).
    """
    skip = (page - 1) * size
    return await user_service.get_couriers(
        skip=skip, limit=size, search=search
    )


@couriers_router.get(
    "/{courier_id}",
    response_model=UserResponse,
    summary="Профиль курьера",
)
async def get_courier(
    courier_id: uuid.UUID,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_READ])
    ],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """
    Получить данные конкретного курьера.
    """
    # В идеале на уровне сервиса можно добавить проверку:
    # if user.role != Role.COURIER: raise NotFoundError()
    user = await user_service.get(id=courier_id)
    return user


@couriers_router.patch(
    "/{courier_id}",
    response_model=UserResponse,
    summary="Обновить данные курьера",
)
async def update_courier(
    courier_id: uuid.UUID,
    schema: UserAdminUpdate,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """Изменение ФИО, пароля или других данных курьера."""
    updated_user = await user_service.update(courier_id, schema)
    return updated_user


@couriers_router.post(
    "/{courier_id}/block",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Уволить/Заблокировать курьера",
)
async def block_courier(
    courier_id: uuid.UUID,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """
    Переводит курьера в статус is_active = False.
    """
    await user_service.archive(courier_id)
