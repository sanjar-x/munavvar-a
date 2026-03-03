# src/modules/inventory/services.py
import uuid
from datetime import UTC, datetime

from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.inventory.exceptions import (
    BadRequestError,
    EmptyTransferError,
    InsufficientStockError,
    InvalidQuantityError,
    InvalidTransferStatusError,
    InventoryNotFoundError,
    InventoryTypeMismatchError,
    NotFoundError,
    RouteLoopError,
    TransferNotFoundError,
    VirtualInventoryConfigurationError,
)
from src.modules.inventory.schemas import (
    AdjustmentItem,
    CreateLocation,
    InventoriesResponse,
    InventoryResponse,
    Item,
    StockTransferItemResponse,
    StockTransferResponse,
    TransferResult,
)
from src.modules.inventory.uow import InventoryUnitOfWork


class InventoryService:
    """Сервис управления инфраструктурными узлами (Точками хранения)."""

    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    async def bootstrap_system_inventories(
        self, system_user_id: uuid.UUID
    ) -> None:
        """
        DevOps/Startup метод.
        Гарантирует, что системные виртуальные локации существуют в БД
        и привязаны к системному пользователю.
        """
        system_types = {
            InventoryType.VIRTUAL_VENDOR: "Системный: Поставщик тары",
            InventoryType.VIRTUAL_LOSS: "Системный: Списание и брак",
        }

        async with self.uow:
            for inv_type, default_name in system_types.items():
                existing = (
                    await self.uow.inventories.get_system_virtual_inventory(
                        inv_type
                    )
                )
                if not existing:
                    await self.uow.inventories.add(
                        {
                            "name": default_name,
                            "type": inv_type,
                            "user_id": system_user_id,  # <--- Привязываем к System User
                        }
                    )
            await self.uow.commit()

    async def create_inventory(self, dto: CreateLocation) -> InventoryResponse:
        """Универсальный метод создания локации (Склад, Машина, Клиент)."""

        # Строгая валидация возвращена: у любой локации должен быть владелец (включая System User)
        if not dto.user_id:
            raise BadRequestError(
                message="Обязательно указание user_id для любой локации"
            )

        async with self.uow:
            # Защита от дублей: один курьер = одна активная машина
            if dto.type == InventoryType.COURIER:
                existing_truck = (
                    await self.uow.inventories.get_courier_inventory(
                        dto.user_id
                    )
                )
                if existing_truck:
                    raise BadRequestError(
                        message="У этого курьера уже есть активная машина. Деактивируйте старую."
                    )

            new_inventory = await self.uow.inventories.add(
                {
                    "name": dto.name,
                    "type": dto.type,
                    "user_id": dto.user_id,
                }
            )
            await self.uow.commit()

            return InventoryResponse.model_validate(new_inventory)

    async def update_inventory(
        self, inventory_id: uuid.UUID, new_name: str
    ) -> InventoryResponse:
        """Переименование склада, адреса или машины (без изменения типа)."""
        if not new_name.strip():
            raise BadRequestError(
                message="Название локации не может быть пустым"
            )

        async with self.uow:
            inventory = await self.uow.inventories.get(inventory_id)
            if not inventory:
                raise InventoryNotFoundError(inventory_id=inventory_id)

            updated_inventory = await self.uow.inventories.update(
                inventory_id, {"name": new_name.strip()}
            )
            await self.uow.commit()

            return InventoryResponse.model_validate(updated_inventory)

    async def get_inventory_by_id(
        self, inventory_id: uuid.UUID
    ) -> InventoryResponse:
        """Получить локацию по ID."""
        async with self.uow:
            inventory = await self.uow.inventories.get(inventory_id)
            if not inventory:
                raise InventoryNotFoundError(inventory_id=inventory_id)
            return InventoryResponse.model_validate(inventory)

    async def get_couriers_inventories(self) -> list[InventoriesResponse]:
        async with self.uow:
            inventories = await self.uow.inventories.get_couriers_inventories()
            inventories_with_balances = []
            for inventory in list(inventories):
                balances = list(
                    await self.uow.transactions.get_balances(inventory.id)
                )
                inventories_with_balances.append(
                    InventoriesResponse(inventory=inventory, balances=balances)
                )
            return inventories_with_balances

    async def get_client_addresses(
        self, user_id: uuid.UUID
    ) -> list[InventoryResponse]:
        """Получить все адреса доставки конкретного клиента (B2B/B2C)."""
        async with self.uow:
            inventories = await self.uow.inventories.get_client_inventories(
                user_id
            )
            return [
                InventoryResponse.model_validate(inv) for inv in inventories
            ]


