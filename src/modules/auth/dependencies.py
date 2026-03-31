# src/modules/auth/dependencies.py
import uuid
from typing import Annotated, Any

from fastapi import Depends, Security
from fastapi.security import OAuth2PasswordBearer, SecurityScopes

from src.core.config import settings
from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.core.security.jwt import decode_access_token
from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.services import AuthService
from src.modules.users.dependencies import get_user_service
from src.modules.users.enums import Role
from src.modules.users.services import UserService

# 1. ДИНАМИЧЕСКАЯ ГЕНЕРАЦИЯ SCOPES ДЛЯ SWAGGER
# Берем все публичные строковые атрибуты из класса Scope
swagger_scopes = {
    value: f"Разрешение: {value}"
    for key, value in vars(Scope).items()
    if not key.startswith("__") and isinstance(value, str)
}

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    scopes=swagger_scopes,
)


async def get_token_payload(
    security_scopes: SecurityScopes,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> dict[str, Any]:
    """
    [FAST PATH] Уровень 1: Валидация JWT и проверка прав.
    НЕ ДЕЛАЕТ ЗАПРОСОВ В БД. Идеально для высоконагруженных ручек.
    """
    payload = decode_access_token(token)
    user_id_str = payload.get("sub")
    token_scopes = payload.get("scopes", [])

    if not user_id_str:
        raise UnauthorizedError(
            message="Некорректный токен: отсутствует ID пользователя.",
            error_code="INVALID_TOKEN_PAYLOAD",
        )

    for required_scope in security_scopes.scopes:
        if required_scope not in token_scopes:
            raise ForbiddenError(
                message=f"Требуется разрешение: '{required_scope}'",
                error_code="INSUFFICIENT_PERMISSIONS",
            )
    return payload


async def get_current_user(
    payload: Annotated[dict[str, Any], Depends(get_token_payload)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> User:
    """
    [SLOW PATH] Уровень 2: Получение пользователя из БД.
    Использует кэшированный payload из Уровня 1.
    """
    user_id_str = payload.get("sub")
    try:
        user_id = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        raise UnauthorizedError(  # noqa: B904
            message="Некорректный формат ID пользователя в токене.",
            error_code="INVALID_USER_ID",
        )

    user = await user_service.get(id=user_id)

    if not user:
        raise UnauthorizedError(
            message="Пользователь не найден. Возможно, аккаунт был удален.",
            error_code="USER_NOT_FOUND",
        )
    if not user.is_active:
        raise ForbiddenError(
            message="Ваш аккаунт заблокирован. Обратитесь в поддержку.",
            error_code="USER_BANNED",
        )

    return user


async def get_current_courier(
    current_user: Annotated[User, Security(get_current_user)],
) -> User:
    if current_user.role != Role.COURIER:
        raise ForbiddenError(
            message="Эта ручка доступна только для курьеров.",
            error_code="COURIER_ONLY",
        )
    return current_user


def get_auth_service(
    user_service: Annotated[UserService, Depends(dependency=get_user_service)],
) -> AuthService:
    return AuthService(user_service=user_service)
