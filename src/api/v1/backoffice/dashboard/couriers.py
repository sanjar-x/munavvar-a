# src/api/v1/backoffice/dashboard/couriers.py
"""Dashboard API — Courier Fleet (EP-17, EP-20)."""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.backoffice.dashboard import month_ago
from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.infrastructure.database.session import (
    get_session,
)
from src.modules.auth.dependencies import get_current_user
from src.modules.users.dashboard_queries import (
    CourierDashboardQueries,
)
from src.modules.users.dashboard_schemas import (
    CourierFleetResponse,
    CourierLoadResponse,
)

couriers_dashboard_router = APIRouter()


async def get_courier_dashboard_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CourierDashboardQueries:
    return CourierDashboardQueries(session)


@couriers_dashboard_router.get(
    "/couriers/fleet",
    response_model=CourierFleetResponse,
)
async def get_courier_fleet(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.USERS_READ],
        ),
    ],
    queries: Annotated[
        CourierDashboardQueries,
        Depends(get_courier_dashboard_queries),
    ],
) -> CourierFleetResponse:
    """EP-17: Карточки курьеров (BR-14)."""
    return await queries.get_fleet()


@couriers_dashboard_router.get(
    "/couriers/load-by-days",
    response_model=CourierLoadResponse,
)
async def get_courier_load(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.USERS_READ],
        ),
    ],
    queries: Annotated[
        CourierDashboardQueries,
        Depends(get_courier_dashboard_queries),
    ],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> CourierLoadResponse:
    """EP-20: Загрузка курьеров по дням (BR-19)."""
    today = date.today()
    return await queries.get_courier_load(
        date_from=(date_from or today - timedelta(days=30)),
        date_to=date_to or today,
    )
