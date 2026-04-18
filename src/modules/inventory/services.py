import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from src.common.pagination import (
    CursorInvalidError,
    CursorPaginationMeta,
    build_cursor_meta,
    decode_cursor,
)
from src.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
)
from src.core.security.permissions import Scope
from src.infrastructure.database.models import Inventory, StockTransfer
from src.modules.catalog.public import CatalogService
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.inventory.exceptions import (
    ArchivedProductsInTransferError,
    CourierAlreadyAssignedError,
    InsufficientStockError,
    InventoryNotFoundError,
    InventoryTypeMismatchError,
    RouteLoopError,
    TransferNotFoundError,
)
from src.modules.inventory.schemas import (
    CapitalizeDeficitRequest,
    CapitalizeTaraItem,
    CapitalizeTaraRequest,
    CreateTransferRequest,
    TransportCreate,
    TransportUpdate,
    WarehouseCreate,
    WarehouseUpdate,
)
from src.modules.inventory.uow import InventoryUnitOfWork

# Допустимые маршруты для каждого типа накладной:
# (множество разрешённых типов отправителя,
# множество разрешённых типов получателя)
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
        frozenset(
            {
                InventoryType.WAREHOUSE,
                InventoryType.COURIER,
                InventoryType.CLIENT,
            }
        ),
        frozenset({InventoryType.VIRTUAL_LOSS}),
    ),
    TransferType.INVENTORY_FINDING: (
        frozenset({InventoryType.VIRTUAL_VENDOR}),
        frozenset({InventoryType.WAREHOUSE, InventoryType.COURIER}),
    ),
    TransferType.INITIAL_BALANCE: (
        frozenset({InventoryType.VIRTUAL_VENDOR}),
        frozenset(
            {
                InventoryType.CLIENT,
                InventoryType.WAREHOUSE,
                InventoryType.COURIER,
            }
        ),
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

            # Guard against violating uq_active_courier_inventory:
            # user_id is NOT NULL, so we cannot unassign — raise 409 instead.
            new_user_id = update_data.get("user_id")
            if new_user_id is not None:
                existing = await self.uow.inventories.get_courier_inventory(
                    new_user_id
                )
                if existing and existing.id != transport_id:
                    raise CourierAlreadyAssignedError(
                        courier_id=new_user_id,
                        existing_transport_id=existing.id,
                    )

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
                raise BadRequestError(
                    message="Удаление системных складов запрещено",
                    error_code="SYSTEM_INVENTORY_DELETE_FORBIDDEN",
                    details={"transport_id": str(transport_id)},
                )

            success = await self.uow.inventories.delete(transport_id)
            await self.uow.commit()
            return success


class WarehouseService:
    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    async def create_warehouse(self, schema: WarehouseCreate) -> Inventory:
        async with self.uow:
            existing = await self.uow.inventories.get_by(
                name=schema.name,
                type=InventoryType.WAREHOUSE,
            )
            if existing:
                raise ConflictError(
                    message=f"Склад с именем '{schema.name}' уже существует",
                    error_code="INVENTORY_NAME_DUPLICATE",
                    details={
                        "name": schema.name,
                        "existing_id": str(existing.id),
                    },
                )

            warehouse = await self.uow.inventories.add(
                {
                    "user_id": schema.user_id,
                    "name": schema.name,
                    "type": InventoryType.WAREHOUSE,
                }
            )
            await self.uow.commit()
            result = await self.uow.inventories.get_with_user(
                warehouse.id,
                active_only=False,
            )
            if not result:
                raise InventoryNotFoundError(inventory_id=warehouse.id)
            return result

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
        owner_id: uuid.UUID | None = None,
    ) -> Sequence[Inventory]:
        async with self.uow:
            return await self.uow.inventories.get_all_warehouses_with_balances(
                owner_id=owner_id,
            )

    async def update_warehouse(
        self,
        warehouse_id: uuid.UUID,
        schema: WarehouseUpdate,
    ) -> Inventory | None:
        async with self.uow:
            warehouse = await self.uow.inventories.get(warehouse_id)
            if not warehouse or warehouse.type != InventoryType.WAREHOUSE:
                return None

            update_data = schema.model_dump(exclude_unset=True)
            if not update_data:
                return warehouse

            new_name = update_data.get("name")
            if new_name and new_name != warehouse.name:
                existing = await self.uow.inventories.search_inventories(
                    search_query=new_name,
                    inv_type=InventoryType.WAREHOUSE,
                    limit=1,
                )
                if existing and existing[0].name == new_name:
                    raise ConflictError(
                        message=(
                            f"Склад с именем '{new_name}' уже существует"
                        ),
                        error_code="INVENTORY_NAME_DUPLICATE",
                        details={
                            "name": new_name,
                            "existing_id": str(existing[0].id),
                        },
                    )

            await self.uow.inventories.update(warehouse_id, update_data)
            await self.uow.commit()
            return await self.uow.inventories.get_with_user(
                warehouse_id, active_only=False
            )

    async def archive_warehouse(self, warehouse_id: uuid.UUID) -> bool:
        async with self.uow:
            warehouse = await self.uow.inventories.get(warehouse_id)
            if not warehouse or warehouse.type != InventoryType.WAREHOUSE:
                return False

            if warehouse.type in (
                InventoryType.VIRTUAL_VENDOR,
                InventoryType.VIRTUAL_LOSS,
            ):
                raise BadRequestError(
                    message="Удаление системных складов запрещено",
                    error_code="SYSTEM_INVENTORY_DELETE_FORBIDDEN",
                    details={"warehouse_id": str(warehouse_id)},
                )

            success = await self.uow.inventories.archive(warehouse_id)
            await self.uow.commit()
            return success

    async def search_inventories(
        self,
        search_query: str,
        inv_type: InventoryType | None = None,
        limit: int = 50,
    ) -> Sequence[Inventory]:
        async with self.uow:
            return await self.uow.inventories.search_inventories(
                search_query=search_query,
                inv_type=inv_type,
                limit=limit,
            )

    async def search_inventories_cursor(
        self,
        search_query: str,
        inv_type: InventoryType | None = None,
        size: int = 50,
        cursor_token: str | None = None,
    ) -> tuple[Sequence[Inventory], CursorPaginationMeta]:
        """Cursor-вариант ``search_inventories`` (FRD §15.2)."""
        cursor: tuple[str, uuid.UUID] | None = None
        if cursor_token:
            sort_value, last_id = decode_cursor(cursor_token)
            if not isinstance(sort_value, str):
                raise CursorInvalidError()
            cursor = (sort_value, last_id)
        async with self.uow:
            rows = await self.uow.inventories.search_inventories_cursor(
                search_query=search_query,
                inv_type=inv_type,
                size=size,
                cursor=cursor,
            )
        page, meta = build_cursor_meta(list(rows), size, lambda r: r.name)
        return page, meta

    async def get_warehouses_with_balances_cursor(
        self,
        owner_id: uuid.UUID | None = None,
        size: int = 50,
        cursor_token: str | None = None,
    ) -> tuple[Sequence[Inventory], CursorPaginationMeta]:
        """Cursor-вариант ``get_warehouses_with_balances`` (FRD §15.2)."""
        cursor: tuple[str, uuid.UUID] | None = None
        if cursor_token:
            sort_value, last_id = decode_cursor(cursor_token)
            if not isinstance(sort_value, str):
                raise CursorInvalidError()
            cursor = (sort_value, last_id)
        async with self.uow:
            repo = self.uow.inventories
            rows = await repo.get_all_warehouses_with_balances_cursor(
                owner_id=owner_id,
                size=size,
                cursor=cursor,
            )
        page, meta = build_cursor_meta(list(rows), size, lambda r: r.name)
        return page, meta


