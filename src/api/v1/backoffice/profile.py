# src/api/v1/profile/me.py

from typing import Annotated

from fastapi import APIRouter, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.users.schemas import UserResponse

profile_router = APIRouter()


@profile_router.get(
    "/me",
    response_model=UserResponse,
    summary="Получить профиль текущего пользователя",
)
async def get_me(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.PROFILE_READ])
    ],
):
    """
    Возвращает данные профиля авторизованного пользователя.
    FastAPI автоматически:
    1. Достанет JWT из заголовка Authorization
    2. Проверит наличие 'profile:read' в токене
    3. Сходит в БД (через get_current_user) и достанет объект User
    """
    # Никаких запросов к сервисам или БД внутри роутера!
    # Зависимость уже сделала всю грязную работу.
    return current_user
