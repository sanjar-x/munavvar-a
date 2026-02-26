# src/modules/logistics/services.py
import uuid

from src.common.uow import IUnitOfWork
from src.modules.catalog.models import ProductType
from src.modules.logistics.inventory.enums import InventoryType
from src.modules.logistics.inventory.models import Inventory
from src.modules.orders.models import Order


class LogisticsService:
    """Доменный сервис для управления физическим перемещением товаров."""

    def __init__(self, uow: IUnitOfWork):
        self.uow = uow

    async def get_client_balcony(
        self, client_id: uuid.UUID
    ) -> Inventory | None:
        return await self.uow.inventories.get_client_balcony(client_id)

    async def get_courier_inventory(
        self, courier_id: uuid.UUID
    ) -> Inventory | None:
        return await self.uow.inventories.get_courier_inventory(courier_id)

    async def add_client_balcony(self, client_id: uuid.UUID) -> Inventory:
        return await self.uow.inventories.add(
            {
                "user_id": client_id,
                "type": InventoryType.CLIENT_BALCONY,
                "name": f"Балкон клиента {client_id}",
            }
        )

    async def add_courier_inventory(self, courier_id: uuid.UUID) -> Inventory:
        return await self.uow.inventories.add(
            {
                "user_id": courier_id,
                "type": InventoryType.COURIER_CAR,
                "name": f"Машина курьера {courier_id}",
            }
        )

    async def get_or_add_client_balcony(
        self, client_id: uuid.UUID
    ) -> Inventory:
        balcony = await self.get_client_balcony(client_id)
        if not balcony:
            balcony = await self.add_client_balcony(client_id)
        return balcony

    async def get_or_add_courier_inventory(
        self, courier_id: uuid.UUID
    ) -> Inventory:
        inventory = await self.get_courier_inventory(courier_id)
        if not inventory:
            inventory = await self.add_courier_inventory(courier_id)
        return inventory

    async def get_courier_inventory_or_fail(
        self, courier_id: uuid.UUID
    ) -> Inventory:
        inventory = await self.get_courier_inventory(courier_id)
        if not inventory:
            raise Exception(f"У курьера {courier_id} нет активной машины!")
        return inventory

    async def get_courier_inventories_with_balances(self):
        result = (
            await self.uow.inventories.get_courier_inventories_with_balances()
        )
        return result

    async def deliver_order_items(
        self, order: Order, courier_id: uuid.UUID, client_id: uuid.UUID
    ) -> None:
        courier_inventory: Inventory = (
            await self.get_courier_inventory_or_fail(courier_id)
        )
        client_balcony: Inventory = await self.get_or_add_client_balcony(
            client_id
        )

        to_return = {}

        for item in order.items:
            if item.product.type == ProductType.CONTAINER:
                to_return[item.product.id] = (
                    to_return.get(item.product.id, 0) - item.quantity
                )
                continue

            base_tx = {
                "from_id": courier_inventory.id,
                "to_id": client_balcony.id,
                "quantity": item.quantity,
                "order_id": order.id,
            }

            await self.uow.stock_transactions.add(
                {**base_tx, "product_id": item.product.id}
            )

            if item.product.type == ProductType.WATER:
                ret_id = item.product.returnable_item_id
                await self.uow.stock_transactions.add(
                    {**base_tx, "product_id": ret_id}
                )
                to_return[ret_id] = to_return.get(ret_id, 0) + item.quantity

        for product_id, quantity in to_return.items():
            if quantity > 0:
                await self.uow.stock_transactions.add(
                    {
                        "from_id": client_balcony.id,
                        "to_id": courier_inventory.id,
                        "product_id": product_id,
                        "quantity": quantity,
                        "order_id": order.id,
                    }
                )
