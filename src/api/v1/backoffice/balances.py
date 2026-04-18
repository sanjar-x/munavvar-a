# src/api/v1/backoffice/balances.py
"""Backoffice cross-cut view of inventory balances (FRD §9).

`GET /backoffice/balances/` — материализованные остатки по всем
инвентарям с фильтрами и поиском. Read-only.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.catalog.enums import ProductType
from src.modules.inventory.dependencies import get_balance_service
from src.modules.inventory.enums import InventoryType
from src.modules.inventory.schemas import (
    BalanceFilter,
    BalancesListResponse,
    SortOrder,
)
from src.modules.inventory.services import BalanceService

balances_router = APIRouter()


def build_balance_filter(
    q: Annotated[str | None, Query()] = None,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    product_id_in: Annotated[list[uuid.UUID] | None, Query()] = None,
    product_type_in: Annotated[list[ProductType] | None, Query()] = None,
    inventory_type_in: Annotated[list[InventoryType] | None, Query()] = None,
    inventory_id_in: Annotated[list[uuid.UUID] | None, Query()] = None,
    user_id: Annotated[uuid.UUID | None, Query()] = None,
    quantity_from: Annotated[int | None, Query(ge=0)] = None,
    quantity_to: Annotated[int | None, Query(ge=0)] = None,
    nonzero_only: Annotated[bool, Query()] = True,
    sort: Annotated[str, Query()] = "quantity",
    order: Annotated[SortOrder, Query()] = "desc",
) -> BalanceFilter:
    return BalanceFilter(
        q=q,
        product_id=product_id,
        product_id_in=product_id_in,
        product_type_in=product_type_in,
        inventory_type_in=inventory_type_in,
        inventory_id_in=inventory_id_in,
        user_id=user_id,
        quantity_from=quantity_from,
        quantity_to=quantity_to,
        nonzero_only=nonzero_only,
        sort=sort,
        order=order,
    )


@balances_router.get(
    "/",
    response_model=BalancesListResponse,
    summary="Остатки (FRD §9)",
)
async def list_balances(
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.INVENTORY_READ]),
    ],
    service: Annotated[BalanceService, Depends(get_balance_service)],
    filters: Annotated[BalanceFilter, Depends(build_balance_filter)],
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
):
    """Срез по `inventory_balances`.

    По умолчанию `nonzero_only=true` — нулевые остатки скрыты,
    чтобы UI отдавал реальные «есть на складе/у курьера/у клиента».
    """
    return await service.list(filters=filters, page=page, size=size)
