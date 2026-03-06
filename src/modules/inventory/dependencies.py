# src/modules/inventory/dependencies.py


from src.infrastructure.database.session import async_session_maker
from src.modules.inventory.uow import InventoryUnitOfWork


def get_inventory_uow() -> InventoryUnitOfWork:
    return InventoryUnitOfWork(session_factory=async_session_maker)
