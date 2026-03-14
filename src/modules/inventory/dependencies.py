# src/modules/inventory/dependencies.py
from typing import Annotated

from fastapi import Depends

from src.infrastructure.database.session import async_session_maker
from src.modules.inventory.services import (
    StockTransferService,
    TransportService,
    WarehouseService,
)
from src.modules.inventory.uow import InventoryUnitOfWork


def get_inventory_uow() -> InventoryUnitOfWork:
    return InventoryUnitOfWork(session_factory=async_session_maker)


def get_transport_service(
    uow: Annotated[InventoryUnitOfWork, Depends(get_inventory_uow)],
) -> TransportService:
    return TransportService(uow=uow)


def get_warehouse_service(
    uow: Annotated[InventoryUnitOfWork, Depends(get_inventory_uow)],
) -> WarehouseService:
    return WarehouseService(uow=uow)


def get_stock_transfer_service(
    uow: Annotated[InventoryUnitOfWork, Depends(get_inventory_uow)],
) -> StockTransferService:
    return StockTransferService(uow=uow)
