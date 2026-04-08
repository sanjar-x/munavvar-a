# src/application/order/schemas.py
import uuid

from pydantic import BaseModel, ConfigDict, Field

# Тебе нужно убедиться, что PaymentMethod импортируется из правильного места
from src.modules.orders.enums import PaymentMethod

# --- ВЛОЖЕННЫЕ СХЕМЫ ---


class OrderItemCreate(BaseModel):
    """Схема одного товара в корзине/заказе."""

    product_id: uuid.UUID = Field(..., description="ID товара из каталога")
    quantity: int = Field(
        ..., gt=0, description="Количество товара (строго больше нуля)"
    )


class MissingTaraDTO(BaseModel):
    """Схема для описания недостающей тары в ответе валидации."""

    product_id: str = Field(..., description="ID возвратной тары")
    name: str = Field(..., description="Название тары")
    missing_quantity: int = Field(
        ..., description="Сколько штук не хватает на балансе"
    )


# --- ЗАПРОСЫ (REQUESTS) ---


class CartValidateRequest(BaseModel):
    """Схема запроса для проверки корзины перед оформлением."""

    inventory_id: uuid.UUID = Field(
        ..., description="ID инвентаря (адреса) клиента"
    )
    items: list[OrderItemCreate] = Field(
        ..., min_length=1, description="Товары в корзине"
    )


class OrderCreate(BaseModel):
    """Схема создания нового заказа клиентом или менеджером."""

    inventory_id: uuid.UUID = Field(
        ..., description="ID инвентаря (адреса) клиента"
    )
    payment_method: PaymentMethod = Field(
        ..., description="Способ оплаты (наличные/карта/и т.д.)"
    )
    items: list[OrderItemCreate] = Field(
        ..., min_length=1, description="Список товаров"
    )
    is_initial_tara: bool = Field(
        default=False,
        description=(
            "Флаг первичного оприходования тары"
            " (если у клиента физически есть бутыли,"
            " но их нет в базе)"
        ),
    )


class OrderDeliveryCompleteRequest(BaseModel):
    """Схема для курьера при завершении заказа."""

    actual_returned_tara: dict[uuid.UUID, int] = Field(
        default_factory=dict,
        description=(
            "Фактически возвращенная тара в формате {tara_id: количество}"
        ),
    )


# --- ОТВЕТЫ (RESPONSES) ---


class CartValidationResponse(BaseModel):
    """Схема ответа на проверку корзины."""

    is_valid: bool = Field(
        ..., description="Можно ли оформить заказ с текущей корзиной"
    )
    needs_initial_tara: bool = Field(
        ..., description="Нужно ли предложить клиенту оприходовать тару"
    )
    missing_items: list[MissingTaraDTO] = Field(
        default_factory=list, description="Список недостающей тары"
    )
    message: str | None = Field(
        default=None, description="Человекочитаемое сообщение об ошибке"
    )


class OrderResponse(BaseModel):
    """
    Базовая схема ответа для созданного заказа.
    В будущем сюда можно добавить вложенные items, client, courier.
    """

    id: uuid.UUID
    client_id: uuid.UUID
    client_inventory_id: uuid.UUID
    payment_method: PaymentMethod
    status: str
    total_amount: float  # Или Decimal

    model_config = ConfigDict(from_attributes=True)
