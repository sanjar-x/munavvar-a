import uuid
from collections.abc import Sequence
from datetime import datetime

from src.core.exceptions import ConflictError
from src.infrastructure.database.models import Inventory, StockTransfer
from src.modules.catalog.public import CatalogService
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.inventory.exceptions import (
    CourierAlreadyAssignedError,
    InsufficientStockError,
    InventoryNotFoundError,
    InventoryTypeMismatchError,
    RouteLoopError,
)
from src.modules.inventory.schemas import (
    CapitalizeDeficitRequest,
    CapitalizeTaraItem,
    CapitalizeTaraRequest,
    CreateTransferRequest,
    TransportCreate,
    TransportUpdate,
    WarehouseCreate,
)
from src.modules.inventory.uow import InventoryUnitOfWork

# Допустимые маршруты для каждого типа накладной:
# (множество разрешённых типов отправителя, множество разрешённых типов получателя)
_VALID_ROUTES: dict[
    TransferType, tuple[frozenset[InventoryType], frozenset[InventoryType]]
] = {
    TransferType.COURIER_LOAD: (
        frozenset({InventoryType.WAREHOUSE}),
        frozenset({InventoryType.COURIER}),
    ),
    TransferType.COURIER_RETURN: (
        frozenset({InventoryType.COURIER}),
        frozenset({InventoryType.WAREHOUSE}),
    ),
    TransferType.CLIENT_DELIVERY: (
        frozenset({InventoryType.COURIER}),
        frozenset({InventoryType.CLIENT}),
    ),
    TransferType.CLIENT_RETURN: (
        frozenset({InventoryType.CLIENT}),
        frozenset({InventoryType.COURIER}),
    ),
    TransferType.LOSS_WRITE_OFF: (
        frozenset({
            InventoryType.WAREHOUSE,
            InventoryType.COURIER,
            InventoryType.CLIENT,
        }),
        frozenset({InventoryType.VIRTUAL_LOSS}),
    ),
    TransferType.INVENTORY_FINDING: (
        frozenset({InventoryType.VIRTUAL_VENDOR}),
        frozenset({InventoryType.WAREHOUSE, InventoryType.COURIER}),
    ),
    TransferType.INITIAL_BALANCE: (
        frozenset({InventoryType.VIRTUAL_VENDOR}),
        frozenset({
            InventoryType.CLIENT,
            InventoryType.WAREHOUSE,
            InventoryType.COURIER,
        }),
    ),
    TransferType.WAREHOUSE_SALE: (
        frozenset({InventoryType.WAREHOUSE}),
        frozenset({InventoryType.CLIENT}),
    ),
    TransferType.WAREHOUSE_TARA_RETURN: (
        frozenset({InventoryType.CLIENT}),
        frozenset({InventoryType.WAREHOUSE}),
    ),
}


