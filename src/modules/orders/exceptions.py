# src/modules/orders/exceptions.py

import uuid
from typing import Any

from src.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
)


class OrderNotFoundError(NotFoundError):
    """Выбрасывается, когда запрашиваемый заказ не существует."""

    def __init__(
        self,
        order_id: uuid.UUID | str,
        message: str = "Заказ не найден",
    ):
        super().__init__(
            message=message,
            error_code="ORDER_NOT_FOUND",
            details={"order_id": str(order_id)},
        )


class InvalidOrderStatusError(ConflictError):
    """
    Защита State Machine.
    Выбрасывается при попытке нелогичного перехода статусов.
    Например: попытка отменить уже доставленный заказ.
    """

    def __init__(
        self,
        order_id: uuid.UUID | str,
        current_status: Any,
        expected_status: Any = None,
        message: str = "Недопустимая операция для текущего статуса заказа",
    ):
        details = {
            "order_id": str(order_id),
            "current_status": str(current_status),
        }
        if expected_status:
            details["expected_status"] = str(expected_status)

        super().__init__(
            message=message,
            error_code="INVALID_ORDER_STATUS",
            details=details,
        )


class OrderAccessDeniedError(ForbiddenError):
    """
    Защита от IDOR (Insecure Direct Object Reference).
    Выбрасывается, если клиент пытается просмотреть чужой заказ,
    или курьер пытается закрыть заказ, назначенный на другого водителя.
    """

    def __init__(
        self,
        user_id: uuid.UUID | str,
        order_id: uuid.UUID | str,
        message: str = "У вас нет прав на управление этим заказом",
    ):
        super().__init__(
            message=message,
            error_code="ORDER_ACCESS_DENIED",
            details={"user_id": str(user_id), "order_id": str(order_id)},
        )


class EmptyCartError(ConflictError):
    """Выбрасывается при попытке оформить заказ без товаров."""

    def __init__(
        self, message: str = "Невозможно оформить заказ: корзина пуста"
    ):
        super().__init__(
            message=message,
            error_code="EMPTY_CART",
        )


class ProductsUnavailableError(ConflictError):
    """
    Выбрасывается на этапе Checkout'а, если запрошенные товары
    отсутствуют в модуле Catalog (удалены или скрыты).
    """

    def __init__(
        self,
        missing_product_ids: list[uuid.UUID],
        message: str = "Один или несколько товаров недоступны для заказа",
    ):
        super().__init__(
            message=message,
            error_code="PRODUCTS_UNAVAILABLE",
            details={
                "missing_product_ids": [
                    str(pid) for pid in missing_product_ids
                ]
            },
        )


class CourierAssignmentError(ConflictError):
    """
    Выбрасывается при ошибках диспетчеризации логиста.
    Например, если попытаться назначить курьера на отмененный заказ.
    """

    def __init__(
        self,
        order_id: uuid.UUID | str,
        courier_id: uuid.UUID | str,
        reason: str,
    ):
        super().__init__(
            message=f"Ошибка назначения курьера: {reason}",
            error_code="COURIER_ASSIGNMENT_ERROR",
            details={"order_id": str(order_id), "courier_id": str(courier_id)},
        )


class InsufficientTaraError(ConflictError):
    """
    Выбрасывается при оформлении заказа, если у клиента
    недостаточно пустой тары для обмена.
    """

    def __init__(
        self,
        shortages: list[dict[str, Any]],
        message: str = "Недостаточно пустой тары для оформления заказа",
    ):
        super().__init__(
            message=message,
            error_code="INSUFFICIENT_TARA",
            details={"shortages": shortages},
        )


class ClientInventoryNotFoundError(NotFoundError):
    """Выбрасывается, когда инвентарь (адрес доставки) клиента не найден."""

    def __init__(
        self,
        inventory_id: uuid.UUID | str,
        message: str = "Инвентарь клиента не найден",
    ):
        super().__init__(
            message=message,
            error_code="CLIENT_INVENTORY_NOT_FOUND",
            details={"inventory_id": str(inventory_id)},
        )


class DeliveryQuantityExceededError(ConflictError):
    """
    Курьер указал фактическое количество товара больше заказанного.
    Защита от накрутки долга клиенту.
    """

    def __init__(
        self,
        product_id: uuid.UUID | str,
        ordered: int,
        actual: int,
    ):
        super().__init__(
            message="Фактическое количество превышает заказанное",
            error_code="DELIVERY_QUANTITY_EXCEEDED",
            details={
                "product_id": str(product_id),
                "ordered": ordered,
                "actual": actual,
            },
        )


class CannotRemoveLastItemError(ConflictError):
    """
    Запрет удаления последнего товара из заказа.
    Пустой заказ не должен существовать — используйте отмену.
    """

    def __init__(self):
        super().__init__(
            message="Нельзя удалить последний товар. Используйте отмену заказа.",
            error_code="CANNOT_REMOVE_LAST_ITEM",
        )


class InvalidPickupOperationError(ConflictError):
    """Выбрасывается при попытке выполнить pickup-операцию на обычном заказе."""

    def __init__(
        self,
        order_id: uuid.UUID | str,
        reason: str,
    ):
        super().__init__(
            message=f"Ошибка операции самовывоза: {reason}",
            error_code="INVALID_PICKUP_OPERATION",
            details={"order_id": str(order_id)},
        )


class CatalogServiceUnavailableError(ServiceUnavailableError):
    """
    Выбрасывается, если модуль Orders не может получить цены из модуля Catalog.
    (Актуально, если в будущем вы разнесете монолит на микросервисы).
    """

    def __init__(
        self,
        message: str = "Сервис каталога временно недоступен для расчета цен",
    ):
        super().__init__(
            message=message,
            error_code="CATALOG_SERVICE_UNAVAILABLE",
        )
