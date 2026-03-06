# src/application/inventories/dependencies.py
from src.application.inventories.uow import IInventoryUnitOfWork, InventoryUnitOfWork
from src.infrastructure.database.session import async_session_maker


def get_inventory_uow() -> IInventoryUnitOfWork:
    return InventoryUnitOfWork(session_factory=async_session_maker)
