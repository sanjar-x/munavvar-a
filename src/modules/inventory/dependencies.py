# src/modules/inventory/dependencies.py

from typing import Annotated

from fastapi import Depends

from src.infrastructure.database.session import async_session_maker
from src.modules.inventory.services import (
    InventoryService,
    StockTransferItemService,
    StockTransferService,
)
from src.modules.inventory.uow import InventoryUnitOfWork


def get_inventory_uow() -> InventoryUnitOfWork:
    return InventoryUnitOfWork(session_factory=async_session_maker)


def get_inventory_service(
    uow: Annotated[InventoryUnitOfWork, Depends(get_inventory_uow)],
) -> InventoryService:
    return InventoryService(uow=uow)


def get_stock_transfer_service(
    uow: Annotated[InventoryUnitOfWork, Depends(get_inventory_uow)],
) -> StockTransferService:
    return StockTransferService(uow=uow)


def get_stock_transfer_item_service(
    uow: Annotated[InventoryUnitOfWork, Depends(get_inventory_uow)],
) -> StockTransferItemService:
    return StockTransferItemService(uow=uow)