class TransportService:
    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    async def create_transport(self, schema: TransportCreate) -> Inventory:
        async with self.uow:
            # В реальной системе здесь должна быть проверка, user_id курьера
            transport = await self.uow.inventories.add({
                "user_id": schema.user_id,
                "name": schema.name,
                "type": InventoryType.COURIER,
            })
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

            # Guard against violating uq_active_courier_inventory:
            # user_id is NOT NULL, so we cannot unassign — raise 409 instead.
            new_user_id = update_data.get("user_id")
            if new_user_id is not None:
                existing = await self.uow.inventories.get_courier_inventory(new_user_id)
                if existing and existing.id != transport_id:
                    raise CourierAlreadyAssignedError(
                        courier_id=new_user_id,
                        existing_transport_id=existing.id,
                    )

            transport = await self.uow.inventories.update(transport_id, update_data)
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
            existing = await self.uow.inventories.search_inventories(
                search_query=schema.name,
                inv_type=InventoryType.WAREHOUSE,
                limit=1,
            )
            if existing and existing[0].name == schema.name:
                raise ConflictError(
                    message=f"Склад с именем '{schema.name}' уже существует",
                    error_code="INVENTORY_NAME_DUPLICATE",
                    details={
                        "name": schema.name,
                        "existing_id": str(existing[0].id),
                    },
                )

            warehouse = await self.uow.inventories.add({
                "user_id": schema.user_id,
                "name": schema.name,
                "type": InventoryType.WAREHOUSE,
            })
            await self.uow.commit()
            return await self.uow.inventories.get_with_user(
                warehouse.id,
                active_only=False,
            )

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
            return await self.uow.inventories.get_all_warehouses_with_balances()


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

    async def create_transfer(
        self,
        created_by_id: uuid.UUID,
        schema: CreateTransferRequest,
    ) -> StockTransfer:
        """
        Единый метод создания и проведения накладной (single-step).
        """
        async with self.uow:
            # 1. Авто-подстановка виртуальных складов
            from_id = schema.from_id
            to_id = schema.to_id

            if schema.type in (
                TransferType.INVENTORY_FINDING,
                TransferType.INITIAL_BALANCE,
            ):
                vendor_inv = await self.uow.inventories.get_system_inventory(
                    InventoryType.VIRTUAL_VENDOR
                )
                from_id = vendor_inv.id

            if schema.type == TransferType.LOSS_WRITE_OFF:
                loss_inv = await self.uow.inventories.get_system_inventory(
                    InventoryType.VIRTUAL_LOSS
                )
                to_id = loss_inv.id

            # 2. Защита от петли
            if from_id == to_id:
                raise RouteLoopError(inventory_id=from_id)

            # 3. Валидация маршрута
            from_inventory = await self.uow.inventories.get(from_id)
            if not from_inventory:
                raise InventoryNotFoundError(inventory_id=from_id)
            to_inventory = await self.uow.inventories.get(to_id)
            if not to_inventory:
                raise InventoryNotFoundError(inventory_id=to_id)

            route = _VALID_ROUTES.get(schema.type)
            if route:
                allowed_from, allowed_to = route
                if from_inventory.type not in allowed_from:
                    raise InventoryTypeMismatchError(
                        inventory_id=from_inventory.id,
                        expected_type=str(allowed_from),
                        actual_type=from_inventory.type,
                    )
                if to_inventory.type not in allowed_to:
                    raise InventoryTypeMismatchError(
                        inventory_id=to_inventory.id,
                        expected_type=str(allowed_to),
                        actual_type=to_inventory.type,
                    )

            # 4. Блокировка и проверка остатков (пропуск для VIRTUAL_VENDOR)
            if from_inventory.type != InventoryType.VIRTUAL_VENDOR:
                from_inventory = await self.uow.inventories.get_inventory_with_balances(
                    from_id, with_for_update=True
                )
                balances = {b.product_id: b.quantity for b in from_inventory.balances}
                shortages: dict[uuid.UUID, int] = {}
                for item in schema.items:
                    available = balances.get(item.product_id, 0)
                    if available < item.quantity:
                        shortages[item.product_id] = item.quantity - available
                if shortages:
                    raise InsufficientStockError(shortages=shortages)

            # 5. Создаём накладную (сразу COMPLETED)
            transfer = await self.uow.transfers.add({
                "from_id": from_id,
                "to_id": to_id,
                "type": schema.type,
                "status": TransferStatus.COMPLETED,
                "created_by_id": created_by_id,
                "accepted_by_id": created_by_id,
                "reason": schema.reason,
                "route_sheet_id": schema.route_sheet_id,
            })

            # 6. Строки накладной и проводки в леджере
            for item in schema.items:
                await self.uow.transfer_items.add({
                    "transfer_id": transfer.id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                })
                await self.uow.transactions.add({
                    "product_id": item.product_id,
                    "transfer_id": transfer.id,
                    "from_id": from_id,
                    "to_id": to_id,
                    "quantity": item.quantity,
                })

            await self.uow.commit()
            return await self.uow.transfers.get_transfer(transfer.id)


class CapitalizeTaraService:
    """
    Оприходование тары клиента (INITIAL_BALANCE).
    Используется при переходе клиента в онлайн-систему,
    когда у клиента есть физическая тара, не учтенная в системе.
    """

    def __init__(self, uow: InventoryUnitOfWork, catalog_service: CatalogService):
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
                raise InventoryNotFoundError(inventory_id=dto.client_inventory_id)

            vendor_inv = await self.uow.inventories.get_vendor_inventory()

            transfer = await self.uow.transfers.add({
                "from_id": vendor_inv.id,
                "to_id": inventory.id,
                "type": TransferType.INITIAL_BALANCE,
                "status": TransferStatus.COMPLETED,
                "created_by_id": created_by_id,
                "accepted_by_id": created_by_id,
            })

            for item in dto.items:
                await self.uow.transfer_items.add({
                    "transfer_id": transfer.id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                })
                await self.uow.transactions.add({
                    "product_id": item.product_id,
                    "transfer_id": transfer.id,
                    "from_id": vendor_inv.id,
                    "to_id": inventory.id,
                    "quantity": item.quantity,
                })

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
                raise InventoryNotFoundError(inventory_id=dto.client_inventory_id)

            # Проверяем владельца инвентаря
            if inventory.user_id != client_id:
                raise InventoryNotFoundError(inventory_id=dto.client_inventory_id)

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

            transfer = await self.uow.transfers.add({
                "from_id": vendor_inv.id,
                "to_id": inventory.id,
                "type": TransferType.INITIAL_BALANCE,
                "status": TransferStatus.COMPLETED,
                "created_by_id": client_id,
                "accepted_by_id": client_id,
            })

            for cap_item in items_to_capitalize:
                await self.uow.transfer_items.add({
                    "transfer_id": transfer.id,
                    "product_id": cap_item.product_id,
                    "quantity": cap_item.quantity,
                })
                await self.uow.transactions.add({
                    "product_id": cap_item.product_id,
                    "transfer_id": transfer.id,
                    "from_id": vendor_inv.id,
                    "to_id": inventory.id,
                    "quantity": cap_item.quantity,
                })

            await self.uow.commit()

            return {
                "transfer_id": transfer.id,
                "capitalized_items": [
                    {"product_id": ci.product_id, "quantity": ci.quantity}
                    for ci in items_to_capitalize
                ],
            }
