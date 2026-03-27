# src/api/v1/backoffice/transfers.py
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.dependencies import (
    get_stock_transfer_service,
)
from src.modules.inventory.schemas import (
    TransferCompleteRequest,
    TransferCreate,
    TransferItemCreate,
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
    status_code=status.HTTP_201_CREATED,
    summary="Создание черновика перемещения",
)
async def create_transfer(
    schema: TransferCreate,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    transfer_service: Annotated[
        StockTransferService, Depends(get_stock_transfer_service)
    ],
):
    return await transfer_service.create_draft_transfer(current_admin.id, schema)


@transfers_router.put(
    "/{transfer_id}/items",
    response_model=TransferResponse,  # Assuming StockTransferResponse is a typo and should be TransferResponse based on existing schemas
    summary="Добавление/обновление строк в черновик",
)
async def update_transfer_items(
    transfer_id: uuid.UUID,
    items_schema: list[TransferItemCreate],
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    transfer_service: Annotated[
        StockTransferService, Depends(get_stock_transfer_service)
    ],
):
    try:
        return await transfer_service.update_draft_items(transfer_id, items_schema)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@transfers_router.post(
    "/{transfer_id}/complete",
    response_model=TransferResponse,  # Assuming StockTransferResponse is a typo and should be TransferResponse based on existing schemas
    summary="Проведение документа",
)
async def complete_transfer(
    transfer_id: uuid.UUID,
    schema: TransferCompleteRequest,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    transfer_service: Annotated[
        StockTransferService, Depends(get_stock_transfer_service)
    ],
):
    try:
        return await transfer_service.complete_transfer(
            transfer_id, accepted_by_id=schema.accepted_by_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
