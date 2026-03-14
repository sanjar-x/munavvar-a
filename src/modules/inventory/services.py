# src/modules/inventory/services.py
import uuid
from typing import Sequence

from src.infrastructure.database.models import Inventory
from src.modules.inventory.enums import InventoryType
from src.modules.inventory.schemas import (
    TransportCreate,
    TransportUpdate,
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
            return await uow.inventories.get_with_balances(transport_id)

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
