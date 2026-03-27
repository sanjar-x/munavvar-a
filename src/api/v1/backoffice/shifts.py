# src/api/v1/backoffice/shifts.py
from typing import Annotated

from fastapi import APIRouter, Depends, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.schemas import (
    CloseShiftRequest,
    FactoryExchangeRequest,
)
from src.modules.inventory.shift_service import ShiftService
from src.modules.inventory.uow import InventoryUnitOfWork

shifts_router = APIRouter()


def get_shift_service(
    uow: Annotated[InventoryUnitOfWork, Depends()],
) -> ShiftService:
    return ShiftService(uow)


@shifts_router.post("/factory-exchange")
async def factory_exchange(
    request: FactoryExchangeRequest,
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.INVENTORY_WRITE])
    ],
    shift_service: Annotated[ShiftService, Depends(get_shift_service)],
):
    """Обмен на заводе: курьер сдаёт пустые, забирает полные (COURIER→FACTORY→COURIER)."""
    return await shift_service.factory_exchange(
        request, created_by_id=admin.id
    )


@shifts_router.post("/close")
async def close_shift(
    request: CloseShiftRequest,
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.INVENTORY_WRITE])
    ],
    shift_service: Annotated[ShiftService, Depends(get_shift_service)],
):
    """Закрытие смены курьера и инкассация (Backoffice/Кладовщик)."""
    return await shift_service.close_shift(request)
