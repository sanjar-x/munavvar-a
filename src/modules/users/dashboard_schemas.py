# src/modules/users/dashboard_schemas.py
"""Pydantic-схемы ответов для Dashboard API — домен Couriers."""

import uuid

from pydantic import BaseModel, Field

# --- EP-17: Дашборд курьеров (BR-14) ---


class CourierVehicleBalance(BaseModel):
    product_id: uuid.UUID
    product_name: str
    quantity: int


class CourierFleetCard(BaseModel):
    """Карточка одного курьера."""

    courier_id: uuid.UUID
    courier_name: str
    vehicle_id: uuid.UUID | None = None
    vehicle_name: str | None = None
    is_active: bool = Field(
        description="Есть ли активный транспорт",
    )
    vehicle_balances: list[CourierVehicleBalance] = Field(
        default_factory=list,
    )
    orders_assigned_today: int = 0
    orders_delivered_today: int = 0
    cash_balance: int = Field(
        default=0,
        description="Тийины — баланс кассы курьера",
    )
    cash_collected_today: int = Field(
        default=0,
        description="Тийины — собрано за сегодня",
    )
    containers_collected_today: int = Field(
        default=0,
        description="Тара, собранная у клиентов сегодня",
    )


class CourierFleetResponse(BaseModel):
    """EP-17: Карточки всех курьеров."""

    couriers: list[CourierFleetCard]
    total_active: int
    total_stock_on_couriers: int
    total_courier_cash: int = Field(
        description="Тийины",
    )


# --- EP-20: Загрузка курьеров по дням (BR-19) ---


class CourierDayLoad(BaseModel):
    date: str
    courier_id: uuid.UUID
    courier_name: str
    deliveries_count: int


class CourierLoadResponse(BaseModel):
    """EP-20: Загрузка курьеров по дням."""

    data: list[CourierDayLoad]
    total_deliveries: int
    avg_per_courier: float
    max_load: int
