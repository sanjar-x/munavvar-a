# src/modules/orders/schemas.py
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.modules.catalog.schemas import ProductResponse
from src.modules.inventory.enums import InventoryType
from src.modules.inventory.schemas import TransferResponse
from src.modules.orders.enums import OrderStatus, PaymentMethod
from src.modules.users.schemas import UserResponse


class Item(BaseModel):
    product_id: uuid.UUID = Field(
        ...,
        description="ID воды, тары или оборудования из каталога",
    )
    quantity: int = Field(
        ...,
        gt=0,  # Строгая валидация: количество должно быть больше 0!
        title="Количество",
        examples=[2],
    )


class OrderCreate(BaseModel):
    items: list[Item] = Field(
        ...,
        min_length=1,
        title="Корзина товаров",
    )
    payment_method: PaymentMethod = Field(
        ...,
        title="Способ оплаты",
        description="Намерение клиента по оплате: Наличные, Карта ",
        examples=[PaymentMethod.CASH],
    )
    client_inventory_id: uuid.UUID = Field(
        ...,
        title="ID адреса клиента",
        description="Инвентарь клиента, куда будет доставлен заказ",
    )


class OrderAssignCourierRequest(BaseModel):
    """Схема для диспетчера: назначить курьера на заказ."""

    courier_id: uuid.UUID = Field(..., title="ID Курьера")


class OrderStatusUpdateRequest(BaseModel):
    """Схема для курьера: изменить статус заказа (например, на DELIVERED)."""

    status: OrderStatus = Field(..., title="Новый статус заказа")


class OrderItemActual(BaseModel):
    """Фактически доставленное количество товара."""

    product_id: uuid.UUID
    quantity: int = Field(ge=0)


class OrderDeliverRequest(BaseModel):
    """Запрос курьера на завершение доставки с возможной корректировкой."""

    actual_items: list[OrderItemActual] | None = Field(
        default=None,
        description="Фактический состав (если отличается от заказа)",
    )


# =====================================================================
# 3. СХЕМЫ ОТВЕТОВ (RESPONSES)
# =====================================================================


class OrderItemResponse(BaseModel):
    """Как выглядит одна позиция в заказе при выдаче клиенту."""

    id: uuid.UUID
    product_id: uuid.UUID
    product: ProductResponse
    quantity: int = Field(description="Количество")
    unit_price: int = Field(description="Историческая цена на момент покупки")
    total: int = Field(description="quantity * unit_price")

    model_config = ConfigDict(from_attributes=True)


class InventoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: InventoryType
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    """Полная модель заказа для Личного Кабинета или Дашборда."""

    id: uuid.UUID
    client_id: uuid.UUID
    client: UserResponse
    client_inventory_id: uuid.UUID
    client_inventory: InventoryResponse
    courier_id: uuid.UUID | None = None
    courier: UserResponse | None = None
    status: OrderStatus
    total_amount: int

    items: list[OrderItemResponse]
    stock_transfers: list[TransferResponse] = []

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
