# src/api/v1/courier/inventory.py
from typing import Annotated

from fastapi import APIRouter, Depends, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_courier
from src.modules.inventory.dependencies import get_inventory_uow
from src.modules.inventory.enums import InventoryType
from src.modules.inventory.schemas import (
    BalanceResponse,
    ProductSimpleResponse,
)
from src.modules.inventory.uow import InventoryUnitOfWork

inventory_router = APIRouter()


@inventory_router.get(
    "/my-stock",
    response_model=list[BalanceResponse],
    summary="Остатки товаров в машине курьера",
)
async def get_my_vehicle_stock(
    courier: Annotated[
        User,
        Security(
            get_current_courier,
            scopes=[Scope.INVENTORY_READ],
        ),
    ],
    uow: Annotated[
        InventoryUnitOfWork,
        Depends(get_inventory_uow),
    ],
):
    """Текущие остатки товаров, загруженных в машину.

    Показывает воду, тару и оборудование
    с ненулевым балансом.
    """
    async with uow:
        inv = await uow.inventories.get_inventory_with_balances_by_user(
            user_id=courier.id,
            inv_type=InventoryType.COURIER,
        )
        if not inv:
            return []
        return [
            BalanceResponse(
                product=ProductSimpleResponse.model_validate(b.product),
                quantity=b.quantity,
            )
            for b in inv.balances
            if b.quantity != 0
        ]
