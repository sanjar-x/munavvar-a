# src/api/v1/backoffice/dashboard.py
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security

from src.api.dependencies.auth import get_current_user
from src.api.dependencies.queries import get_users_dashboard_query
from src.core.security.permissions import Scope
from src.modules.users.models import User
from src.modules.users.queries import UsersDashboardQuery
from src.modules.users.schemas import UsersDashboardResponse

couriers_router = APIRouter()


@couriers_router.get(
    "/",
    response_model=UsersDashboardResponse,
    summary="Сводка по курерам (Балансы, Касса, Тары)",
)
async def get_couriers_dashboard(
    current_staff: Annotated[
        User,
        Security(
            dependency=get_current_user,
            scopes=[
                Scope.USERS_READ,
                Scope.INVENTORY_READ,
                Scope.FINANCES_READ,
            ],
        ),
    ],
    query: Annotated[
        UsersDashboardQuery, Depends(dependency=get_users_dashboard_query)
    ],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return await query.get_couriers(skip=skip, limit=limit)
