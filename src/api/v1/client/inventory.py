# src/api/v1/client/inventory.py
#
# ЭНДПОИНТ /capitalize-deficit УДАЛЕН (Фикс Fraud Risk).
#
# Причина: Клиент мог отправить фейковую корзину на 1000 бутылей,
# получить 1000 тар на баланс и не оформить заказ — бесконтрольная
# накрутка виртуального баланса тары.
#
# Решение: Авто-оприходование дефицита тары теперь происходит
# ИСКЛЮЧИТЕЛЬНО внутри транзакции создания заказа через флаг
# capitalize_missing_tara: true в POST /orders.
#
# Для диспетчеров: POST /backoffice/clients/{id}/inventory/capitalize
# остается без изменений (ручное оприходование под авторизацией).

from typing import Annotated

from fastapi import APIRouter, Depends, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.dependencies import get_inventory_uow
from src.modules.inventory.enums import InventoryType
from src.modules.inventory.schemas import BalanceResponse
from src.modules.inventory.uow import InventoryUnitOfWork

inventory_router = APIRouter()


@inventory_router.get(
    "/balance",
    response_model=list[BalanceResponse],
    summary="Баланс тары клиента",
)
async def get_my_tara_balance(
    client: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.ORDERS_READ]),
    ],
    uow: Annotated[
        InventoryUnitOfWork,
        Depends(get_inventory_uow),
    ],
):
    """Текущий баланс тары (бутыли) на адресе клиента.

    Возвращает список товаров с количеством.
    Только чтение — мутации баланса через заказы.
    """
    async with uow:
        inv = await uow.inventories.get_inventory_with_balances_by_user(
            user_id=client.id,
            inv_type=InventoryType.CLIENT,
        )
        if not inv:
            return []
        return [
            BalanceResponse(
                product=b.product,
                quantity=b.quantity,
            )
            for b in inv.balances
            if b.quantity != 0
        ]
