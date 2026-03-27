# src/api/v1/backoffice/transport.py
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.dependencies import get_transport_service
from src.modules.inventory.schemas import (
    TransportCreate,
    TransportDetailResponse,
    TransportResponse,
    TransportUpdate,
)
from src.modules.inventory.services import TransportService

transport_router = APIRouter()


@transport_router.get(
    "/",
    response_model=list[TransportResponse],
    summary="Получить список всех транспортов (курьерских инвентарей)",
)
async def get_transports(
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    transport_service: Annotated[
        TransportService, Depends(get_transport_service)
    ],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user_id: uuid.UUID | None = Query(None, description="Фильтр по курьеру"),
):
    # TODO: Add specific TRANSPORT_READ permission if exists
    skip = (page - 1) * size
    transports, _ = await transport_service.get_transports(
        skip=skip, limit=size, user_id=user_id
    )
    return transports


@transport_router.post(
    "/",
    response_model=TransportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Зарегистрировать новый транспорт",
)
async def create_transport(
    schema: TransportCreate,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    transport_service: Annotated[
        TransportService, Depends(get_transport_service)
    ],
):
    return await transport_service.create_transport(schema)


@transport_router.get(
    "/{transport_id}",
    response_model=TransportDetailResponse,
    summary="Детальная информация о транспорте с остатками",
)
async def get_transport_detail(
    transport_id: uuid.UUID,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    transport_service: Annotated[
        TransportService, Depends(get_transport_service)
    ],
):
    transport = await transport_service.get_transport_with_balances(
        transport_id
    )
    if not transport:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transport not found"
        )
    return transport


@transport_router.patch(
    "/{transport_id}",
    response_model=TransportResponse,
    summary="Обновить информацию о транспорте",
)
async def update_transport(
    transport_id: uuid.UUID,
    schema: TransportUpdate,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    transport_service: Annotated[
        TransportService, Depends(get_transport_service)
    ],
):
    transport = await transport_service.update_transport(transport_id, schema)
    if not transport:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transport not found"
        )
    return transport


@transport_router.delete(
    "/{transport_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить транспорт",
)
async def delete_transport(
    transport_id: uuid.UUID,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    transport_service: Annotated[
        TransportService, Depends(get_transport_service)
    ],
):
    success = await transport_service.delete_transport(transport_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transport not found"
        )
    return None
