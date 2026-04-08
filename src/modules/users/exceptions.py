# src/modules/users/exceptions.py

import uuid

from src.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
    UnprocessableEntityError,
)


class UserNotFoundError(NotFoundError):
    def __init__(self, user_id: uuid.UUID):
        super().__init__(
            message=f"Пользователь с идентификатором {user_id} не найден.",
            error_code="USER_NOT_FOUND",
            details={"user_id": user_id},
        )


class UserAlreadyExistsError(ConflictError):
    def __init__(self, identity_id: str):
        # super().__init__ передает данные в базовый класс ConflictError,
        # который уже сам решит, как превратить их в HTTP 409
        super().__init__(
            message=(
                f"Пользователь с идентификатором"
                f" '{identity_id}' уже зарегистрирован."
            ),
            error_code="USER_ALREADY_EXISTS",
            details={"identity_id": identity_id},
        )


class InvalidCredentialsError(UnauthorizedError):
    def __init__(self):
        super().__init__(
            message="Неверный email или пароль.",
            error_code="INVALID_CREDENTIALS",
        )


class UserInactiveError(UnauthorizedError):
    def __init__(self, email: str):
        super().__init__(
            message="Аккаунт деактивирован. Обратитесь в поддержку.",
            error_code="USER_INACTIVE",
            details={"email": email},
        )


class UserForbiddenError(ForbiddenError):
    def __init__(self, action: str):
        super().__init__(
            message=f"У вас нет прав для выполнения действия: {action}.",
            error_code="USER_FORBIDDEN",
            details={"action": action},
        )


class UserServiceUnavailableError(ServiceUnavailableError):
    def __init__(self):
        super().__init__(
            message="Сервис пользователей временно недоступен.",
            error_code="USER_SERVICE_UNAVAILABLE",
        )


class UserUpdateConflictError(ConflictError):
    def __init__(self, user_id: uuid.UUID, reason: str | None = None):
        details = {"user_id": user_id}
        if reason:
            details["reason"] = reason

        super().__init__(
            message=(
                f"Не удалось обновить данные пользователя"
                f" {user_id} из-за конфликта состояний."
            ),
            error_code="USER_UPDATE_CONFLICT",
            details=details,
        )


class UserDeleteConflictError(ConflictError):
    def __init__(self, user_id: uuid.UUID, reason: str | None = None):
        details = {"user_id": user_id}
        if reason:
            details["reason"] = reason

        super().__init__(
            message=(
                "Отказ физического удаления."
                f" Пользователь {user_id}"
                " имеет жесткие связи в базе данных."
            ),
            error_code="USER_DELETE_CONFLICT",
            details=details,
        )


class StaffPasswordRequiredError(UnprocessableEntityError):
    def __init__(self, user_id: uuid.UUID, role: str):
        super().__init__(
            message=(
                "Для назначения роли сотрудника необходимо задать пароль "
                "для локального входа."
            ),
            error_code="STAFF_PASSWORD_REQUIRED",
            details={"user_id": user_id, "role": role},
        )


class PhoneAlreadyExistsError(ConflictError):
    def __init__(self, phone: str):
        super().__init__(
            message=(f"Номер телефона '{phone}' уже используется."),
            error_code="PHONE_ALREADY_EXISTS",
            details={"phone": phone},
        )


class PhoneNotFoundError(NotFoundError):
    def __init__(self, phone_id: uuid.UUID):
        super().__init__(
            message=(f"Телефонный номер с ID {phone_id} не найден."),
            error_code="PHONE_NOT_FOUND",
            details={"phone_id": phone_id},
        )


class PhoneLimitExceededError(UnprocessableEntityError):
    def __init__(self, user_id: uuid.UUID, limit: int = 5):
        super().__init__(
            message=(
                f"Достигнут лимит дополнительных телефонов"
                f" ({limit}) для пользователя."
            ),
            error_code="PHONE_LIMIT_EXCEEDED",
            details={"user_id": user_id, "limit": limit},
        )