class StockTransferService:
    """
    Сервис для чтения и поиска накладных (Query Service).
    Отдает данные из Строгого Леджера (StockTransaction) без мутаций.
    """

    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    # --- ЧТЕНИЕ ОСТАТКОВ ---

    # --- ЧТЕНИЕ НАКЛАДНЫХ (СУЩЕСТВУЮЩЕЕ) ---

    async def get_transfer_details(
        self, transfer_id: uuid.UUID
    ) -> StockTransferResponse:
        async with self.uow:
            transfer = await self.uow.transfers.get_with_details(transfer_id)
            if not transfer:
                raise TransferNotFoundError(transfer_id=transfer_id)
            return StockTransferResponse.model_validate(transfer)

    async def get_transfers_by_order(
        self, order_id: uuid.UUID
    ) -> list[StockTransferResponse]:
        async with self.uow:
            transfers = await self.uow.transfers.get_by_order_id(order_id)
            return [StockTransferResponse.model_validate(t) for t in transfers]

    async def get_outgoing_drafts(
        self, warehouse_id: uuid.UUID
    ) -> list[StockTransferResponse]:
        async with self.uow:
            transfers = await self.uow.transfers.get_outgoing_drafts(
                warehouse_id
            )
            return [StockTransferResponse.model_validate(t) for t in transfers]

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
    ) -> list[StockTransferResponse]:
        async with self.uow:
            transfers = await self.uow.transfers.search_transfers(
                skip=skip,
                limit=limit,
                status=status,
                transfer_type=transfer_type,
                from_inventory_id=from_inventory_id,
                to_inventory_id=to_inventory_id,
                date_from=date_from,
                date_to=date_to,
            )
            return [StockTransferResponse.model_validate(t) for t in transfers]


