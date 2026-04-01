# src/modules/inventory/dashboard_schemas.py
"""Pydantic-схемы ответов для Dashboard API — домен Inventory."""

import uuid

from pydantic import BaseModel, Field

# --- EP-13: Складская сводка (BR-10) ---


class InventorySummary(BaseModel):
    """EP-13: Агрегированные KPI по складскому учёту."""

    total_water_stock: int = Field(
        description="Полные бутыли на складах + курьерах",
    )
    total_container_stock: int = Field(
        description="Пустые бутыли на складах + курьерах",
    )
    total_equipment_stock: int = Field(
        description="Оборудование на складах + курьерах",
    )
    containers_at_clients: int = Field(
        description="Тара у клиентов",
    )
    stock_on_couriers: int = Field(
        description="Всего единиц товара на курьерах",
    )
    losses_today: int = Field(
        description="Списания за сегодня (единиц)",
    )
    active_couriers_count: int


# --- EP-14: Распределение тары (BR-11) ---


class ContainerProductBreakdown(BaseModel):
    """Разбивка по конкретному продукту-таре."""

    product_id: uuid.UUID
    product_name: str
    at_warehouses: int = 0
    at_couriers: int = 0
    at_clients: int = 0
    lost: int = 0
    total: int = 0


class ContainerDistribution(BaseModel):
    """EP-14: Разбивка тары по местоположению."""

    at_warehouses: int
    at_couriers: int
    at_clients: int
    lost: int = Field(description="VIRTUAL_LOSS balance")
    total_in_system: int = Field(
        description="|VIRTUAL_VENDOR| — всего введено",
    )
    per_product: list[ContainerProductBreakdown]


# --- EP-19: Виртуальные счета + целостность (BR-18) ---


class VirtualProductBalance(BaseModel):
    product_id: uuid.UUID
    product_name: str
    vendor_balance: int = Field(
        description="Отрицательный (VIRTUAL_VENDOR)",
    )
    loss_balance: int = Field(
        description="Положительный (VIRTUAL_LOSS)",
    )


class LossTrendPoint(BaseModel):
    date: str
    quantity: int


class VirtualAccountsResponse(BaseModel):
    """EP-19: Баланс виртуальных счетов + контроль."""

    vendor_total: int = Field(
        description="ABS(SUM VIRTUAL_VENDOR)",
    )
    loss_total: int = Field(
        description="SUM VIRTUAL_LOSS",
    )
    real_total: int = Field(
        description="SUM (WAREHOUSE + COURIER + CLIENT)",
    )
    integrity_ok: bool = Field(
        description=("vendor_total == loss_total + real_total"),
    )
    integrity_diff: int = Field(
        description="Разница (0 если ok)",
    )
    per_product: list[VirtualProductBalance]
    loss_trend_30d: list[LossTrendPoint] = Field(
        default_factory=list,
        description="Потери по дням за 30 дней",
    )


# --- EP-15: Должники по таре (BR-12) ---


class ContainerDebtorItem(BaseModel):
    client_id: uuid.UUID
    client_name: str
    client_type: str
    container_balance: int
    last_order_date: str | None = None
    days_since_last_order: int | None = None


class ContainerDebtorsResponse(BaseModel):
    """EP-15: Должники по таре."""

    debtors: list[ContainerDebtorItem]
    total_containers_at_clients: int


# --- EP-16: Статистика перемещений (BR-13) ---


class MovementTypeStats(BaseModel):
    transfer_type: str
    transfers_count: int
    total_items: int


class MovementStatsResponse(BaseModel):
    """EP-16: Статистика перемещений."""

    types: list[MovementTypeStats]
    total_transfers: int
    total_items: int


# --- EP-18: Тренды остатков (BR-17) ---


class InventoryTrendPoint(BaseModel):
    date: str
    water_stock: int
    container_stock: int
    containers_at_clients: int


class InventoryTrendResponse(BaseModel):
    """EP-18: Временной ряд остатков."""

    points: list[InventoryTrendPoint]
