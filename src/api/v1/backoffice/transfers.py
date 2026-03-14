# src/api/v1/backoffice/transfers.py
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.schemas import (
    TransferCompleteRequest,
    TransferCreate,
    TransferItemCreate,
    TransferResponse,
)
from src.modules.inventory.services import StockTransferService
from src.modules.inventory.uow import InventoryUnitOfWork

transfers_router = APIRouter()


@transfers_router.get(
    "/",
    response_model=list[TransferResponse],
    summary="Журнал всех накладных",
)
async def get_transfers(
    uow: Annotated[InventoryUnitOfWork, Depends()],
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    skip = (page - 1) * size
    transfers = await uow.transfers.search_transfers(skip=skip, limit=size)
    return transfers


@transfers_router.post(
    "/",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создание черновика перемещения",
)
async def create_transfer(
    schema: TransferCreate,
    uow: Annotated[InventoryUnitOfWork, Depends()],
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
):
    return await StockTransferService.create_draft_transfer(
        uow, current_admin.id, schema
    )


@transfers_router.post(
    "/{transfer_id}/items",
    response_model=TransferResponse,
    summary="Добавление/обновление строк в черновик",
)
async def update_transfer_items(
    transfer_id: uuid.UUID,
    items: list[TransferItemCreate],
    uow: Annotated[InventoryUnitOfWork, Depends()],
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
):
    try:
        return await StockTransferService.update_draft_items(uow, transfer_id, items)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@transfers_router.post(
    "/{transfer_id}/complete",
    response_model=TransferResponse,
    summary="Проведение документа",
)
async def complete_transfer(
    transfer_id: uuid.UUID,
    schema: TransferCompleteRequest,
    uow: Annotated[InventoryUnitOfWork, Depends()],
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
):
    try:
        return await StockTransferService.complete_transfer(
            uow, transfer_id, schema.accepted_by_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
