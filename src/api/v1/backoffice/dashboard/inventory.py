# src/api/v1/backoffice/dashboard/inventory.py
"""Dashboard API — Inventory (EP-13..EP-16, EP-18, EP-19)."""

import uuid
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
from src.modules.inventory.dashboard_queries import (
    InventoryDashboardQueries,
)
from src.modules.inventory.dashboard_schemas import (
    ContainerDebtorsResponse,
    ContainerDistribution,
    InventorySummary,
    InventoryTrendResponse,
    MovementStatsResponse,
    VirtualAccountsResponse,
)
from src.modules.users.enums import Role

inventory_dashboard_router = APIRouter()


async def get_inventory_dashboard_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InventoryDashboardQueries:
    return InventoryDashboardQueries(session)


def _storekeeper_id(user: User) -> uuid.UUID | None:
    if user.role == Role.STOREKEEPER:
        return user.id
    return None


@inventory_dashboard_router.get(
    "/inventory/summary",
    response_model=InventorySummary,
)
async def get_inventory_summary(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.INVENTORY_READ],
        ),
    ],
    queries: Annotated[
        InventoryDashboardQueries,
        Depends(get_inventory_dashboard_queries),
    ],
) -> InventorySummary:
    """EP-13: Складская сводка (BR-10)."""
    return await queries.get_summary(
        warehouse_owner_id=_storekeeper_id(current_user),
    )


@inventory_dashboard_router.get(
    "/inventory/container-distribution",
    response_model=ContainerDistribution,
)
async def get_container_distribution(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.INVENTORY_READ],
        ),
    ],
    queries: Annotated[
        InventoryDashboardQueries,
        Depends(get_inventory_dashboard_queries),
    ],
) -> ContainerDistribution:
    """EP-14: Распределение тары (BR-11)."""
    return await queries.get_container_distribution()


@inventory_dashboard_router.get(
    "/inventory/virtual-accounts",
    response_model=VirtualAccountsResponse,
)
async def get_virtual_accounts(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.INVENTORY_READ],
        ),
    ],
    queries: Annotated[
        InventoryDashboardQueries,
        Depends(get_inventory_dashboard_queries),
    ],
) -> VirtualAccountsResponse:
    """EP-19: Виртуальные счета + целостность (BR-18)."""
    return await queries.get_virtual_accounts()


@inventory_dashboard_router.get(
    "/inventory/container-debtors",
    response_model=ContainerDebtorsResponse,
)
async def get_container_debtors(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.INVENTORY_READ],
        ),
    ],
    queries: Annotated[
        InventoryDashboardQueries,
        Depends(get_inventory_dashboard_queries),
    ],
    limit: int = Query(default=10, ge=1, le=100),
) -> ContainerDebtorsResponse:
    """EP-15: Должники по таре (BR-12)."""
    return await queries.get_container_debtors(
        limit=limit,
    )


@inventory_dashboard_router.get(
    "/inventory/movement-stats",
    response_model=MovementStatsResponse,
)
async def get_movement_stats(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.INVENTORY_READ],
        ),
    ],
    queries: Annotated[
        InventoryDashboardQueries,
        Depends(get_inventory_dashboard_queries),
    ],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> MovementStatsResponse:
    """EP-16: Статистика перемещений (BR-13)."""
    today = date.today()
    return await queries.get_movement_stats(
        date_from=date_from or month_ago(today),
        date_to=date_to or today,
        warehouse_owner_id=_storekeeper_id(current_user),
    )


@inventory_dashboard_router.get(
    "/inventory/trends",
    response_model=InventoryTrendResponse,
)
async def get_inventory_trends(
    current_user: Annotated[
        User,
        Security(
            get_current_user,
            scopes=[Scope.INVENTORY_READ],
        ),
    ],
    queries: Annotated[
        InventoryDashboardQueries,
        Depends(get_inventory_dashboard_queries),
    ],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> InventoryTrendResponse:
    """EP-18: Тренды остатков (BR-17)."""
    today = date.today()
    return await queries.get_inventory_trends(
        date_from=date_from or today - timedelta(days=7),
        date_to=date_to or today,
    )