class StockTransferItemService:
    """
    Сервис для точечного управления товарами внутри DRAFT-накладной (Корзины).
    """

    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    async def add_or_increment_item(
        self, transfer_id: uuid.UUID, item_dto: Item
    ) -> StockTransferItemResponse:
        """
        Бизнес-кейс: Работа со сканером штрихкодов.
        Если товар уже есть в черновике - увеличивает quantity.
        Если нет - добавляет новую строку.
        """
        async with self.uow:
            transfer = await self.uow.transfers.get_with_details(
                transfer_id, with_for_update=True
            )
            if not transfer:
                raise TransferNotFoundError(transfer_id=transfer_id)

            if transfer.status != TransferStatus.DRAFT:
                raise InvalidTransferStatusError(
                    current_status=transfer.status,
                    expected_status=TransferStatus.DRAFT,
                    message="Добавлять товары можно только в черновик (DRAFT)",
                )
            existing_item = next(
                (
                    item
                    for item in transfer.items
                    if item.product_id == item_dto.product_id
                ),
                None,
            )

            if existing_item:
                new_quantity = existing_item.quantity + item_dto.quantity
                updated_item = await self.uow.transfer_items.update(
                    existing_item.id, {"quantity": new_quantity}
                )
                await self.uow.commit()
                return StockTransferItemResponse.model_validate(updated_item)
            else:
                # Создание нового
                new_item = await self.uow.transfer_items.add(
                    {
                        "transfer_id": transfer.id,
                        "product_id": item_dto.product_id,
                        "quantity": item_dto.quantity,
                    }
                )
                await self.uow.commit()
                return StockTransferItemResponse.model_validate(new_item)

    async def update_item_quantity_in_draft(
        self, transfer_id: uuid.UUID, item_id: uuid.UUID, new_quantity: int
    ) -> StockTransferItemResponse:
        """
        Изменить количество конкретного товара в черновике (вручную с клавиатуры терминала).
        """
        if new_quantity <= 0:
            raise InvalidQuantityError(
                product_id="unknown", quantity=new_quantity
            )

        async with self.uow:
            transfer = await self.uow.transfers.get_with_details(
                transfer_id, with_for_update=True
            )
            if not transfer:
                raise TransferNotFoundError(transfer_id=transfer_id)

            if transfer.status != TransferStatus.DRAFT:
                raise InvalidTransferStatusError(
                    current_status=transfer.status,
                    expected_status=TransferStatus.DRAFT,
                    message="Изменять количество можно только в черновике (DRAFT)",
                )

            # Валидация принадлежности
            if not any(item.id == item_id for item in transfer.items):
                raise NotFoundError(
                    message="Строка товара не найдена в указанной накладной"
                )

            updated_item = await self.uow.transfer_items.update(
                item_id, {"quantity": new_quantity}
            )
            await self.uow.commit()
            return StockTransferItemResponse.model_validate(updated_item)

    async def remove_item_from_draft(
        self, transfer_id: uuid.UUID, item_id: uuid.UUID
    ) -> None:
        """Удалить строку товара (свайп влево)."""
        async with self.uow:
            transfer = await self.uow.transfers.get_with_details(
                transfer_id, with_for_update=True
            )
            if not transfer:
                raise TransferNotFoundError(transfer_id=transfer_id)

            if transfer.status != TransferStatus.DRAFT:
                raise InvalidTransferStatusError(
                    current_status=transfer.status,
                    expected_status=TransferStatus.DRAFT,
                    message="Удалять товары можно только из черновика (DRAFT)",
                )

            success = await self.uow.transfer_items.delete(item_id)
            if not success:
                raise NotFoundError(message="Строка товара не найдена")

            await self.uow.commit()


