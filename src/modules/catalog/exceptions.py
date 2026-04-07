# src/modules/catalog/exceptions.py

import uuid
from typing import Any

from src.core.exceptions import (
    BadRequestError,
    NotFoundError,
)


class ProductNotFoundError(NotFoundError):
    """Выбрасывается, когда запрашиваемый товар или тара не существуют в БД."""

    def __init__(
        self,
        product_id: uuid.UUID | None = None,
        message: str = "Товар не найден",
        details: dict[str, Any] | None = None,
    ):
        error_details = details or {}
        if product_id:
            error_details["product_id"] = str(product_id)

        super().__init__(
            message=message,
            error_code="PRODUCT_NOT_FOUND",
            details=error_details,
        )


class ProductHasStockError(BadRequestError):
    """Нельзя удалить товар, если он есть на складах/транспортах."""

    def __init__(
        self,
        product_id: uuid.UUID,
        details: dict[str, Any] | None = None,
    ):
        error_details = details or {}
        error_details["product_id"] = str(product_id)
        super().__init__(
            message=(
                "Невозможно удалить товар:"
                " на складах или в транспортах есть остатки"
            ),
            error_code="PRODUCT_HAS_STOCK",
            details=error_details,
        )


class ProductHasAssociatedProductsError(BadRequestError):
    """Нельзя удалить товар, если другие товары ссылаются
    на него как на возвратную тару."""

    def __init__(
        self,
        product_id: uuid.UUID,
        details: dict[str, Any] | None = None,
    ):
        error_details = details or {}
        error_details["product_id"] = str(product_id)
        super().__init__(
            message=(
                "Невозможно удалить товар:"
                " другие товары ссылаются на него"
                " как на возвратную тару"
            ),
            error_code="PRODUCT_HAS_ASSOCIATED_PRODUCTS",
            details=error_details,
        )


class InvalidReturnableItemError(BadRequestError):
    """Выбрасывается при нарушении бизнес-правил привязки возвратной тары."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            error_code="INVALID_RETURNABLE_ITEM",
            details=details,
        )
