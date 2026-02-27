# src/api/v1/auth/register.py
from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.api.dependencies.services import get_user_service
from src.modules.users.models import Role, User
from src.modules.users.schemas import UserAdminCreate, UserCreate, UserResponse
from src.modules.users.services import UserService

register__router = APIRouter()


@register__router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация нового клиента",
)
async def register_user(
    schema: UserCreate,
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    admin_schema = UserAdminCreate(**schema.model_dump(), role=Role.CLIENT_B2C)

    # 3. Передаем в сервис правильный объект UserAdminCreate
    user: User = await user_service.register_local_user(admin_schema)

    return user
