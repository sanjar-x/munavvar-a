# src/modules/inventory/exceptions.py
import uuid
from typing import Any

from fastapi import status

from src.core.exceptions import (
    AppException,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnprocessableEntityError,
)

# ==========================================
# 1. СИСТЕМНЫЕ ОШИБКИ И КОНФИГУРАЦИЯ (500)
# ==========================================


class VirtualInventoryConfigurationError(AppException):
    """
    Критическая системная ошибка.
    Выбрасывается, когда сервис пытается получить виртуальный склад (например, VIRTUAL_LOSS),
    но он не был создан при инициализации БД (отсутствует сидирование).
    """

    def __init__(
        self,
        v_type: str | Any,
        message: str = "Критическая ошибка: Системный виртуальный склад не сконфигурирован",
    ):
        v_type_val = v_type.value if hasattr(v_type, "value") else str(v_type)
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="VIRTUAL_INVENTORY_MISSING",
            details={"inventory_type": v_type_val},
        )


# ==========================================
# 2. ОШИБКИ ПОИСКА (404 NOT FOUND)
# ==========================================


class InventoryNotFoundError(NotFoundError):
    """Склад, локация или машина не найдены."""

    def __init__(
        self,
        inventory_id: uuid.UUID | str,
        message: str = "Локация (склад/клиент/машина) не найдена",
    ):
        super().__init__(
            message=message,
            error_code="INVENTORY_NOT_FOUND",
            details={"inventory_id": str(inventory_id)},
        )


class TransferNotFoundError(NotFoundError):
    """Накладная не найдена."""

    def __init__(
        self,
        transfer_id: uuid.UUID | str,
        message: str = "Накладная не найдена",
    ):
        super().__init__(
            message=message,
            error_code="TRANSFER_NOT_FOUND",
            details={"transfer_id": str(transfer_id)},
        )


# ==========================================
# 3. ОШИБКИ ВАЛИДАЦИИ (400 / 422)
# ==========================================


class RouteLoopError(BadRequestError):
    """Предотвращает создание бессмысленных накладных (отправка на тот же склад)."""

    def __init__(
        self,
        inventory_id: uuid.UUID | str,
        message: str = "Локация отправителя и получателя не могут совпадать",
    ):
        super().__init__(
            message=message,
            error_code="ROUTE_LOOP_DETECTED",
            details={"inventory_id": str(inventory_id)},
        )


class EmptyTransferError(UnprocessableEntityError):
    """Попытка перевести накладную без товаров в статус IN_TRANSIT или COMPLETED."""

    def __init__(
        self,
        transfer_id: uuid.UUID | str,
        message: str = "Накладная пуста (отсутствуют товары в корзине)",
    ):
        super().__init__(
            message=message,
            error_code="EMPTY_TRANSFER",
            details={"transfer_id": str(transfer_id)},
        )


class InvalidQuantityError(UnprocessableEntityError):
    """Защита от передачи отрицательных или нулевых значений в корзину."""

    def __init__(
        self,
        product_id: uuid.UUID | str,
        quantity: int,
        message: str = "Количество товара должно быть строго больше нуля",
    ):
        super().__init__(
            message=message,
            error_code="INVALID_QUANTITY",
            details={
                "product_id": str(product_id),
                "provided_quantity": quantity,
            },
        )


# ==========================================
# 4. БИЗНЕС-КОНФЛИКТЫ (409 CONFLICT)
# ==========================================


class InsufficientStockError(ConflictError):
    """Не хватает остатков для проведения накладной. Передает shortages на фронтенд."""

    def __init__(
        self,
        shortages: dict[uuid.UUID, int],
        message: str = "Недостаточно товара на локации-отправителе",
    ):
        stringified_shortages = {str(k): v for k, v in shortages.items()}
        super().__init__(
            message=message,
            error_code="INSUFFICIENT_STOCK",
            details={"shortages": stringified_shortages},
        )


class InvalidTransferStatusError(ConflictError):
    """Попытка провести накладную с неверным статусом (например, принять DRAFT)."""

    def __init__(
        self,
        current_status: str | Any,
        expected_status: str | list[str] | Any,
        message: str = "Недопустимый статус накладной для данной бизнес-операции",
    ):
        curr_val = (
            current_status.value
            if hasattr(current_status, "value")
            else str(current_status)
        )

        if isinstance(expected_status, list):
            exp_val = [
                e.value if hasattr(e, "value") else str(e)
                for e in expected_status
            ]
        else:
            exp_val = (
                expected_status.value
                if hasattr(expected_status, "value")
                else str(expected_status)
            )

        super().__init__(
            message=message,
            error_code="INVALID_TRANSFER_STATUS",
            details={
                "current_status": curr_val,
                "expected_status": exp_val,
            },
        )


