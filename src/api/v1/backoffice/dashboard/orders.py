# src/api/v1/backoffice/dashboard/orders.py
"""Dashboard API — Orders (EP-1..EP-5, EP-7)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.backoffice.dashboard.utils import month_ago
from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.infrastructure.database.session import (
    get_session,
)
from src.modules.auth.dependencies import get_current_user
from src.modules.orders.dashboard_queries import (
    OrderDashboardQueries,
)
from src.modules.orders.dashboard_schemas import (
    OrderFunnelResponse,
    OrderHeatmapResponse,
    OrdersSummary,
    OrderTrendResponse,
    PaymentBreakdownResponse,
    TopClientsResponse,
)

orders_dashboard_router = APIRouter()


async def get_order_dashboard_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderDashboardQueries:
    return OrderDashboardQueries(session)


@orders_dashboard_router.get(
    "/orders/summary",
    response_model=OrdersSummary,
)
async def get_orders_summary(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.ORDERS_READ],
        ),
    ],
    queries: Annotated[
        OrderDashboardQueries,
        Depends(get_order_dashboard_queries),
    ],
) -> OrdersSummary:
    """EP-1: Операционная сводка (BR-1)."""
    return await queries.get_orders_summary()


@orders_dashboard_router.get(
    "/orders/payment-breakdown",
    response_model=PaymentBreakdownResponse,
)
async def get_payment_breakdown(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.ORDERS_READ],
        ),
    ],
    queries: Annotated[
        OrderDashboardQueries,
        Depends(get_order_dashboard_queries),
    ],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> PaymentBreakdownResponse:
    """EP-5: Разбивка способов оплаты (BR-5)."""
    today = date.today()
    return await queries.get_payment_breakdown(
        date_from=date_from or month_ago(today),
        date_to=date_to or today,
    )


@orders_dashboard_router.get(
    "/orders/trends",
    response_model=OrderTrendResponse,
)
async def get_order_trends(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.ORDERS_READ],
        ),
    ],
    queries: Annotated[
        OrderDashboardQueries,
        Depends(get_order_dashboard_queries),
    ],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    granularity: Annotated[str, Query(pattern="^(day|week|month)$")] = "day",
    sale_type: Annotated[str | None, Query()] = None,
    client_type: Annotated[str | None, Query()] = None,
) -> OrderTrendResponse:
    """EP-2: Тренд заказов (BR-2)."""
    today = date.today()
    return await queries.get_order_trends(
        date_from=date_from or month_ago(today),
        date_to=date_to or today,
        granularity=granularity,
        sale_type=sale_type,
        client_type=client_type,
    )


@orders_dashboard_router.get(
    "/orders/funnel",
    response_model=OrderFunnelResponse,
)
async def get_order_funnel(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.ORDERS_READ],
        ),
    ],
    queries: Annotated[
        OrderDashboardQueries,
        Depends(get_order_dashboard_queries),
    ],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> OrderFunnelResponse:
    """EP-3: Воронка статусов (BR-3)."""
    today = date.today()
    return await queries.get_order_funnel(
        date_from=date_from or month_ago(today),
        date_to=date_to or today,
    )


@orders_dashboard_router.get(
    "/orders/heatmap",
    response_model=OrderHeatmapResponse,
)
async def get_order_heatmap(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.ORDERS_READ],
        ),
    ],
    queries: Annotated[
        OrderDashboardQueries,
        Depends(get_order_dashboard_queries),
    ],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> OrderHeatmapResponse:
    """EP-4: Тепловая карта заказов (BR-4)."""
    today = date.today()
    return await queries.get_order_heatmap(
        date_from=date_from or month_ago(today),
        date_to=date_to or today,
    )


@orders_dashboard_router.get(
    "/orders/top-clients",
    response_model=TopClientsResponse,
)
async def get_top_clients(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.ORDERS_READ],
        ),
    ],
    queries: Annotated[
        OrderDashboardQueries,
        Depends(get_order_dashboard_queries),
    ],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    limit: int = Query(default=10, ge=1, le=100),
    sort_by: Annotated[
        str,
        Query(pattern="^(total_amount|orders_count)$"),
    ] = "total_amount",
) -> TopClientsResponse:
    """EP-7: Топ клиентов (BR-16)."""
    today = date.today()
    return await queries.get_top_clients(
        date_from=date_from or month_ago(today),
        date_to=date_to or today,
        limit=limit,
        sort_by=sort_by,
    )
