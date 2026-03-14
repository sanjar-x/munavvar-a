import uuid
from collections.abc import Sequence

from src.infrastructure.database.models import Inventory, StockTransfer
from src.modules.inventory.enums import InventoryType, TransferStatus
from src.modules.inventory.schemas import (
    TransferCreate,
    TransferItemCreate,
    TransportCreate,
    TransportUpdate,
    WarehouseCreate,
)
from src.modules.inventory.uow import InventoryUnitOfWork


class TransportService:
    @staticmethod
    async def create_transport(
        uow: InventoryUnitOfWork, schema: TransportCreate
    ) -> Inventory:
        async with uow:
            # В реальной системе здесь должна быть проверка, user_id курьера
            transport = await uow.inventories.add({
                "user_id": schema.user_id,
                "name": schema.name,
                "type": InventoryType.COURIER,
            })
            await uow.commit()
            return transport

    @staticmethod
    async def get_transports(
        uow: InventoryUnitOfWork,
        skip: int = 0,
        limit: int = 100,
        user_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[Inventory], int]:
        async with uow:
            filters = {"type": InventoryType.COURIER, "is_active": True}
            if user_id:
                filters["user_id"] = user_id

            transports = await uow.inventories.get_multi(
                skip=skip,
                limit=limit,
                **(filters),  # type: ignore
            )
            total = await uow.inventories.count(**(filters))  # type: ignore
            return transports, total

    @staticmethod
    async def get_transport_with_balances(
        uow: InventoryUnitOfWork, transport_id: uuid.UUID
    ) -> Inventory | None:
        async with uow:
            return await uow.inventories.get_inventory_with_balances(
                transport_id, InventoryType.COURIER
            )

    @staticmethod
    async def update_transport(
        uow: InventoryUnitOfWork, transport_id: uuid.UUID, schema: TransportUpdate
    ) -> Inventory | None:
        async with uow:
            update_data = schema.model_dump(exclude_unset=True)
            if not update_data:
                return await uow.inventories.get(transport_id)

            transport = await uow.inventories.update(transport_id, update_data)
            await uow.commit()
            return transport

    @staticmethod
    async def delete_transport(
        uow: InventoryUnitOfWork, transport_id: uuid.UUID
    ) -> bool:
        async with uow:
            success = await uow.inventories.delete(transport_id)
            await uow.commit()
            return success


class WarehouseService:
    @staticmethod
    async def create_warehouse(
        uow: InventoryUnitOfWork, schema: WarehouseCreate
    ) -> Inventory:
        async with uow:
            warehouse = await uow.inventories.add({
                "user_id": schema.user_id,
                "name": schema.name,
                "type": InventoryType.WAREHOUSE,
            })
            await uow.commit()
            return warehouse

    @staticmethod
    async def get_warehouses(
        uow: InventoryUnitOfWork,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Inventory], int]:
        async with uow:
            filters = {"type": InventoryType.WAREHOUSE, "is_active": True}
            warehouses = await uow.inventories.get_multi(
                skip=skip,
                limit=limit,
                **(filters),  # type: ignore
            )
            total = await uow.inventories.count(**(filters))  # type: ignore
            return warehouses, total

    @staticmethod
    async def get_warehouse_with_balances(
        uow: InventoryUnitOfWork, warehouse_id: uuid.UUID
    ) -> Inventory | None:
        async with uow:
            return await uow.inventories.get_inventory_with_balances(
                warehouse_id, InventoryType.WAREHOUSE
            )

    @staticmethod
    async def get_warehouses_with_balances(
        uow: InventoryUnitOfWork,
    ) -> Sequence[Inventory]:
        async with uow:
            return await uow.inventories.get_all_warehouses_with_balances()


class StockTransferService:
    @staticmethod
    async def create_draft_transfer(
        uow: InventoryUnitOfWork, created_by_id: uuid.UUID, schema: TransferCreate
    ) -> StockTransfer:
        async with uow:
            # TODO: Validate inventories exist and types match the business logic
            transfer = await uow.transfers.add({
                "from_id": schema.from_id,
                "to_id": schema.to_id,
                "type": schema.type,
                "status": TransferStatus.DRAFT,
                "created_by_id": created_by_id,
            })
            await uow.commit()
            return transfer

    @staticmethod
    async def update_draft_items(
        uow: InventoryUnitOfWork,
        transfer_id: uuid.UUID,
        items_schema: list[TransferItemCreate],
    ) -> StockTransfer:
        async with uow:
            transfer = await uow.transfers.get_with_items_for_update(transfer_id)
            if not transfer:
                raise ValueError("Transfer not found")
            if transfer.status != TransferStatus.DRAFT:
                raise ValueError("Cannot update non-draft transfer")

            # Simple logic: replace old items with new ones or update
            # Here we'll clear and add to keep it simple, or find and update
            # Let's clear and re-add for simplicity in this specific task
            for item in transfer.items:
                await uow.transfer_items.delete(item.id)

            for item_data in items_schema:
                await uow.transfer_items.add({
                    "transfer_id": transfer_id,
                    "product_id": item_data.product_id,
                    "quantity": item_data.quantity,
                })

            await uow.commit()
            transfer = await uow.transfers.get_transfer(transfer_id)
            if not transfer:
                raise ValueError("Transfer not found after update")
            return transfer

    @staticmethod
    async def complete_transfer(
        uow: InventoryUnitOfWork,
        transfer_id: uuid.UUID,
        accepted_by_id: uuid.UUID,
    ) -> StockTransfer:
        async with uow:
            transfer = await uow.transfers.get_transfer(transfer_id)
            if not transfer:
                raise ValueError("Transfer not found")
            if transfer.status != TransferStatus.DRAFT:
                raise ValueError("Only draft transfers can be completed")

            # 1. Validate balances in from_inventory
            product_ids = [item.product_id for item in transfer.items]
            balances = await uow.transactions.get_balances_for_products(
                transfer.from_id, product_ids
            )

            for item in transfer.items:
                if balances.get(item.product_id, 0) < item.quantity:
                    raise ValueError(
                        f"Insufficient balance for product {item.product.name}"
                    )

            # 2. Create StockTransactions
            for item in transfer.items:
                await uow.transactions.add({
                    "product_id": item.product_id,
                    "transfer_id": transfer_id,
                    "from_id": transfer.from_id,
                    "to_id": transfer.to_id,
                    "quantity": item.quantity,
                })

            # 3. Update status
            transfer.status = TransferStatus.COMPLETED
            transfer.accepted_by_id = accepted_by_id

            await uow.commit()
            return transfer
