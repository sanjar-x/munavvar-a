# src/modules/inventory/schemas.py
import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.modules.catalog.enums import ProductType
from src.modules.catalog.schemas import ProductResponse
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.users.schemas import UserResponse


class InventoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: InventoryType
    user: UserResponse
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class InventoryBalance(BaseModel):
    quantity: int
    product: ProductResponse


class InventoriesResponse(BaseModel):
    inventory: InventoryResponse
    balances: list[InventoryBalance]


class CreateLocation(BaseModel):
    name: str = Field(
        ...,
        description="'Газель 01A123BC', 'Склад №1'",
    )
    type: InventoryType
    user_id: uuid.UUID = Field(description="Владелец (Клиент или Курьер)")


class InventoryBalanceResponse(BaseModel):
    """
    Модель для отображения остатков конкретного товара на складе.
    Используется для построения ведомости текущих остатков.
    """

    product_id: uuid.UUID
    balance: int

    model_config = ConfigDict(from_attributes=True)


class Item(BaseModel):
    """Стандартная единица измерения передачи товара."""

    product_id: uuid.UUID
    quantity: int = Field(gt=0, description="Количество товара (строго больше нуля)")


class AdjustmentItem(BaseModel):
    """Единица корректировки при инвентаризации."""

    product_id: uuid.UUID
    delta: int = Field(
        description="Положительное число = излишек, Отрицательное = недостача."
    )

    @model_validator(mode="after")
    def validate_delta_not_zero(self) -> Self:
        if self.delta == 0:
            raise ValueError("Корректировка (delta) не может быть равна нулю")
        return self


# ==========================================
# 2. ЗАПРОСЫ: СКЛАД И ПРОИЗВОДСТВО (WAREHOUSE COMMANDS)
# ==========================================


class VendorReceiptRequest(BaseModel):
    """Оприходование новой тары от поставщика пластика."""

    warehouse_id: uuid.UUID
    items: list[Item] = Field(min_length=1)


class InventoryAdjustmentRequest(BaseModel):
    """Внесение результатов инвентаризации (излишки и недостачи)."""

    warehouse_id: uuid.UUID
    items: list[AdjustmentItem] = Field(min_length=1)


# ==========================================
# 3. ЗАПРОСЫ: ЛОГИСТИКА И ИНКАССАЦИЯ (COURIER SHIFT)
# ==========================================


class CloseShiftRequest(BaseModel):
    """Вечерняя сдача смены курьером (Инкассация и возврат остатков)."""

    courier_id: uuid.UUID
    returned_inventory: list[Item]
    cash_collected: float = Field(ge=0, description="Сумма собранных наличных")


# Типы, для которых from_id вычисляется автоматически (VIRTUAL_VENDOR)
_VIRTUAL_SOURCE_TYPES = {
    TransferType.INVENTORY_FINDING,
    TransferType.INITIAL_BALANCE,
}
# Типы, для которых to_id вычисляется автоматически (VIRTUAL_LOSS)
_VIRTUAL_DEST_TYPES = {
    TransferType.LOSS_WRITE_OFF,
}


class CreateTransferRequest(BaseModel):
    """Единый запрос на создание и проведение накладной (single-step)."""

    type: TransferType
    from_id: uuid.UUID | None = Field(
        None, description="ID склада-отправителя (авто для INVENTORY_FINDING, INITIAL_BALANCE)"
    )
    to_id: uuid.UUID | None = Field(
        None, description="ID склада-получателя (авто для LOSS_WRITE_OFF)"
    )
    items: list[Item] = Field(min_length=1, description="Список товаров")
    reason: str | None = Field(
        None, min_length=3, max_length=255,
        description="Причина списания (обязательно для LOSS_WRITE_OFF)",
    )
    route_sheet_id: uuid.UUID | None = Field(
        None, description="ID маршрутного листа (для COURIER_LOAD)"
    )

    @model_validator(mode="after")
    def validate_ids_and_reason(self) -> Self:
        if self.type not in _VIRTUAL_SOURCE_TYPES and self.from_id is None:
            raise ValueError(f"from_id обязателен для типа {self.type}")
        if self.type not in _VIRTUAL_DEST_TYPES and self.to_id is None:
            raise ValueError(f"to_id обязателен для типа {self.type}")
        if self.type == TransferType.LOSS_WRITE_OFF and not self.reason:
            raise ValueError("reason обязателен для LOSS_WRITE_OFF")
        return self


# ==========================================
# 4. ОТВЕТЫ API (RESPONSES)
# ==========================================


class TransferResult(BaseModel):
    """Универсальный ответ при мутации накладных."""

    transfer_id: uuid.UUID
    status: TransferStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ShiftReconciliationResponse(BaseModel):
    """Ответ системы с планом (ожиданиями) для инкассации."""

    route_sheet_id: uuid.UUID
    courier_inventory_id: uuid.UUID
    expected_full_water: int
    expected_empty_bottles: int
    expected_equipment: list[Item]

    # Можно добавить расчетные суммы, если сервис знает цены
    # expected_cash: Decimal

    model_config = ConfigDict(from_attributes=True)


