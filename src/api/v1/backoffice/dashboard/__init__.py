# src/api/v1/backoffice/dashboard/__init__.py
"""Dashboard API — агрегатор sub-роутеров."""

from fastapi import APIRouter

from src.api.v1.backoffice.dashboard.couriers import (
    couriers_dashboard_router,
)
from src.api.v1.backoffice.dashboard.finances import (
    finances_dashboard_router,
)
from src.api.v1.backoffice.dashboard.inventory import (
    inventory_dashboard_router,
)
from src.api.v1.backoffice.dashboard.orders import (
    orders_dashboard_router,
)

dashboard_router = APIRouter()

dashboard_router.include_router(orders_dashboard_router)
dashboard_router.include_router(
    finances_dashboard_router,
)
dashboard_router.include_router(
    inventory_dashboard_router,
)
dashboard_router.include_router(
    couriers_dashboard_router,
)
