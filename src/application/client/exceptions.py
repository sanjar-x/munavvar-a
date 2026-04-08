import uuid

from src.core.exceptions import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
)


class ClientNotFoundError(NotFoundError):
    """Выбрасывается, когда запрашиваемый клиент не найден в БД."""

    def __init__(self, client_id: uuid.UUID):
        super().__init__(
            message=f"Клиент с идентификатором {client_id} не найден.",
            error_code="CLIENT_NOT_FOUND",
            details={"client_id": str(client_id)},
        )


class ClientAlreadyExistsError(ConflictError):
    """Выбрасывается, когда мы пытаемся создать клиента
    с уже занятым номером телефона."""

    def __init__(self, phone: str):
        super().__init__(
            message=(
                f"Клиент с номером телефона '{phone}' уже зарегистрирован."
            ),
            error_code="CLIENT_ALREADY_EXISTS",
            details={"phone": phone},
        )


class ClientInactiveError(UnauthorizedError):
    """Выбрасывается, если клиент был заблокирован/деактивирован в админке."""

    def __init__(
        self, phone: str | None = None, client_id: uuid.UUID | None = None
    ):
        details = {}
        if phone:
            details["phone"] = phone
        if client_id:
            details["client_id"] = str(client_id)

        super().__init__(
            message="Аккаунт клиента деактивирован. Обратитесь в поддержку.",
            error_code="CLIENT_INACTIVE",
            details=details,
        )


class ClientAddressNotFoundError(NotFoundError):
    """Выбрасывается, если запрашиваемый инвентарь (адрес)
    не принадлежит клиенту или не найден."""

    def __init__(self, inventory_id: uuid.UUID):
        super().__init__(
            message=(
                f"Адрес (инвентарь) с идентификатором"
                f" {inventory_id} не найден."
            ),
            error_code="CLIENT_ADDRESS_NOT_FOUND",
            details={"inventory_id": str(inventory_id)},
        )
