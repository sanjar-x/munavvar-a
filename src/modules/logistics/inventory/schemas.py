import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.modules.catalog.models import ProductType
from src.modules.logistics.inventory.enums import InventoryType

# =====================================================================
# 1. СКЛАДЫ / ТОЧКИ УЧЕТА (INVENTORY)
# =====================================================================


class InventoryBase(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        title="Название точки учета",
        examples=["Главный Склад", "Машина Курьера 01A123BC"],
    )
    type: InventoryType = Field(
        ..., title="Тип склада", examples=[InventoryType.COURIER_CAR]
    )


class InventoryCreate(InventoryBase):
    """Создание новой точки учета"""

    user_id: uuid.UUID = Field(
        ...,
        title="Ответственное лицо",
        description="ID пользователя (кладовщика, курьера, клиента)",
    )


class InventoryUpdate(BaseModel):
    """Обновление склада. Тип и user_id менять нельзя"""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    is_active: bool | None = Field(default=None)


class InventoryResponse(InventoryBase):
    """Выдача информации о складе клиенту/фронтенду."""

    id: uuid.UUID
    user_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =====================================================================
# 2. СКЛАДСКИЕ ПРОВОДКИ (STOCK TRANSACTIONS)
# =====================================================================


class StockTransactionCreate(BaseModel):
    """
    Ручное перемещение товаров (Например: Кладовщик грузит машину курьера).
    Для заказов эта схема не используется
    """

    from_id: uuid.UUID = Field(..., title="Склад-отправитель")
    to_id: uuid.UUID = Field(..., title="Склад-получатель")
    product_id: uuid.UUID = Field(..., title="ID Товара (SKU)")
    quantity: int = Field(
        ...,
        gt=0,  # Строгая защита: нельзя переместить 0 или -5 бутылок!
        title="Количество",
        examples=[50],
    )
    # Ручные перемещения не привязаны к заказу, поэтому order_id здесь нет.


class StockTransactionResponse(BaseModel):
    """История движений (Отчет для бухгалтерии и кладовщиков)."""

    id: uuid.UUID
    from_id: uuid.UUID
    to_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    order_id: uuid.UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =====================================================================
# 3. АНАЛИТИКА / БАЛАНСЫ (INVENTORY BALANCES)
# =====================================================================


class InventoryBalanceResponse(BaseModel):
    """
    DTO для нашего ультра-оптимизированного DBA SQL-запроса.
    Выводит актуальные остатки конкретного склада.
    """

    product_id: uuid.UUID
    product_name: str = Field(title="Название товара")
    product_type: ProductType = Field(title="Тип (вода, тара, оборудование)")
    product_attributes: dict[str, Any] = Field(
        title="Свойства", description="JSONB: Литраж, материал и т.д."
    )
    balance: int = Field(title="Остаток", description="Сумма всех транзакций")

    # from_attributes здесь не обязателен, т.к. наш SQL запрос возвращает
    # RowMapping (словарь), который Pydantic легко парсит и так.
