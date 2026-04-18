# src/modules/inventory/dependencies.py
from typing import Annotated

from fastapi import Depends

from src.infrastructure.database.session import async_session_maker
from src.modules.catalog.dependencies import get_catalog_service
from src.modules.catalog.public import CatalogService
from src.modules.inventory.services import (
    CapitalizeTaraService,
    StockTransferService,
    TransportService,
    WarehouseService,
)
from src.modules.inventory.uow import InventoryUnitOfWork


def get_inventory_uow() -> InventoryUnitOfWork:
    return InventoryUnitOfWork(session_factory=async_session_maker)


def get_capitalize_tara_service(
    uow: Annotated[InventoryUnitOfWork, Depends(get_inventory_uow)],
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> CapitalizeTaraService:
    return CapitalizeTaraService(uow=uow, catalog_service=catalog_service)


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
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> StockTransferService:
    return StockTransferService(uow=uow, catalog_service=catalog_service)


def get_stock_ledger_service(
    uow: Annotated[InventoryUnitOfWork, Depends(get_inventory_uow)],
):
    from src.modules.inventory.services import StockLedgerService

    return StockLedgerService(uow=uow)


def get_balance_service(
    uow: Annotated[InventoryUnitOfWork, Depends(get_inventory_uow)],
):
    from src.modules.inventory.services import BalanceService

    return BalanceService(uow=uow)
