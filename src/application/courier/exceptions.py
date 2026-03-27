import uuid

from src.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
)


class CourierNotFoundError(NotFoundError):
    """Выбрасывается, когда запрашиваемый курьер не найден в БД."""

    def __init__(self, courier_id: uuid.UUID):
        super().__init__(
            message=f"Курьер с идентификатором {courier_id} не найден.",
            error_code="COURIER_NOT_FOUND",
            details={"courier_id": str(courier_id)},
        )


class CourierAlreadyExistsError(ConflictError):
    """Выбрасывается, когда мы пытаемся зарегистрировать курьера с уже занятым номером телефона."""

    def __init__(self, phone: str):
        super().__init__(
            message=f"Курьер с номером телефона '{phone}' уже зарегистрирован.",
            error_code="COURIER_ALREADY_EXISTS",
            details={"phone": phone},
        )


class CourierInactiveError(UnauthorizedError):
    """Выбрасывается, если курьер был уволен/отстранен в админке."""

    def __init__(
        self, phone: str | None = None, courier_id: uuid.UUID | None = None
    ):
        details = {}
        if phone:
            details["phone"] = phone
        if courier_id:
            details["courier_id"] = str(courier_id)

        super().__init__(
            message="Аккаунт курьера деактивирован. Обратитесь к логисту или руководству.",
            error_code="COURIER_INACTIVE",
            details=details,
        )


class CourierInventoryNotFoundError(NotFoundError):
    """Выбрасывается, если запрашиваемый инвентарь (машина) не принадлежит курьеру или не найден."""

    def __init__(self, inventory_id: uuid.UUID):
        super().__init__(
            message=f"Машина (инвентарь) с идентификатором {inventory_id} не найдена.",
            error_code="COURIER_INVENTORY_NOT_FOUND",
            details={"inventory_id": str(inventory_id)},
        )


class CourierHasBalancesError(BadRequestError):
    """Выбрасывается при попытке удалить курьера, у которого есть долги или невозвращенная тара в машине."""

    def __init__(
        self,
        message: str = "Невозможно удалить курьера: в машине числится тара или на счету есть средства.",
    ):
        super().__init__(
            message=message,
            error_code="COURIER_HAS_BALANCES",
        )