# Типы накладных, требующие расширенного права logistics:adjustment.
# Кладовщик с logistics:transfer не может их создавать.
_ADJUSTMENT_TRANSFER_TYPES: frozenset[TransferType] = frozenset(
    {
        TransferType.INVENTORY_FINDING,
        TransferType.INITIAL_BALANCE,
        TransferType.LOSS_WRITE_OFF,
    }
)


class StockTransferService:
    def __init__(
        self,
        uow: InventoryUnitOfWork,
        catalog_service: CatalogService,
    ):
        self.uow = uow
        self.catalog_service = catalog_service

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
        warehouse_owner_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
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
                warehouse_owner_id=warehouse_owner_id,
                warehouse_id=warehouse_id,
            )

    async def search_transfers_cursor(
        self,
        size: int = 50,
        cursor_token: str | None = None,
        status: TransferStatus | None = None,
        transfer_type: TransferType | None = None,
        from_inventory_id: uuid.UUID | None = None,
        to_inventory_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        warehouse_owner_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[StockTransfer], CursorPaginationMeta]:
        """Cursor-вариант ``search_transfers`` (FRD §15.2)."""
        cursor: tuple[datetime, uuid.UUID] | None = None
        if cursor_token:
            sort_value, last_id = decode_cursor(cursor_token)
            if not isinstance(sort_value, datetime):
                raise CursorInvalidError()
            cursor = (sort_value, last_id)
        async with self.uow:
            rows = await self.uow.transfers.search_transfers_cursor(
                size=size,
                cursor=cursor,
                status=status,
                transfer_type=transfer_type,
                from_inventory_id=from_inventory_id,
                to_inventory_id=to_inventory_id,
                date_from=date_from,
                date_to=date_to,
                warehouse_owner_id=warehouse_owner_id,
                warehouse_id=warehouse_id,
            )
        page, meta = build_cursor_meta(
            list(rows), size, lambda r: r.created_at
        )
        return page, meta

    async def create_transfer(
        self,
        created_by_id: uuid.UUID,
        schema: CreateTransferRequest,
        caller_scopes: list[str] | None = None,
    ) -> StockTransfer:
        """
        Единый метод создания и проведения накладной (single-step).

        Типы INVENTORY_FINDING, INITIAL_BALANCE и LOSS_WRITE_OFF требуют
        scope logistics:adjustment (только Админ). Кладовщик с
        logistics:transfer не может их создавать.
        """
        # 0. Проверка scope для чувствительных типов накладных
        if schema.type in _ADJUSTMENT_TRANSFER_TYPES and (
            caller_scopes is None
            or Scope.LOGISTICS_ADJUSTMENT not in caller_scopes
        ):
            raise ForbiddenError(
                message=(
                    "Для создания накладной типа"
                    f" '{schema.type}' требуется"
                    " разрешение logistics:adjustment."
                ),
                error_code="INSUFFICIENT_PERMISSIONS",
                details={"transfer_type": schema.type},
            )

        # 0.1. Проверка: все товары в накладной должны быть активными.
        # get_by_ids фильтрует по is_active=True — отсутствующие ID
        # означают архивированные товары.
        product_ids = [item.product_id for item in schema.items]
        active_products = await self.catalog_service.get_by_ids(product_ids)
        active_ids = {p.id for p in active_products}
        archived_ids = [pid for pid in product_ids if pid not in active_ids]
        if archived_ids:
            raise ArchivedProductsInTransferError(
                archived_product_ids=archived_ids
            )

        async with self.uow:
            # 1. Авто-подстановка виртуальных складов
            from_id: uuid.UUID | None = schema.from_id
            to_id: uuid.UUID | None = schema.to_id

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

            if from_id is None:
                raise BadRequestError(
                    message="Не указан склад-отправитель",
                    error_code="MISSING_FROM_ID",
                )
            if to_id is None:
                raise BadRequestError(
                    message="Не указан склад-получатель",
                    error_code="MISSING_TO_ID",
                )

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
                locked = (
                    await self.uow.inventories.get_inventory_with_balances(
                        from_id, with_for_update=True
                    )
                )
                if not locked:
                    raise InventoryNotFoundError(inventory_id=from_id)
                balances = {b.product_id: b.quantity for b in locked.balances}
                requested_quantities: dict[uuid.UUID, int] = {}
                for item in schema.items:
                    requested_quantities[item.product_id] = (
                        requested_quantities.get(item.product_id, 0)
                        + item.quantity
                    )
                shortages: dict[uuid.UUID, int] = {}
                for (
                    product_id,
                    requested_quantity,
                ) in requested_quantities.items():
                    available = balances.get(product_id, 0)
                    if available < requested_quantity:
                        shortages[product_id] = requested_quantity - available
                if shortages:
                    raise InsufficientStockError(shortages=shortages)

            # 5. Создаём накладную (сразу COMPLETED)
            transfer = await self.uow.transfers.add(
                {
                    "from_id": from_id,
                    "to_id": to_id,
                    "type": schema.type,
                    "status": TransferStatus.COMPLETED,
                    "created_by_id": created_by_id,
                    "accepted_by_id": created_by_id,
                    "reason": schema.reason,
                    "route_sheet_id": schema.route_sheet_id,
                }
            )

            # 6. Строки накладной и проводки в леджере (batch inserts)
            transfer_items_data = [
                {
                    "transfer_id": transfer.id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                }
                for item in schema.items
            ]
            stock_transactions_data = [
                {
                    "product_id": item.product_id,
                    "transfer_id": transfer.id,
                    "from_id": from_id,
                    "to_id": to_id,
                    "quantity": item.quantity,
                }
                for item in schema.items
            ]
            await self.uow.transfer_items.add_many(transfer_items_data)
            try:
                await self.uow.transactions.add_many(stock_transactions_data)
            except IntegrityError as exc:
                # Trigger rejects negative balances for
                # non-virtual inventories — convert to
                # domain error for a clean API response.
                await self.uow.rollback()
                raise InsufficientStockError(shortages={}) from exc

            await self.uow.commit()
            result = await self.uow.transfers.get_transfer(transfer.id)
            if not result:
                raise TransferNotFoundError(transfer_id=transfer.id)
            return result


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

    async def capitalize_tara_for_client(
        self,
        client_id: uuid.UUID,
        items: list[CapitalizeTaraItem],
        created_by_id: uuid.UUID,
    ) -> dict:
        """
        Оприходование тары для клиента по его user_id.
        Разрешает client_id → client_inventory_id и выполняет
        оприходование в одной атомарной транзакции.
        """
        async with self.uow:
            client_inv = await self.uow.inventories.get_client_inventory(
                client_id
            )
            if not client_inv:
                raise InventoryNotFoundError(inventory_id=client_id)

            vendor_inv = await self.uow.inventories.get_vendor_inventory()

            transfer = await self.uow.transfers.add(
                {
                    "from_id": vendor_inv.id,
                    "to_id": client_inv.id,
                    "type": TransferType.INITIAL_BALANCE,
                    "status": TransferStatus.COMPLETED,
                    "created_by_id": created_by_id,
                    "accepted_by_id": created_by_id,
                }
            )

            for item in items:
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
                        "to_id": client_inv.id,
                        "quantity": item.quantity,
                    }
                )

            await self.uow.commit()

            return {
                "transfer_id": transfer.id,
                "capitalized_items": [
                    {"product_id": item.product_id, "quantity": item.quantity}
                    for item in items
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


# =====================================================================
# НОВЫЕ СЕРВИСЫ: StockLedger / Balances (FRD §6, §9)
# =====================================================================

from datetime import UTC, timedelta  # noqa: E402

from src.modules.inventory.exceptions import (  # noqa: E402
    DatePresetConflictError,
    DateRangeInvalidError,
    PaginationTooDeepError,
    QuantityConflictError,
    QuantityRangeInvalidError,
)
from src.modules.inventory.schemas import (  # noqa: E402
    BalanceFilter,
    BalanceRowItem,
    BalancesListResponse,
    BalanceSummary,
    InventoryShortRef,
    OffsetPaginationMeta,
    ProductSimpleResponse,
    StockTransactionFilter,
    StockTransactionItem,
    StockTransactionsListResponse,
    StockTransactionSummary,
)

MAX_PAGE_DEPTH = 10_000


def _check_pagination(page: int, size: int) -> None:
    if page * size > MAX_PAGE_DEPTH:
        raise PaginationTooDeepError(page=page, size=size)


def _total_pages(total: int, size: int) -> int:
    if size <= 0:
        return 0
    return (total + size - 1) // size


def _validate_stock_transaction_filter(f: StockTransactionFilter) -> None:
    if f.quantity_eq is not None and (
        f.quantity_from is not None or f.quantity_to is not None
    ):
        raise QuantityConflictError()
    if (
        f.quantity_from is not None
        and f.quantity_to is not None
        and f.quantity_from > f.quantity_to
    ):
        raise QuantityRangeInvalidError()
    if f.date_preset is not None and (
        f.date_from is not None or f.date_to is not None
    ):
        raise DatePresetConflictError()
    if (
        f.date_from is not None
        and f.date_to is not None
        and f.date_from > f.date_to
    ):
        raise DateRangeInvalidError()


def _validate_balance_filter(f: BalanceFilter) -> None:
    if (
        f.quantity_from is not None
        and f.quantity_to is not None
        and f.quantity_from > f.quantity_to
    ):
        raise QuantityRangeInvalidError()


def _resolve_date_preset(
    f: StockTransactionFilter,
) -> StockTransactionFilter:
    """Развернуть `date_preset` в `date_from`/`date_to`.

    TZ — `Asia/Tashkent`. Возвращает новый объект фильтра.
    """
    if f.date_preset is None:
        return f
    try:
        from zoneinfo import ZoneInfo
    except ImportError:  # pragma: no cover
        return f

    tz = ZoneInfo("Asia/Tashkent")
    now_local = datetime.now(tz)
    today = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    preset = f.date_preset
    if preset == "today":
        start_local = today
        end_local = today + timedelta(days=1)
    elif preset == "yesterday":
        start_local = today - timedelta(days=1)
        end_local = today
    elif preset == "this_week":
        start_local = today - timedelta(days=today.weekday())
        end_local = start_local + timedelta(days=7)
    elif preset == "last_week":
        this_monday = today - timedelta(days=today.weekday())
        start_local = this_monday - timedelta(days=7)
        end_local = this_monday
    elif preset == "this_month":
        start_local = today.replace(day=1)
        if start_local.month == 12:
            end_local = start_local.replace(year=start_local.year + 1, month=1)
        else:
            end_local = start_local.replace(month=start_local.month + 1)
    elif preset == "last_month":
        first_this = today.replace(day=1)
        if first_this.month == 1:
            start_local = first_this.replace(
                year=first_this.year - 1, month=12
            )
        else:
            start_local = first_this.replace(month=first_this.month - 1)
        end_local = first_this
    else:
        return f

    return f.model_copy(
        update={
            "date_preset": None,
            "date_from": start_local.astimezone(UTC),
            "date_to": end_local.astimezone(UTC),
        }
    )


def _normalize_stock_q(filters):
    """Применить нормализацию `q` (FRD §4.6) к полю фильтра."""
    from src.modules.inventory.search import normalize_q

    if filters.q is None:
        return filters
    return filters.model_copy(update={"q": normalize_q(filters.q)})


def _normalize_balance_q(filters):
    from src.modules.inventory.search import normalize_q

    if filters.q is None:
        return filters
    return filters.model_copy(update={"q": normalize_q(filters.q)})


def _to_inventory_short(inv) -> InventoryShortRef:
    return InventoryShortRef.model_validate(inv)


def _stock_transaction_to_item(st) -> StockTransactionItem:
    return StockTransactionItem(
        id=st.id,
        product_id=st.product_id,
        product=ProductSimpleResponse.model_validate(st.product),
        quantity=st.quantity,
        from_inventory=_to_inventory_short(st.from_inventory),
        to_inventory=_to_inventory_short(st.to_inventory),
        transfer_id=st.transfer_id,
        transfer_type=st.transfer.type,
        created_at=st.created_at,
    )


class StockLedgerService:
    """Read-only сервис для журнала движений (FRD §6)."""

    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    async def list(
        self,
        filters: StockTransactionFilter,
        page: int,
        size: int,
    ) -> StockTransactionsListResponse:
        _check_pagination(page, size)
        filters = _normalize_stock_q(filters)
        _validate_stock_transaction_filter(filters)
        filters = _resolve_date_preset(filters)

        async with self.uow as uow:
            total, rows = await uow.transactions.search_with_filters(
                filters=filters,
                skip=(page - 1) * size,
                limit=size,
            )
            agg = await uow.transactions.summarize_with_filters(filters)

        items = [_stock_transaction_to_item(st) for st in rows]
        return StockTransactionsListResponse(
            items=items,
            pagination=OffsetPaginationMeta(
                page=page,
                size=size,
                total_count=total,
                total_pages=_total_pages(total, size),
            ),
            summary=StockTransactionSummary(**agg),
        )


class BalanceService:
    """Read-only сервис для остатков (FRD §9)."""

    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    async def list(
        self,
        filters: BalanceFilter,
        page: int,
        size: int,
    ) -> BalancesListResponse:
        _check_pagination(page, size)
        filters = _normalize_balance_q(filters)
        _validate_balance_filter(filters)

        async with self.uow as uow:
            total, rows = await uow.balances.search_with_filters(
                filters=filters,
                skip=(page - 1) * size,
                limit=size,
            )
            agg = await uow.balances.summarize_with_filters(filters)

        items = [
            BalanceRowItem(
                product=ProductSimpleResponse.model_validate(b.product),
                inventory=_to_inventory_short(b.inventory),
                quantity=b.quantity,
            )
            for b in rows
        ]
        return BalancesListResponse(
            items=items,
            pagination=OffsetPaginationMeta(
                page=page,
                size=size,
                total_count=total,
                total_pages=_total_pages(total, size),
            ),
            summary=BalanceSummary(**agg),
        )
