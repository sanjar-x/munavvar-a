# src/application/courier/schemas.py
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- ЗАПРОСЫ (REQUESTS) ---


class CourierCreate(BaseModel):
    username: str = Field(..., description="ФИО курьера")
    phone: str = Field(..., description="Номер телефона курьера (будет Identity)")
    password: str = Field(
        ..., description="Пароль курьера (в открытом виде, будет захэширован)"
    )


class CourierUpdate(BaseModel):
    username: str | None = Field(default=None, description="ФИО курьера")
    phone: str | None = Field(default=None, description="Новый номер телефона")
    password: str | None = Field(default=None, description="Новый пароль")
    is_active: bool | None = Field(
        default=None, description="Статус курьера (уволен/работает)"
    )


# --- ВСПОМОГАТЕЛЬНЫЕ DTO ДЛЯ ОТВЕТА (ИСПРАВЛЕНИЕ ОШИБКИ) ---


class AccountShortDTO(BaseModel):
    """Схема для сериализации финансового счета"""

    id: uuid.UUID
    name: str
    balance: int
    model_config = ConfigDict(from_attributes=True)


class InventoryShortDTO(BaseModel):
    """Схема для сериализации инвентаря (машины)"""

    id: uuid.UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


# --- ВЛОЖЕННЫЕ СХЕМЫ (ДЛЯ ОТВЕТОВ) ---


class CourierInventoryWithBalancesDTO(InventoryShortDTO):
    balances: list[Any]
    model_config = ConfigDict(from_attributes=True)


# --- ОТВЕТЫ (RESPONSES) ---
class Courier(BaseModel):
    """Схема одного курьера для выдачи в списке (без глубоких связей)"""

    id: uuid.UUID
    username: str
    phone: str | None
    account: AccountShortDTO | None  # УБРАЛИ Any, теперь Pydantic знает как парсить!
    inventory: InventoryShortDTO | None  # УБРАЛИ Any!
    is_active: bool
    orders: int = Field(description="Количество выполненных заказов")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CouriersResponse(BaseModel):
    """Схема ответа для эндпоинта списка курьеров с пагинацией"""

    total_count: int
    couriers: list[Courier]


class CourierResponse(BaseModel):
    """Полная карточка курьера для детального просмотра"""

    id: uuid.UUID
    username: str
    phone: str | None
    is_active: bool
    account: AccountShortDTO | None  # УБРАЛИ Any
    inventory: CourierInventoryWithBalancesDTO | None
    orders: list[
        Any
    ]  # Если заказы тоже падают с такой же ошибкой, их тоже нужно описать через DTO!

    model_config = ConfigDict(from_attributes=True)
