# src/api/v1/client/inventory.py
from typing import Annotated

from fastapi import APIRouter, Depends, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.dependencies import get_capitalize_tara_service
from src.modules.inventory.schemas import (
    CapitalizeDeficitRequest,
    CapitalizeTaraResponse,
)
from src.modules.inventory.services import CapitalizeTaraService

inventory_router = APIRouter()


@inventory_router.post(
    "/capitalize-deficit",
    response_model=CapitalizeTaraResponse,
    summary="Оприходовать дефицит тары",
    description=(
        "Автоматически рассчитывает нехватку тары для указанной корзины "
        "и оприходует ровно столько, сколько не хватает. "
        "Защита от фрода: клиент не может оприходовать больше дефицита."
    ),
)
async def capitalize_deficit(
    dto: CapitalizeDeficitRequest,
    client: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_CREATE])
    ],
    capitalize_service: Annotated[
        CapitalizeTaraService, Depends(get_capitalize_tara_service)
    ],
):
    return await capitalize_service.capitalize_deficit(
        dto=dto, client_id=client.id
    )
