# src/api/v1/backoffice/inventories.py
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.dependencies import get_warehouse_service
from src.modules.inventory.enums import InventoryType
from src.modules.inventory.schemas import InventorySearchResult
from src.modules.inventory.services import WarehouseService

inventories_router = APIRouter()


@inventories_router.get(
    "/search",
    response_model=list[InventorySearchResult],
    summary="Поиск инвентарей по названию и типу",
)
async def search_inventories(
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.INVENTORY_READ])
    ],
    warehouse_service: Annotated[
        WarehouseService, Depends(get_warehouse_service)
    ],
    q: str = Query("", description="Поисковый запрос по названию"),
    type: Annotated[
        InventoryType | None,
        Query(description="Фильтр по типу (CLIENT, WAREHOUSE, …)"),
    ] = None,
    limit: int = Query(50, ge=1, le=200),
):
    return await warehouse_service.search_inventories(
        search_query=q,
        inv_type=type,
        limit=limit,
    )
