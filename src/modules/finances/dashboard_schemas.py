# src/modules/finances/dashboard_schemas.py
"""Pydantic-схемы ответов для Dashboard API — домен Finance."""

import uuid
from datetime import date

from pydantic import BaseModel, Field

# --- EP-8: Динамика выручки (BR-6) ---


class RevenueTrendPoint(BaseModel):
    period: str = Field(
        description="2026-03-15 | 2026-W12 | 2026-03",
    )
    revenue: int = Field(description="Тийины")
    orders_count: int


class RevenueTrendResponse(BaseModel):
    """EP-8: Временной ряд выручки."""

    points: list[RevenueTrendPoint]
    total_revenue: int
    total_orders: int
    change_percent: float | None = Field(
        default=None,
        description="% vs аналогичный предыдущий период",
    )


# --- EP-9: Aging-бакеты дебиторки (BR-7) ---


class AgingBucket(BaseModel):
    label: str = Field(description="0-7 дней и т.д.")
    min_days: int
    max_days: int | None = Field(
        default=None,
        description="None для 60+",
    )
    clients_count: int
    total_amount: int = Field(description="Тийины")


class DebtAgingResponse(BaseModel):
    """EP-9: Aging-бакеты."""

    buckets: list[AgingBucket]
    total_debt: int
    total_debtors: int


# --- EP-10: Топ должников (BR-8) ---


class TopDebtorItem(BaseModel):
    client_id: uuid.UUID
    client_name: str
    client_type: str = Field(
        description="client_b2c | client_b2b",
    )
    phone: str | None = None
    debt_amount: int = Field(description="Тийины")
    last_payment_date: date | None = None
    days_overdue: int


class TopDebtorsResponse(BaseModel):
    """EP-10: Топ должников."""

    debtors: list[TopDebtorItem]
    total_debt: int


# --- EP-12: Финансовые KPI (BR-9) ---


class FinanceSummaryKPIs(BaseModel):
    """EP-12: Расчётные финансовые метрики."""

    avg_order_value: int = Field(
        description="Тийины (AOV)",
    )
    total_orders: int
    total_revenue: int = Field(description="Тийины")

    card_confirmation_rate: float = Field(
        description="0.0-1.0",
    )
    card_rejection_rate: float = Field(
        description="0.0-1.0",
    )
    avg_card_confirmation_hours: float | None = None

    collection_rate: float = Field(
        description="0.0-1.0 сдано/собрано",
    )
    overdue_debt_ratio: float = Field(
        description="0.0-1.0 долг>7д / общий долг",
    )


# --- EP-21: Выручка B2B/B2C (BR-20) ---


class SegmentRevenue(BaseModel):
    segment: str = Field(
        description="client_b2b | client_b2c",
    )
    orders_count: int
    total_revenue: int = Field(description="Тийины")
    avg_order_value: int = Field(description="Тийины")


class RevenueBySegmentResponse(BaseModel):
    """EP-21: Выручка по сегментам."""

    segments: list[SegmentRevenue]
    total_orders: int
    total_revenue: int


# --- EP-11: Способы оплаты — фин. призма (BR-5) ---


class PaymentMethodFinanceStats(BaseModel):
    method: str = Field(
        description="cash | card | contract",
    )
    transactions_count: int
    total_amount: int = Field(description="Тийины")


class PaymentMethodsFinanceResponse(BaseModel):
    """EP-11: Финансовая разбивка по способам оплаты."""

    methods: list[PaymentMethodFinanceStats]
