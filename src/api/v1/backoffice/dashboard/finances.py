# src/api/v1/backoffice/dashboard/finances.py
"""Dashboard API — Finance (EP-8..EP-12, EP-21)."""

from datetime import date
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
from src.modules.finances.dashboard_queries import (
    FinanceDashboardQueries,
)
from src.modules.finances.dashboard_schemas import (
    DebtAgingResponse,
    FinanceSummaryKPIs,
    PaymentMethodsFinanceResponse,
    RevenueBySegmentResponse,
    RevenueTrendResponse,
    TopDebtorsResponse,
)

finances_dashboard_router = APIRouter()


async def get_finance_dashboard_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FinanceDashboardQueries:
    return FinanceDashboardQueries(session)


@finances_dashboard_router.get(
    "/finances/revenue-trend",
    response_model=RevenueTrendResponse,
)
async def get_revenue_trend(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.FINANCES_READ],
        ),
    ],
    queries: Annotated[
        FinanceDashboardQueries,
        Depends(get_finance_dashboard_queries),
    ],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    granularity: Annotated[str, Query(pattern="^(day|week|month)$")] = "day",
) -> RevenueTrendResponse:
    """EP-8: Динамика выручки (BR-6)."""
    today = date.today()
    return await queries.get_revenue_trend(
        date_from=date_from or month_ago(today),
        date_to=date_to or today,
        granularity=granularity,
    )


@finances_dashboard_router.get(
    "/finances/debt-aging",
    response_model=DebtAgingResponse,
)
async def get_debt_aging(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.FINANCES_READ],
        ),
    ],
    queries: Annotated[
        FinanceDashboardQueries,
        Depends(get_finance_dashboard_queries),
    ],
) -> DebtAgingResponse:
    """EP-9: Aging-бакеты дебиторки (BR-7)."""
    return await queries.get_debt_aging()


@finances_dashboard_router.get(
    "/finances/top-debtors",
    response_model=TopDebtorsResponse,
)
async def get_top_debtors(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.FINANCES_READ],
        ),
    ],
    queries: Annotated[
        FinanceDashboardQueries,
        Depends(get_finance_dashboard_queries),
    ],
    limit: int = Query(default=10, ge=1, le=100),
) -> TopDebtorsResponse:
    """EP-10: Топ должников (BR-8)."""
    return await queries.get_top_debtors(limit=limit)


@finances_dashboard_router.get(
    "/finances/summary-kpis",
    response_model=FinanceSummaryKPIs,
)
async def get_summary_kpis(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.FINANCES_READ],
        ),
    ],
    queries: Annotated[
        FinanceDashboardQueries,
        Depends(get_finance_dashboard_queries),
    ],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> FinanceSummaryKPIs:
    """EP-12: Расчётные финансовые KPI (BR-9)."""
    today = date.today()
    return await queries.get_summary_kpis(
        date_from=date_from or month_ago(today),
        date_to=date_to or today,
    )


@finances_dashboard_router.get(
    "/finances/revenue-by-segment",
    response_model=RevenueBySegmentResponse,
)
async def get_revenue_by_segment(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.FINANCES_READ],
        ),
    ],
    queries: Annotated[
        FinanceDashboardQueries,
        Depends(get_finance_dashboard_queries),
    ],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> RevenueBySegmentResponse:
    """EP-21: Выручка B2B/B2C (BR-20)."""
    today = date.today()
    return await queries.get_revenue_by_segment(
        date_from=date_from or month_ago(today),
        date_to=date_to or today,
    )


@finances_dashboard_router.get(
    "/finances/payment-methods",
    response_model=PaymentMethodsFinanceResponse,
)
async def get_payment_methods(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.FINANCES_READ],
        ),
    ],
    queries: Annotated[
        FinanceDashboardQueries,
        Depends(get_finance_dashboard_queries),
    ],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> PaymentMethodsFinanceResponse:
    """EP-11: Способы оплаты — фин. призма (BR-5)."""
    today = date.today()
    return await queries.get_payment_methods(
        date_from=date_from or month_ago(today),
        date_to=date_to or today,
    )
