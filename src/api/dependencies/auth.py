# src/api/dependencies/auth.py
import uuid
from typing import Annotated, Any

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer, SecurityScopes

from src.api.dependencies.services import get_user_service
from src.core.config import settings
from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.core.security.jwt import decode_access_token
from src.core.security.permissions import Scope
from src.modules.users.models import User
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
    scopes=swagger_scopes,  # Теперь Swagger всегда знает все права!
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
    except ValueError, TypeError:
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
