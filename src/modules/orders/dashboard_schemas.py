# src/modules/orders/dashboard_schemas.py
"""Pydantic-схемы ответов для Dashboard API — домен Orders."""

import uuid

from pydantic import BaseModel, Field


class OrderStatusCount(BaseModel):
    status: str = Field(description="OrderStatus value")
    count: int


class OrdersSummary(BaseModel):
    """EP-1: Операционная сводка (BR-1)."""

    # Активные заказы (незавершённые, все даты)
    active_by_status: list[OrderStatusCount] = Field(
        description=(
            "Количество заказов в незавершённых статусах: "
            "new, assigned, in_transit, arrived"
        ),
    )
    unassigned_orders: int = Field(
        description=(
            "NEW delivery-заказы без курьера — "
            "ключевой показатель для диспетчера"
        ),
    )

    # Статистика за сегодня
    total_today: int
    delivered_today: int
    cancelled_today: int
    revenue_today: int = Field(
        description="сум, сумма завершённых сегодня",
    )
    by_sale_type: dict[str, int] = Field(
        description='{"delivery": N, "warehouse_pickup": N}',
    )

    # Ресурсы
    active_couriers: int


# --- EP-5: Разбивка способов оплаты (BR-5) ---


class PaymentMethodStats(BaseModel):
    method: str = Field(
        description="cash | card | contract",
    )
    orders_count: int
    total_amount: int = Field(description="сум")


class PaymentBreakdownResponse(BaseModel):
    """EP-5: Разбивка по способам оплаты."""

    methods: list[PaymentMethodStats]
    total_orders: int
    total_amount: int


# --- EP-2: Тренд заказов (BR-2) ---


class OrderTrendPoint(BaseModel):
    period: str
    orders_count: int
    revenue: int = Field(description="сум")
    avg_order_value: int = Field(description="сум")


class OrderTrendResponse(BaseModel):
    """EP-2: Временной ряд заказов."""

    points: list[OrderTrendPoint]
    total_orders: int
    total_revenue: int


# --- EP-3: Воронка статусов (BR-3) ---


class StatusFunnelItem(BaseModel):
    status: str
    count: int
    percentage: float = Field(description="0.0-1.0")


class OrderFunnelResponse(BaseModel):
    """EP-3: Распределение по текущему статусу."""

    total: int
    statuses: list[StatusFunnelItem]


# --- EP-4: Тепловая карта (BR-4) ---


class HeatmapCell(BaseModel):
    day_of_week: int = Field(
        description="1=Пн..7=Вс (ISO 8601)",
    )
    hour: int = Field(description="0-23")
    count: int


class OrderHeatmapResponse(BaseModel):
    """EP-4: Тепловая карта заказов."""

    cells: list[HeatmapCell]
    max_count: int


# --- EP-7: Топ клиентов (BR-16) ---


class TopClientItem(BaseModel):
    client_id: uuid.UUID
    client_name: str
    client_type: str = Field(
        description="client_b2c | client_b2b",
    )
    orders_count: int
    total_amount: int = Field(description="сум")


class TopClientsResponse(BaseModel):
    """EP-7: Топ клиентов по заказам."""

    clients: list[TopClientItem]
