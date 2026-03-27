# src/api/v1/backoffice/transfers.py
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.dependencies import get_stock_transfer_service
from src.modules.inventory.schemas import (
    CreateTransferRequest,
    TransferResponse,
)
from src.modules.inventory.services import StockTransferService

transfers_router = APIRouter()


@transfers_router.get(
    "/",
    response_model=list[TransferResponse],
    summary="Журнал всех накладных",
)
async def get_transfers(
    transfer_service: Annotated[
        StockTransferService, Depends(get_stock_transfer_service)
    ],
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    skip = (page - 1) * size
    return await transfer_service.search_transfers(skip=skip, limit=size)


@transfers_router.post(
    "/",
    response_model=TransferResponse,
    summary="Создание и проведение накладной",
)
async def create_transfer(
    schema: CreateTransferRequest,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.INVENTORY_WRITE])
    ],
    transfer_service: Annotated[
        StockTransferService, Depends(get_stock_transfer_service)
    ],
):
    return await transfer_service.create_transfer(current_admin.id, schema)
