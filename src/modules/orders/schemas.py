# src/modules/orders/schemas.py
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.modules.catalog.schemas import ProductResponse
from src.modules.inventory.enums import InventoryType
from src.modules.inventory.schemas import TransferResponse
from src.modules.orders.enums import OrderStatus, PaymentMethod, SaleType
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
    capitalize_missing_tara: bool = Field(
        default=False,
        title="Оприходовать недостающую тару",
        description=(
            "Если True — система автоматически оприходует дефицит тары "
            "перед созданием заказа (INITIAL_BALANCE)."
        ),
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        title="Заметки к доставке",
        description=(
            "Инструкции для курьера: код домофона, этаж, время доставки и т.д."
        ),
    )


class OrderAssignCourierRequest(BaseModel):
    """Схема для диспетчера: назначить курьера на заказ."""

    courier_id: uuid.UUID = Field(..., title="ID Курьера")


class OrderStatusUpdateRequest(BaseModel):
    """Схема для курьера: изменить статус заказа (например, на DELIVERED)."""

    status: OrderStatus = Field(..., title="Новый статус заказа")


class CancelOrderRequest(BaseModel):
    """Запрос на отмену заказа (клиент или бэкофис)."""

    reason: str | None = Field(
        default=None,
        max_length=500,
        title="Причина отмены",
        description="Опциональная причина отмены заказа",
    )


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


class TaraCheckRequest(BaseModel):
    """Запрос на проверку доступности тары перед оформлением заказа."""

    items: list[Item] = Field(..., min_length=1)
    client_inventory_id: uuid.UUID = Field(
        ...,
        title="ID адреса клиента",
    )


class TaraShortage(BaseModel):
    product_id: uuid.UUID
    product_name: str
    returnable_item_id: uuid.UUID
    required: int
    available: int
    deficit: int


class TaraCheckResponse(BaseModel):
    """Результат проверки тары: можно ли оформить заказ."""

    can_order: bool = Field(
        description="Можно ли оформить заказ с текущей тарой"
    )
    shortages: list[TaraShortage] = Field(
        default_factory=list,
        description="Список нехваток тары (пуст, если can_order=true)",
    )


class WarehouseSaleCreate(BaseModel):
    """Создание заказа на самовывоз со склада."""

    warehouse_id: uuid.UUID = Field(
        ..., description="ID склада, с которого продаём"
    )
    items: list[Item] = Field(..., min_length=1, title="Корзина товаров")
    capitalize_missing_tara: bool = Field(
        default=False,
        title="Оприходовать недостающую тару",
    )


class WarehouseSaleCapitalizeTaraRequest(BaseModel):
    """Оприходование тары, принесённой покупателем на склад."""

    warehouse_id: uuid.UUID = Field(
        ..., description="ID склада (для контекста)"
    )
    items: list[Item] = Field(
        ..., min_length=1, description="Тара, принесённая покупателем"
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
    payment_method: PaymentMethod
    total_amount: int
    capitalization_applied: bool = Field(
        default=False,
        description=(
            "True, если при создании заказа было выполнено "
            "авто-оприходование недостающей тары (INITIAL_BALANCE)."
        ),
    )
    sale_type: SaleType = Field(
        default=SaleType.DELIVERY,
        description="Тип продажи: delivery или warehouse_pickup",
    )
    warehouse_id: uuid.UUID | None = Field(
        default=None,
        description="ID склада (только для самовывоза)",
    )
    contract_id: uuid.UUID | None = Field(
        default=None,
        description="ID договора (только для CONTRACT оплаты)",
    )
    notes: str | None = Field(
        default=None,
        description="Инструкции по доставке",
    )
    cancellation_reason: str | None = Field(
        default=None,
        description="Причина отмены (если статус CANCELLED)",
    )

    items: list[OrderItemResponse]
    stock_transfers: list[TransferResponse] = []

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrdersResponse(BaseModel):
    """Постраничный список заказов с общим количеством."""

    total_count: int
    orders: list[OrderResponse]