class StockTransferResponse(BaseModel):
    """
    Полная модель накладной (с агрегацией).
    Используется в StockTransferService для отдачи на фронтенд.
    """

    id: uuid.UUID
    type: TransferType
    status: TransferStatus
    from_id: uuid.UUID
    to_id: uuid.UUID
    created_by_id: uuid.UUID
    accepted_by_id: uuid.UUID | None
    order_id: uuid.UUID | None
    created_at: datetime

    # Вложенные отношения (загружаются через selectinload в репозитории)
    items: list[StockTransferItemResponse] = Field(default_factory=list)
    transactions: list[StockTransactionResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# src/modules/inventory/schemas.py


# --- МОДЕЛИ ДЛЯ ОТВЕТОВ API (RESPONSES) ---


class StockTransferItemResponse(BaseModel):
    """Товар в корзине (черновике)"""

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int

    model_config = ConfigDict(from_attributes=True)


class ProductSimpleResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: ProductType

    model_config = ConfigDict(from_attributes=True)


class StockTransactionResponse(BaseModel):
    """Строка Леджера (фактическое движение)"""

    id: uuid.UUID
    product_id: uuid.UUID
    product: ProductSimpleResponse
    quantity: int
    from_id: uuid.UUID
    to_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UpdateItemQuantityDto(BaseModel):
    """Для изменения количества товара кладовщиком в DRAFT"""

    quantity: int = Field(gt=0)


# --- ОПРИХОДОВАНИЕ ТАРЫ (CAPITALIZATION) ---


class CapitalizeTaraItem(BaseModel):
    """Позиция оприходования: ID тары и количество."""

    product_id: uuid.UUID = Field(description="ID возвратной тары (пустая бутыль)")
    quantity: int = Field(gt=0, description="Количество единиц тары")


class CapitalizeTaraRequest(BaseModel):
    """Запрос на оприходование тары (Backoffice — без лимитов)."""

    client_inventory_id: uuid.UUID = Field(description="ID адреса клиента")
    items: list[CapitalizeTaraItem] = Field(min_length=1)


class CapitalizeDeficitRequest(BaseModel):
    """
    Запрос от клиента на оприходование дефицита тары.
    Система сама рассчитает необходимое количество.
    """

    items: list[Item] = Field(
        min_length=1,
        description="Корзина товаров (как при оформлении заказа)",
    )
    client_inventory_id: uuid.UUID = Field(description="ID адреса клиента")


class CapitalizeTaraResponse(BaseModel):
    """Результат оприходования тары."""

    transfer_id: uuid.UUID
    capitalized_items: list[CapitalizeTaraItem]

    model_config = ConfigDict(from_attributes=True)


# --- ТРАНСПОРТ (BACKOFFICE) ---


class BalanceResponse(BaseModel):
    product: ProductSimpleResponse
    quantity: int

    model_config = ConfigDict(from_attributes=True)


class TransportCreate(BaseModel):
    user_id: uuid.UUID = Field(
        ..., description="ID курьера, ответственного за транспорт"
    )
    name: str = Field(
        ...,
        max_length=255,
        description="Название транспорта (напр. 'Машина АВ123')",
    )


class TransportUpdate(BaseModel):
    user_id: uuid.UUID | None = Field(None, description="Новый ответственный курьер")
    name: str | None = Field(None, max_length=255, description="Новое название")


class TransportResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    type: str = "COURIER"

    model_config = ConfigDict(from_attributes=True)


class TransportDetailResponse(TransportResponse):
    balances: list[BalanceResponse] = []


# --- СКЛАДЫ (WAREHOUSES) ---


class WarehouseCreate(BaseModel):
    user_id: uuid.UUID = Field(..., description="ID материально ответственного")
    name: str = Field(..., max_length=255)


class BalanceItem(BaseModel):
    product: ProductSimpleResponse
    quantity: int

    model_config = ConfigDict(from_attributes=True)


class WarehouseDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    user_id: uuid.UUID
    balances: list[BalanceItem] = []

    model_config = ConfigDict(from_attributes=True)


# --- НАКЛАДНЫЕ (TRANSFERS) ---


class TransferItemResponse(BaseModel):
    product: ProductSimpleResponse
    quantity: int

    model_config = ConfigDict(from_attributes=True)


class TransferResponse(BaseModel):
    id: uuid.UUID
    from_id: uuid.UUID
    to_id: uuid.UUID
    created_by_id: uuid.UUID
    accepted_by_id: uuid.UUID | None
    status: TransferStatus
    type: TransferType
    items: list[TransferItemResponse] = []
    reason: str | None = None
    route_sheet_id: uuid.UUID | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
