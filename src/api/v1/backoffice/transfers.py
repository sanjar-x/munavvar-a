# src/api/v1/backoffice/transfers.py
import uuid
from datetime import UTC, date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_caller_scopes, get_current_user
from src.modules.inventory.dependencies import get_stock_transfer_service
from src.modules.inventory.enums import TransferType
from src.modules.inventory.schemas import (
    CreateTransferRequest,
    TransferResponse,
    TransfersCursorListResponse,
)
from src.modules.inventory.services import StockTransferService
from src.modules.users.enums import Role

transfers_router = APIRouter()


def date_to_datetime_start(d: date) -> datetime:
    return datetime.combine(d, time.min).replace(tzinfo=UTC)


def date_to_datetime_end(d: date) -> datetime:
    return datetime.combine(d, time.max).replace(tzinfo=UTC)


@transfers_router.get(
    "/",
    response_model=list[TransferResponse] | TransfersCursorListResponse,
    summary="Журнал всех накладных",
)
async def get_transfers(
    transfer_service: Annotated[
        StockTransferService, Depends(get_stock_transfer_service)
    ],
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.LOGISTICS_TRANSFER])
    ],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    cursor: Annotated[
        str | None,
        Query(
            description=(
                "Cursor-режим (FRD §15.2). Если задан — `page`"
                " игнорируется, ответ оборачивается в"
                " `TransfersCursorListResponse`."
            )
        ),
    ] = None,
    type: Annotated[
        TransferType | None, Query(description="Фильтр по типу")
    ] = None,
    from_date: Annotated[
        date | None, Query(description="Начальная дата (включительно)")
    ] = None,
    to_date: Annotated[
        date | None, Query(description="Конечная дата (включительно)")
    ] = None,
    warehouse_id: Annotated[
        uuid.UUID | None, Query(description="Склад (from или to)")
    ] = None,
):
    # Storekeeper sees only transfers touching their
    # warehouse(s); admin sees all
    warehouse_owner_id = (
        current_admin.id if current_admin.role == Role.STOREKEEPER else None
    )
    # Convert date → datetime (start/end of day) for inclusive filtering
    date_from = (
        date_to_datetime_start(from_date) if from_date is not None else None
    )
    date_to_ = date_to_datetime_end(to_date) if to_date is not None else None

    if cursor is not None:
        items, meta = await transfer_service.search_transfers_cursor(
            size=size,
            cursor_token=cursor,
            transfer_type=type,
            date_from=date_from,
            date_to=date_to_,
            warehouse_id=warehouse_id,
            warehouse_owner_id=warehouse_owner_id,
        )
        return TransfersCursorListResponse(
            items=[TransferResponse.model_validate(it) for it in items],
            pagination=meta,
        )

    skip = (page - 1) * size
    return await transfer_service.search_transfers(
        skip=skip,
        limit=size,
        transfer_type=type,
        date_from=date_from,
        date_to=date_to_,
        warehouse_id=warehouse_id,
        warehouse_owner_id=warehouse_owner_id,
    )


def _has_cursor_format_request() -> bool:
    """Hook для будущего расширения (`?format=cursor`).

    Сейчас активирующий триггер — наличие `?cursor=...`.
    """
    return False


@transfers_router.post(
    "/",
    response_model=TransferResponse,
    summary="Создание и проведение накладной",
)
async def create_transfer(
    schema: CreateTransferRequest,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.LOGISTICS_TRANSFER])
    ],
    caller_scopes: Annotated[list[str], Depends(get_caller_scopes)],
    transfer_service: Annotated[
        StockTransferService, Depends(get_stock_transfer_service)
    ],
):
    return await transfer_service.create_transfer(
        current_admin.id, schema, caller_scopes
    )