class WarehouseCommandService:
    """
    Сервис управления главными складами и производством (HOD Business).
    Вся работа с БД строго через UnitOfWork.
    """

    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    # --- 3.1. Управление черновиками сборки ---

    async def add_items_to_transfer(
        self,
        from_id: uuid.UUID,
        to_id: uuid.UUID,
        created_by_id: uuid.UUID,
        items: list[Item],
        transfer_id: uuid.UUID | None = None,
    ) -> TransferResult:
        async with self.uow:
            if from_id == to_id:
                raise RouteLoopError(inventory_id=from_id)

            from_inv = await self.uow.inventories.get(from_id)
            to_inv = await self.uow.inventories.get(to_id)

            if not from_inv:
                raise InventoryNotFoundError(
                    inventory_id=from_id, message="Склад отправителя не найден"
                )
            if not to_inv:
                raise InventoryNotFoundError(
                    inventory_id=to_id,
                    message="Склад получателя (Машина/Склад) не найден",
                )

            for item in items:
                if item.quantity <= 0:
                    raise InvalidQuantityError(
                        product_id=item.product_id, quantity=item.quantity
                    )

            if transfer_id:
                transfer = await self.uow.transfers.get_with_details(
                    transfer_id, with_for_update=True
                )
                if not transfer:
                    raise TransferNotFoundError(transfer_id=transfer_id)
                if transfer.status != TransferStatus.DRAFT:
                    raise InvalidTransferStatusError(
                        current_status=transfer.status,
                        expected_status=TransferStatus.DRAFT,
                        message="Изменять товары можно только в черновике",
                    )
                if transfer.from_id != from_id or transfer.to_id != to_id:
                    raise RouteLoopError(
                        inventory_id=from_id,
                        message="Маршрут в существующей накладной отличается",
                    )
            else:
                transfer = await self.uow.transfers.add(
                    {
                        "from_id": from_id,
                        "to_id": to_id,
                        "created_by_id": created_by_id,
                        "type": TransferType.WAREHOUSE_TRANSFER,
                        "status": TransferStatus.DRAFT,
                    }
                )

            # Агрегация товаров (защита от дублирования строк в корзине)
            current_items = {
                item.product_id: item.quantity
                for item in (transfer.items if transfer_id else [])
            }
            for new_item in items:
                current_items[new_item.product_id] = (
                    current_items.get(new_item.product_id, 0)
                    + new_item.quantity
                )

            if transfer_id:
                await self.uow.transfer_items.clear_draft_items(transfer.id)

            new_draft_items = [
                {
                    "transfer_id": transfer.id,
                    "product_id": p_id,
                    "quantity": qty,
                }
                for p_id, qty in current_items.items()
            ]

            if not new_draft_items:
                raise EmptyTransferError(transfer_id=transfer.id)

            await self.uow.transfer_items.add_many(new_draft_items)
            await self.uow.commit()

            return TransferResult(
                transfer_id=transfer.id,
                status=transfer.status,
                created_at=datetime.now(UTC),
            )

    # --- 3.2. Универсальное проведение накладной ---

    async def complete_draft_transfer(
        self, transfer_id: uuid.UUID, accepted_by_id: uuid.UUID
    ) -> TransferResult:
        """
        Переводит собранный DRAFT в COMPLETED.
        Товар мгновенно перемещается с Главного Склада в Машину Курьера.
        """
        async with self.uow:
            transfer = await self.uow.transfers.get_with_details(
                transfer_id, with_for_update=True
            )
            if not transfer:
                raise TransferNotFoundError(transfer_id=transfer_id)

            if transfer.status == TransferStatus.COMPLETED:
                return TransferResult(
                    transfer_id=transfer.id,
                    status=transfer.status,
                    created_at=transfer.created_at,
                )

            if transfer.status != TransferStatus.DRAFT:
                raise InvalidTransferStatusError(
                    current_status=transfer.status,
                    expected_status=TransferStatus.DRAFT,
                    message="Провести можно только накладную в статусе DRAFT",
                )

            if not transfer.items:
                raise EmptyTransferError(transfer_id=transfer.id)

            # Bulk проверка остатков на складе-отправителе
            product_ids = [item.product_id for item in transfer.items]
            balances = await self.uow.transactions.get_balances_for_products(
                transfer.from_id, product_ids
            )

            deficit = {}
            for item in transfer.items:
                if balances.get(item.product_id, 0) < item.quantity:
                    deficit[item.product_id] = item.quantity - balances.get(
                        item.product_id, 0
                    )
            if deficit:
                raise InsufficientStockError(shortages=deficit)

            # Переливаем товары из Корзины в Строгий Леджер
            transactions_data = [
                {
                    "transfer_id": transfer.id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "from_id": transfer.from_id,
                    "to_id": transfer.to_id,
                }
                for item in transfer.items
            ]
            await self.uow.transactions.add_many(transactions_data)
            await self.uow.transfer_items.clear_draft_items(transfer.id)

            await self.uow.transfers.update(
                transfer.id,
                {
                    "status": TransferStatus.COMPLETED,
                    "accepted_by_id": accepted_by_id,
                },
            )

            await self.uow.commit()
            return TransferResult(
                transfer_id=transfer.id,
                status=TransferStatus.COMPLETED,
                created_at=datetime.now(UTC),
            )

    # --- 3.3. Закупка тары у поставщика ---

    async def execute_vendor_receipt(
        self,
        warehouse_id: uuid.UUID,
        created_by_id: uuid.UUID,
        items: list[Item],
    ) -> TransferResult:
        if not items:
            raise EmptyTransferError(
                transfer_id="new_receipt",
                message="Нельзя создать пустую накладную закупки",
            )

        async with self.uow:
            warehouse = await self.uow.inventories.get(warehouse_id)
            if not warehouse:
                raise InventoryNotFoundError(inventory_id=warehouse_id)
            if warehouse.type != InventoryType.WAREHOUSE:
                raise InventoryTypeMismatchError(
                    inventory_id=warehouse_id,
                    expected_type=InventoryType.WAREHOUSE,
                    actual_type=warehouse.type,
                    message="Оприходовать закупку можно только",
                )

            vendor_inv = (
                await self.uow.inventories.get_system_virtual_inventory(
                    InventoryType.VIRTUAL_VENDOR
                )
            )
            if not vendor_inv:
                raise VirtualInventoryConfigurationError(
                    v_type=InventoryType.VIRTUAL_VENDOR
                )

            transfer = await self.uow.transfers.add(
                {
                    "from_id": vendor_inv.id,
                    "to_id": warehouse_id,
                    "created_by_id": created_by_id,
                    "type": TransferType.PURCHASE,
                    "status": TransferStatus.COMPLETED,
                }
            )

            transactions_data = [
                {
                    "transfer_id": transfer.id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "from_id": vendor_inv.id,
                    "to_id": warehouse_id,
                }
                for item in items
            ]
            await self.uow.transactions.add_many(transactions_data)

            await self.uow.commit()
            return TransferResult(
                transfer_id=transfer.id,
                status=transfer.status,
                created_at=datetime.now(UTC),
            )

    # --- 3.4. Цикл Розлива на Заводе (Магия HOD) ---

    async def execute_factory_refill(
        self,
        warehouse_id: uuid.UUID,
        factory_id: uuid.UUID,
        water_id: uuid.UUID,
        bottle_id: uuid.UUID,
        quantity: int,
        created_by_id: uuid.UUID,
    ) -> tuple[TransferResult, TransferResult]:

        if quantity <= 0:
            raise InvalidQuantityError(
                product_id=bottle_id,
                quantity=quantity,
                message="Количество на розлив должно быть больше 0",
            )

        async with self.uow:
            if warehouse_id == factory_id:
                raise RouteLoopError(
                    inventory_id=warehouse_id,
                    message="Склад и завод не могут совпадать",
                )

            warehouse = await self.uow.inventories.get(warehouse_id)
            if not warehouse:
                raise InventoryNotFoundError(inventory_id=warehouse_id)

            current_bottles = await self.uow.transactions.get_balance(
                warehouse_id, bottle_id
            )
            if current_bottles < quantity:
                raise InsufficientStockError(
                    shortages={bottle_id: quantity - current_bottles},
                    message="На складе не хватает пустых бутылей для розлива",
                )

            # Накладная №1: Списание пустой тары на завод
            dispatch_transfer = await self.uow.transfers.add(
                {
                    "from_id": warehouse_id,
                    "to_id": factory_id,
                    "created_by_id": created_by_id,
                    "type": TransferType.PRODUCTION,
                    "status": TransferStatus.COMPLETED,
                }
            )
            await self.uow.transactions.add(
                {
                    "transfer_id": dispatch_transfer.id,
                    "product_id": bottle_id,
                    "quantity": quantity,
                    "from_id": warehouse_id,
                    "to_id": factory_id,
                }
            )

            # Накладная №2: Приемка готовой продукции (Вода + Бутылка)
            receipt_transfer = await self.uow.transfers.add(
                {
                    "from_id": factory_id,
                    "to_id": warehouse_id,
                    "created_by_id": created_by_id,
                    "type": TransferType.PRODUCTION,
                    "status": TransferStatus.COMPLETED,
                }
            )

            await self.uow.transactions.add_many(
                [
                    {
                        "transfer_id": receipt_transfer.id,
                        "product_id": bottle_id,
                        "quantity": quantity,
                        "from_id": factory_id,
                        "to_id": warehouse_id,
                    },
                    {
                        "transfer_id": receipt_transfer.id,
                        "product_id": water_id,
                        "quantity": quantity,
                        "from_id": factory_id,
                        "to_id": warehouse_id,
                    },
                ]
            )

            await self.uow.commit()

            return (
                TransferResult(
                    transfer_id=dispatch_transfer.id,
                    status=TransferStatus.COMPLETED,
                    created_at=datetime.now(UTC),
                ),
                TransferResult(
                    transfer_id=receipt_transfer.id,
                    status=TransferStatus.COMPLETED,
                    created_at=datetime.now(UTC),
                ),
            )

    # --- 3.5. Корректировка остатков ---

    async def execute_inventory_adjustment(
        self,
        warehouse_id: uuid.UUID,
        created_by_id: uuid.UUID,
        items: list[AdjustmentItem],
    ) -> list[TransferResult]:

        if not items:
            raise EmptyTransferError(
                transfer_id="adjustment", message="Список корректировок пуст"
            )

        async with self.uow:
            warehouse = await self.uow.inventories.get(warehouse_id)
            if not warehouse:
                raise InventoryNotFoundError(inventory_id=warehouse_id)

            shortages = [i for i in items if i.delta < 0]
            surpluses = [i for i in items if i.delta > 0]
            results = []

            # 1. Обработка недостач
            if shortages:
                loss_inv = (
                    await self.uow.inventories.get_system_virtual_inventory(
                        InventoryType.VIRTUAL_LOSS
                    )
                )
                if not loss_inv:
                    raise VirtualInventoryConfigurationError(
                        v_type=InventoryType.VIRTUAL_LOSS
                    )

                product_ids = [s.product_id for s in shortages]
                balances = (
                    await self.uow.transactions.get_balances_for_products(
                        warehouse_id, product_ids
                    )
                )

                deficit = {}
                for s in shortages:
                    if balances.get(s.product_id, 0) < abs(s.delta):
                        deficit[s.product_id] = abs(s.delta) - balances.get(
                            s.product_id, 0
                        )
                if deficit:
                    raise InsufficientStockError(
                        shortages=deficit,
                        message="Невозможно списать товар",
                    )

                transfer = await self.uow.transfers.add(
                    {
                        "from_id": warehouse_id,
                        "to_id": loss_inv.id,
                        "created_by_id": created_by_id,
                        "type": TransferType.LOSS_WRITE_OFF,
                        "status": TransferStatus.COMPLETED,
                    }
                )
                await self.uow.transactions.add_many(
                    [
                        {
                            "transfer_id": transfer.id,
                            "product_id": s.product_id,
                            "quantity": abs(s.delta),
                            "from_id": warehouse_id,
                            "to_id": loss_inv.id,
                        }
                        for s in shortages
                    ]
                )
                results.append(
                    TransferResult(
                        transfer_id=transfer.id,
                        status=transfer.status,
                        created_at=datetime.now(UTC),
                    )
                )

            # 2. Обработка излишков
            if surpluses:
                vendor_inv = (
                    await self.uow.inventories.get_system_virtual_inventory(
                        InventoryType.VIRTUAL_VENDOR
                    )
                )
                if not vendor_inv:
                    raise VirtualInventoryConfigurationError(
                        v_type=InventoryType.VIRTUAL_VENDOR
                    )

                transfer = await self.uow.transfers.add(
                    {
                        "from_id": vendor_inv.id,
                        "to_id": warehouse_id,
                        "created_by_id": created_by_id,
                        "type": TransferType.INVENTORY_FINDING,
                        "status": TransferStatus.COMPLETED,
                    }
                )
                await self.uow.transactions.add_many(
                    [
                        {
                            "transfer_id": transfer.id,
                            "product_id": s.product_id,
                            "quantity": s.delta,
                            "from_id": vendor_inv.id,
                            "to_id": warehouse_id,
                        }
                        for s in surpluses
                    ]
                )
                results.append(
                    TransferResult(
                        transfer_id=transfer.id,
                        status=transfer.status,
                        created_at=datetime.now(UTC),
                    )
                )

            await self.uow.commit()
            return results
