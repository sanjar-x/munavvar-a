# src/modules/logistics/services.py
import uuid

from src.common.uow import IUnitOfWork
from src.modules.logistics.inventory.models import Inventory


class WarehouseService:
    """(Завод <-> Склад <-> Курьер)."""

    def __init__(self, uow: IUnitOfWork):
        self.uow = uow

    async def get_factory_inventory(self) -> Inventory | None:
        system_user = await self.uow.users.get_system_user()
        return await self.uow.inventories.get_factory_inventory(
            system_user_id=system_user.id
        )

    async def get_warehouse_inventory(self) -> Inventory | None:
        system_user = await self.uow.users.get_system_user()
        return await self.uow.inventories.get_warehouse_inventory(
            system_user_id=system_user.id
        )

    async def get_courier_inventory(
        self, courier_id: uuid.UUID
    ) -> Inventory | None:
        """
        Получает склад (машину) курьера или водителя Газели.
        Для системы водитель Газели — это такой же курьер со своей машиной.
        """
        return await self.uow.inventories.get_courier_inventory(courier_id)

    async def get_inventory_balances(self, inventory_id: uuid.UUID):
        return await self.uow.inventories.get_inventory_balances(
            inventory_id=inventory_id
        )
