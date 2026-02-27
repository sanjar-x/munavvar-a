import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from src.core.config import settings
from src.core.exceptions import UnauthorizedError


def create_access_token(
    payload_data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    """
    Генерирует JWT токен.
    :param payload_data: Полезная нагрузка (например, {"sub": "123", "scopes": [...]})
    :param expires_delta: Опциональное время жизни токена
    """
    # 1. Создаем копию словаря, чтобы не мутировать исходный
    to_encode = payload_data.copy()

    # 2. Рассчитываем время жизни
    now = datetime.now(tz=UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # 3. Добавляем стандартные системные Claims (зарезервированные поля JWT)
    to_encode.update(
        {
            "exp": expire,  # Время смерти
            "iat": now,  # Время создания
            "jti": str(uuid.uuid4()),  # Уникальный ID токена (для Blacklist)
        }
    )

    # 4. Подписываем
    encoded_jwt: str = jwt.encode(
        to_encode,
        key=settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Расшифровывает и валидирует токен.
    """
    try:
        decoded_token: dict[str, Any] = jwt.decode(
            jwt=token,
            key=settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
        )
        return decoded_token

    except ExpiredSignatureError as e:
        raise UnauthorizedError(
            message="Срок действия токена истек. Авторизуйтесь заново.",
            error_code="TOKEN_EXPIRED",
        ) from e
    except InvalidTokenError as e:
        raise UnauthorizedError(
            message="Невалидный токен доступа.", error_code="INVALID_TOKEN"
        ) from e