class TransferTypeMismatchError(ConflictError):
    """Несоответствие типа накладной процессу (например, отгрузка клиента вместо закупки)."""

    def __init__(
        self,
        expected_type: str | Any,
        actual_type: str | Any,
        message: str = "Несоответствие типа накладной для данной бизнес-операции",
    ):
        exp_val = (
            expected_type.value
            if hasattr(expected_type, "value")
            else str(expected_type)
        )
        act_val = (
            actual_type.value
            if hasattr(actual_type, "value")
            else str(actual_type)
        )

        super().__init__(
            message=message,
            error_code="TRANSFER_TYPE_MISMATCH",
            details={
                "expected_type": exp_val,
                "actual_type": act_val,
            },
        )


class InventoryTypeMismatchError(ConflictError):
    """
    Защита домена: попытка использовать склад клиента как машину курьера,
    или виртуальный склад как реальный.
    """

    def __init__(
        self,
        inventory_id: uuid.UUID | str,
        expected_type: str | Any,
        actual_type: str | Any,
        message: str = "Тип локации не подходит для данной операции",
    ):
        exp_val = (
            expected_type.value
            if hasattr(expected_type, "value")
            else str(expected_type)
        )
        act_val = (
            actual_type.value
            if hasattr(actual_type, "value")
            else str(actual_type)
        )

        super().__init__(
            message=message,
            error_code="INVENTORY_TYPE_MISMATCH",
            details={
                "inventory_id": str(inventory_id),
                "expected_type": exp_val,
                "actual_type": act_val,
            },
        )


class ProductMismatchInTransitError(ConflictError):
    """Фаза 2 (Приемка): попытка принять товар, которого не было в исходной накладной отгрузки."""

    def __init__(
        self,
        invalid_product_ids: list[uuid.UUID],
        message: str = "Попытка принять товар, который не был отгружен в данной накладной",
    ):
        stringified_ids = [str(p_id) for p_id in invalid_product_ids]
        super().__init__(
            message=message,
            error_code="PRODUCT_MISMATCH_IN_TRANSIT",
            details={"invalid_product_ids": stringified_ids},
        )


class CourierRouteMismatchError(ConflictError):
    """Попытка инкассации/разгрузки не своей машины или чужого маршрутного листа."""

    def __init__(
        self,
        route_sheet_id: uuid.UUID | str,
        inventory_id: uuid.UUID | str,
        message: str = "Машина не привязана к указанному маршрутному листу",
    ):
        super().__init__(
            message=message,
            error_code="COURIER_ROUTE_MISMATCH",
            details={
                "route_sheet_id": str(route_sheet_id),
                "inventory_id": str(inventory_id),
            },
        )


# ==========================================
# 5. ОШИБКИ БЕЗОПАСНОСТИ И ЛЕДЖЕРА (403 FORBIDDEN)
# ==========================================


class StrictLedgerViolationError(ForbiddenError):
    """Попытка напрямую изменить Леджер через update/delete."""

    def __init__(
        self,
        message: str = "Strict Ledger: Прямая мутация проводок запрещена. Используйте компенсирующую накладную (Reversal).",
    ):
        super().__init__(
            message=message,
            error_code="STRICT_LEDGER_VIOLATION",
        )


class ReversalNotAllowedError(ForbiddenError):
    """Попытка отменить/отреверсировать накладную, которую отменять нельзя (например, Инвентаризацию)."""

    def __init__(
        self,
        transfer_id: uuid.UUID | str,
        transfer_type: str | Any,
        message: str = "Данный тип накладной не подлежит автоматической отмене (Reversal)",
    ):
        t_type = (
            transfer_type.value
            if hasattr(transfer_type, "value")
            else str(transfer_type)
        )
        super().__init__(
            message=message,
            error_code="REVERSAL_NOT_ALLOWED",
            details={
                "transfer_id": str(transfer_id),
                "transfer_type": t_type,
            },
        )
