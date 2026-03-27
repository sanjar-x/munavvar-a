import uuid
from collections.abc import Sequence
from datetime import datetime

from src.infrastructure.database.models import Inventory, StockTransfer
from src.modules.catalog.services import CatalogService
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.inventory.exceptions import (
    InventoryNotFoundError,
)
from src.modules.inventory.schemas import (
    CapitalizeDeficitRequest,
    CapitalizeTaraItem,
    CapitalizeTaraRequest,
    TransferCreate,
    TransferItemCreate,
    TransportCreate,
    TransportUpdate,
    WarehouseCreate,
)
from src.modules.inventory.uow import InventoryUnitOfWork


class TransportService:
    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    async def create_transport(self, schema: TransportCreate) -> Inventory:
        async with self.uow:
            # В реальной системе здесь должна быть проверка, user_id курьера
            transport = await self.uow.inventories.add(
                {
                    "user_id": schema.user_id,
                    "name": schema.name,
                    "type": InventoryType.COURIER,
                }
            )
            await self.uow.commit()
            return transport

    async def get_transports(
        self,
        skip: int = 0,
        limit: int = 100,
        user_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[Inventory], int]:
        async with self.uow:
            filters = {"type": InventoryType.COURIER, "is_active": True}
            if user_id:
                filters["user_id"] = user_id

            transports = await self.uow.inventories.get_multi(
                skip=skip,
                limit=limit,
                **(filters),  # type: ignore
            )
            total = await self.uow.inventories.count(**(filters))  # type: ignore
            return transports, total

    async def get_transport_with_balances(
        self, transport_id: uuid.UUID
    ) -> Inventory | None:
        async with self.uow:
            return await self.uow.inventories.get_inventory_with_balances(
                transport_id, InventoryType.COURIER
            )

    async def update_transport(
        self, transport_id: uuid.UUID, schema: TransportUpdate
    ) -> Inventory | None:
        async with self.uow:
            update_data = schema.model_dump(exclude_unset=True)
            if not update_data:
                return await self.uow.inventories.get(transport_id)

            transport = await self.uow.inventories.update(
                transport_id, update_data
            )
            await self.uow.commit()
            return transport

    async def delete_transport(self, transport_id: uuid.UUID) -> bool:
        async with self.uow:
            transport = await self.uow.inventories.get(transport_id)
            if not transport:
                return False

            if transport.type in (
                InventoryType.VIRTUAL_VENDOR,
                InventoryType.VIRTUAL_LOSS,
            ):
                raise ValueError("Удаление системных складов запрещено")

            success = await self.uow.inventories.delete(transport_id)
            await self.uow.commit()
            return success


class WarehouseService:
    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    async def create_warehouse(self, schema: WarehouseCreate) -> Inventory:
        async with self.uow:
            warehouse = await self.uow.inventories.add(
                {
                    "user_id": schema.user_id,
                    "name": schema.name,
                    "type": InventoryType.WAREHOUSE,
                }
            )
            await self.uow.commit()
            return warehouse

    async def get_warehouses(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Inventory], int]:
        async with self.uow:
            filters = {"type": InventoryType.WAREHOUSE, "is_active": True}
            warehouses = await self.uow.inventories.get_multi(
                skip=skip,
                limit=limit,
                **(filters),  # type: ignore
            )
            total = await self.uow.inventories.count(**(filters))  # type: ignore
            return warehouses, total

    async def get_warehouse_with_balances(
        self, warehouse_id: uuid.UUID
    ) -> Inventory | None:
        async with self.uow:
            return await self.uow.inventories.get_inventory_with_balances(
                warehouse_id, InventoryType.WAREHOUSE
            )

    async def get_warehouses_with_balances(
        self,
    ) -> Sequence[Inventory]:
        async with self.uow:
            return (
                await self.uow.inventories.get_all_warehouses_with_balances()
            )


