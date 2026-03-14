# src/api/v1/backoffice/warehouses.py
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, status

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.schemas import (
    InventoryResponse,
    WarehouseCreate,
    WarehouseDetailResponse,
)
from src.modules.inventory.services import WarehouseService
from src.modules.inventory.uow import InventoryUnitOfWork

warehouses_router = APIRouter()


@warehouses_router.get(
    "/",
    response_model=list[WarehouseDetailResponse],
    summary="Список всех складов с актуальными остатками",
)
async def get_warehouses_with_balances(
    uow: Annotated[InventoryUnitOfWork, Depends()],
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
):
    return await WarehouseService.get_warehouses_with_balances(uow)


@warehouses_router.post(
    "/",
    response_model=InventoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создание нового склада",
)
async def create_warehouse(
    schema: WarehouseCreate,
    uow: Annotated[InventoryUnitOfWork, Depends()],
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
):
    return await WarehouseService.create_warehouse(uow, schema)


@warehouses_router.get(
    "/{warehouse_id}",
    response_model=WarehouseDetailResponse,
    summary="Детальная информация по складу с остатками",
)
async def get_warehouse_detail(
    warehouse_id: uuid.UUID,
    uow: Annotated[InventoryUnitOfWork, Depends()],
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
):
    warehouse = await WarehouseService.get_warehouse_with_balances(uow, warehouse_id)
    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found"
        )
    return warehouse
