# src/api/v1/backoffice/stock_transactions.py
"""Backoffice journal of stock movements (FRD §6).

`GET /backoffice/stock-transactions/` — read-only лента всех движений
склад/курьер/клиент с расширенной фильтрацией, поиском (`q`) и
пагинацией. Доступ — `inventory:read` (роли ADMIN, STOREKEEPER,
ACCOUNTANT, COURIER).
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.catalog.enums import ProductType
from src.modules.inventory.dependencies import get_stock_ledger_service
from src.modules.inventory.enums import InventoryType, TransferType
from src.modules.inventory.schemas import (
    DatePreset,
    SortOrder,
    StockTransactionFilter,
    StockTransactionsListResponse,
)
from src.modules.inventory.services import StockLedgerService

stock_transactions_router = APIRouter()


def build_stock_transaction_filter(
    q: Annotated[str | None, Query(description="Free-text поиск")] = None,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    product_id_in: Annotated[list[uuid.UUID] | None, Query()] = None,
    product_type_in: Annotated[list[ProductType] | None, Query()] = None,
    from_id: Annotated[uuid.UUID | None, Query()] = None,
    to_id: Annotated[uuid.UUID | None, Query()] = None,
    inventory_id: Annotated[uuid.UUID | None, Query()] = None,
    direction: Annotated[
        Literal["incoming", "outgoing", "any"] | None,
        Query(
            description="incoming | outgoing | any (only with inventory_id)",
        ),
    ] = None,
    from_type_in: Annotated[list[InventoryType] | None, Query()] = None,
    to_type_in: Annotated[list[InventoryType] | None, Query()] = None,
    transfer_id: Annotated[uuid.UUID | None, Query()] = None,
    transfer_type_in: Annotated[list[TransferType] | None, Query()] = None,
    order_id: Annotated[uuid.UUID | None, Query()] = None,
    created_by_id: Annotated[uuid.UUID | None, Query()] = None,
    quantity_eq: Annotated[int | None, Query(ge=0)] = None,
    quantity_from: Annotated[int | None, Query(ge=0)] = None,
    quantity_to: Annotated[int | None, Query(ge=0)] = None,
    date_preset: Annotated[DatePreset | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    sort: Annotated[Literal["created_at", "quantity"], Query()] = "created_at",
    order: Annotated[SortOrder, Query()] = "desc",
) -> StockTransactionFilter:
    return StockTransactionFilter(
        q=q,
        product_id=product_id,
        product_id_in=product_id_in,
        product_type_in=product_type_in,
        from_id=from_id,
        to_id=to_id,
        inventory_id=inventory_id,
        direction=direction,
        from_type_in=from_type_in,
        to_type_in=to_type_in,
        transfer_id=transfer_id,
        transfer_type_in=transfer_type_in,
        order_id=order_id,
        created_by_id=created_by_id,
        quantity_eq=quantity_eq,
        quantity_from=quantity_from,
        quantity_to=quantity_to,
        date_preset=date_preset,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        order=order,
    )


@stock_transactions_router.get(
    "/",
    response_model=StockTransactionsListResponse,
    summary="Журнал движений (FRD §6)",
)
async def list_stock_transactions(
    current_user: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.INVENTORY_READ]),
    ],
    service: Annotated[StockLedgerService, Depends(get_stock_ledger_service)],
    filters: Annotated[
        StockTransactionFilter,
        Depends(build_stock_transaction_filter),
    ],
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
):
    """Список движений склад/курьер/клиент.

    Поддерживает: free-text `q` (имя продукта/склада, кол-во,
    суффикс телефона владельца склада; UUID-поиск отключён),
    multi-value фильтры, диапазоны количества/дат, пресеты дат,
    сортировку по `created_at` или `quantity`, offset-пагинацию,
    inline-`summary` с агрегатами.
    """
    return await service.list(filters=filters, page=page, size=size)
