import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security, status

from src.application.courier.dependencies import get_courier_service
from src.application.courier.schemas import (
    CourierCreate,
    CourierResponse,
    CouriersResponse,
)
from src.application.courier.service import CourierService
from src.core.security.permissions import Scope
from src.modules.auth.dependencies import get_current_user
from src.modules.users.dependencies import get_user_service
from src.modules.users.models import User
from src.modules.users.schemas import UserAdminUpdate, UserResponse
from src.modules.users.services import UserService

couriers_router = APIRouter()


@couriers_router.post(
    "/",
    response_model=CourierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Зарегистрировать нового курьера",
)
async def create_courier(
    schema: CourierCreate,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    courier_service: Annotated[CourierService, Depends(get_courier_service)],
):
    return await courier_service.create_courier(schema)


@couriers_router.get(
    "/",
    response_model=CouriersResponse,
    summary="Список всех курьеров",
)
async def get_couriers(
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_READ])
    ],
    courier_service: Annotated[CourierService, Depends(get_courier_service)],
    page: Annotated[int, Query(ge=1, description="Номер страницы")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Размер страницы")] = 50,
    search: Annotated[str | None, Query(description="Поиск по ФИО курьера")] = None,
):
    skip = (page - 1) * size
    return await courier_service.get_couriers(skip=skip, limit=size, search=search)


@couriers_router.get(
    "/{courier_id}",
    response_model=CourierResponse,
    summary="Профиль курьера",
)
async def get_courier(
    courier_id: uuid.UUID,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_READ])
    ],
    courier_service: Annotated[CourierService, Depends(get_courier_service)],
):
    """Получить данные конкретного курьера."""
    return await courier_service.get_courier(courier_id)


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
