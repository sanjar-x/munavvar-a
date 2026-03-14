# src/modules/inventory/schemas.py
import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.modules.catalog.schemas import ProductResponse
from src.modules.inventory.enums import InventoryType, TransferStatus, TransferType
from src.modules.users.schemas import UserResponse


class InventoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: InventoryType
    user: UserResponse
    is_active: bool


class InventoryBalance(BaseModel):
    quantity: int
    product: ProductResponse


class InventoriesResponse(BaseModel):
    inventory: InventoryResponse
    balances: list[InventoryBalance]


class CreateLocation(BaseModel):
    name: str = Field(
        ...,
        description="'Газель 01A123BC', 'Завод №1'",
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


class DraftTransferRequest(BaseModel):
    """Запрос на создание или пополнение черновика накладной."""

    from_id: uuid.UUID = Field(description="ID склада отправителя")
    to_id: uuid.UUID = Field(description="ID склада/машины получателя")
    items: list[Item] = Field(min_length=1, description="Список товаров")


class CompleteTransferRequest(BaseModel):
    """Запрос на проведение существующего черновика."""

    transfer_id: uuid.UUID


class VendorReceiptRequest(BaseModel):
    """Оприходование новой тары от поставщика пластика."""

    warehouse_id: uuid.UUID
    items: list[Item] = Field(min_length=1)


class FactoryRefillRequest(BaseModel):
    """Специальный запрос для магии HOD: Розлив воды в пустую тару."""

    warehouse_id: uuid.UUID
    factory_id: uuid.UUID = Field(description="ID Завода (Скважины)")
    water_id: uuid.UUID = Field(description="ID продукта 'Вода' (сырье)")
    bottle_id: uuid.UUID = Field(description="ID продукта 'Пустая бутыль' (тара)")
    quantity: int = Field(gt=0, description="Сколько бутылей воды разлито")


class InventoryAdjustmentRequest(BaseModel):
    """Внесение результатов инвентаризации (излишки и недостачи)."""

    warehouse_id: uuid.UUID
    items: list[AdjustmentItem] = Field(min_length=1)


# ==========================================
# 3. ЗАПРОСЫ: ЛОГИСТИКА И ИНКАССАЦИЯ (COURIER SHIFT)
# ==========================================


class LoadCourierTruckRequest(BaseModel):
    """Утренняя загрузка машины курьера."""

    route_sheet_id: uuid.UUID = Field(
        description="Связь с маршрутным листом из модуля Логистики"
    )
    warehouse_id: uuid.UUID
    courier_inventory_id: uuid.UUID
    items: list[Item] = Field(min_length=1)


class CloseShiftRequest(BaseModel):
    """Вечерняя сдача смены курьером (Инкассация тары)."""

    route_sheet_id: uuid.UUID
    warehouse_id: uuid.UUID = Field(description="Склад, на который сдается факт")
    actual_full_water: int = Field(ge=0, description="Факт: нераспроданная полная вода")
    actual_empty_bottles: int = Field(ge=0, description="Факт: собранные пустые бутыли")
    actual_equipment: list[Item] = Field(
        default_factory=list,
        description="Остальное оборудование (кулеры, помпы)",
    )


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


class StockTransactionResponse(BaseModel):
    """Строка Леджера (фактическое движение)"""

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    from_id: uuid.UUID
    to_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UpdateItemQuantityDto(BaseModel):
    """Для изменения количества товара кладовщиком в DRAFT"""

    quantity: int = Field(gt=0)


# --- ТРАНСПОРТ (BACKOFFICE) ---


class ProductSimpleResponse(BaseModel):
    id: uuid.UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class BalanceResponse(BaseModel):
    product: ProductSimpleResponse
    quantity: int

    model_config = ConfigDict(from_attributes=True)


class TransportCreate(BaseModel):
    user_id: uuid.UUID = Field(
        ..., description="ID курьера, ответственного за транспорт"
    )
    name: str = Field(
        ..., max_length=255, description="Название транспорта (напр. 'Машина АВ123')"
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


class TransferCreate(BaseModel):
    from_id: uuid.UUID
    to_id: uuid.UUID
    type: TransferType


class TransferItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(..., gt=0)


class TransferCompleteRequest(BaseModel):
    accepted_by_id: uuid.UUID = Field(..., description="Кто физически принял товар")


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

    model_config = ConfigDict(from_attributes=True)