class StockTransferService:
    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    async def search_transfers(
        self,
        skip: int = 0,
        limit: int = 50,
        status: TransferStatus | None = None,
        transfer_type: TransferType | None = None,
        from_inventory_id: uuid.UUID | None = None,
        to_inventory_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Sequence[StockTransfer]:
        async with self.uow:
            return await self.uow.transfers.search_transfers(
                skip=skip,
                limit=limit,
                status=status,
                transfer_type=transfer_type,
                from_inventory_id=from_inventory_id,
                to_inventory_id=to_inventory_id,
                date_from=date_from,
                date_to=date_to,
            )

    async def create_draft_transfer(
        self, created_by_id: uuid.UUID, schema: TransferCreate
    ) -> StockTransfer:
        async with self.uow:
            # TODO: Validate inventories exist and types match the business logic
            transfer = await self.uow.transfers.add(
                {
                    "from_id": schema.from_id,
                    "to_id": schema.to_id,
                    "type": schema.type,
                    "status": TransferStatus.DRAFT,
                    "created_by_id": created_by_id,
                }
            )
            await self.uow.commit()
            return transfer

    async def update_draft_items(
        self,
        transfer_id: uuid.UUID,
        items_schema: list[TransferItemCreate],
    ) -> StockTransfer:
        async with self.uow:
            transfer = await self.uow.transfers.get_with_items_for_update(
                transfer_id
            )
            if not transfer:
                raise ValueError("Transfer not found")
            if transfer.status != TransferStatus.DRAFT:
                raise ValueError("Cannot update non-draft transfer")

            # Simple logic: replace old items with new ones or update
            # Here we'll clear and add to keep it simple, or find and update
            # Let's clear and re-add for simplicity in this specific task
            for item in transfer.items:
                await self.uow.transfer_items.delete(item.id)

            for item_data in items_schema:
                await self.uow.transfer_items.add(
                    {
                        "transfer_id": transfer_id,
                        "product_id": item_data.product_id,
                        "quantity": item_data.quantity,
                    }
                )

            await self.uow.commit()
            transfer = await self.uow.transfers.get_transfer(transfer_id)
            if not transfer:
                raise ValueError("Transfer not found after update")
            return transfer

    async def complete_transfer(
        self,
        transfer_id: uuid.UUID,
        accepted_by_id: uuid.UUID,
    ) -> StockTransfer:
        async with self.uow:
            transfer = await self.uow.transfers.get_transfer(transfer_id)
            if not transfer:
                raise ValueError("Transfer not found")
            if transfer.status != TransferStatus.DRAFT:
                raise ValueError("Only draft transfers can be completed")

            # 1. Захватываем блокировку на инвентарь-отправитель (Race Condition Protection)
            await self.uow.inventories.get_inventory_with_balances(
                transfer.from_id, with_for_update=True
            )

            # 2. Validate balances in from_inventory
            product_ids = [item.product_id for item in transfer.items]
            balances = await self.uow.transactions.get_balances_for_products(
                transfer.from_id, product_ids
            )

            for item in transfer.items:
                if balances.get(item.product_id, 0) < item.quantity:
                    raise ValueError(
                        f"Insufficient balance for product {item.product.name}"
                    )

            # 2. Create StockTransactions
            for item in transfer.items:
                await self.uow.transactions.add(
                    {
                        "product_id": item.product_id,
                        "transfer_id": transfer_id,
                        "from_id": transfer.from_id,
                        "to_id": transfer.to_id,
                        "quantity": item.quantity,
                    }
                )

            # 3. Update status
            transfer.status = TransferStatus.COMPLETED
            transfer.accepted_by_id = accepted_by_id

            await self.uow.commit()
            return transfer


class CapitalizeTaraService:
    """
    Оприходование тары клиента (INITIAL_BALANCE).
    Используется при переходе клиента в онлайн-систему,
    когда у клиента есть физическая тара, не учтенная в системе.
    """

    def __init__(
        self, uow: InventoryUnitOfWork, catalog_service: CatalogService
    ):
        self.uow = uow
        self.catalog_service = catalog_service

    async def capitalize_tara(
        self,
        dto: CapitalizeTaraRequest,
        created_by_id: uuid.UUID,
    ) -> dict:
        """
        Оприходование тары администратором (без лимитов).
        VIRTUAL_VENDOR → ClientInventory.
        """
        async with self.uow:
            inventory = await self.uow.inventories.get_inventory_with_balances(
                dto.client_inventory_id, inv_type=InventoryType.CLIENT
            )
            if not inventory:
                raise InventoryNotFoundError(
                    inventory_id=dto.client_inventory_id
                )

            vendor_inv = await self.uow.inventories.get_vendor_inventory()

            transfer = await self.uow.transfers.add(
                {
                    "from_id": vendor_inv.id,
                    "to_id": inventory.id,
                    "type": TransferType.INITIAL_BALANCE,
                    "status": TransferStatus.COMPLETED,
                    "created_by_id": created_by_id,
                    "accepted_by_id": created_by_id,
                }
            )

            for item in dto.items:
                await self.uow.transfer_items.add(
                    {
                        "transfer_id": transfer.id,
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                    }
                )
                await self.uow.transactions.add(
                    {
                        "product_id": item.product_id,
                        "transfer_id": transfer.id,
                        "from_id": vendor_inv.id,
                        "to_id": inventory.id,
                        "quantity": item.quantity,
                    }
                )

            await self.uow.commit()

            return {
                "transfer_id": transfer.id,
                "capitalized_items": [
                    {"product_id": item.product_id, "quantity": item.quantity}
                    for item in dto.items
                ],
            }

    async def capitalize_deficit(
        self,
        dto: CapitalizeDeficitRequest,
        client_id: uuid.UUID,
    ) -> dict:
        """
        Оприходование дефицита тары клиентом.
        Рассчитывает нехватку автоматически и оприходует ровно столько,
        сколько не хватает для текущей корзины (защита от фрода).
        """
        product_ids = [item.product_id for item in dto.items]
        products = await self.catalog_service.get_by_ids(product_ids)

        # Определяем какие товары требуют возвратной тары
        exchange_items = [
            (p, next(i for i in dto.items if i.product_id == p.id))
            for p in products
            if p.returnable_item_id is not None
        ]

        if not exchange_items:
            return {"transfer_id": None, "capitalized_items": []}

        async with self.uow:
            inventory = await self.uow.inventories.get_inventory_with_balances(
                dto.client_inventory_id, inv_type=InventoryType.CLIENT
            )
            if not inventory:
                raise InventoryNotFoundError(
                    inventory_id=dto.client_inventory_id
                )

            # Проверяем владельца инвентаря
            if inventory.user_id != client_id:
                raise InventoryNotFoundError(
                    inventory_id=dto.client_inventory_id
                )

            balances = {b.product_id: b.quantity for b in inventory.balances}

            # Рассчитываем дефицит
            items_to_capitalize: list[CapitalizeTaraItem] = []
            for product, item in exchange_items:
                required_tare_id = product.returnable_item_id
                if required_tare_id is None:
                    continue
                available = balances.get(required_tare_id, 0)
                deficit = item.quantity - available
                if deficit > 0:
                    items_to_capitalize.append(
                        CapitalizeTaraItem(
                            product_id=required_tare_id,
                            quantity=deficit,
                        )
                    )

            if not items_to_capitalize:
                return {"transfer_id": None, "capitalized_items": []}

            vendor_inv = await self.uow.inventories.get_vendor_inventory()

            transfer = await self.uow.transfers.add(
                {
                    "from_id": vendor_inv.id,
                    "to_id": inventory.id,
                    "type": TransferType.INITIAL_BALANCE,
                    "status": TransferStatus.COMPLETED,
                    "created_by_id": client_id,
                    "accepted_by_id": client_id,
                }
            )

            for cap_item in items_to_capitalize:
                await self.uow.transfer_items.add(
                    {
                        "transfer_id": transfer.id,
                        "product_id": cap_item.product_id,
                        "quantity": cap_item.quantity,
                    }
                )
                await self.uow.transactions.add(
                    {
                        "product_id": cap_item.product_id,
                        "transfer_id": transfer.id,
                        "from_id": vendor_inv.id,
                        "to_id": inventory.id,
                        "quantity": cap_item.quantity,
                    }
                )

            await self.uow.commit()

            return {
                "transfer_id": transfer.id,
                "capitalized_items": [
                    {"product_id": ci.product_id, "quantity": ci.quantity}
                    for ci in items_to_capitalize
                ],
            }
