# src/modules/orders/services.py
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import cast

from src.common.service import BaseService
from src.infrastructure.database.models import Order
from src.modules.catalog.services import CatalogService
from src.modules.finances.enums import TransactionStatus
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.orders.enums import OrderStatus, PaymentMethod, SaleType
from src.modules.inventory.exceptions import InsufficientStockError
from src.modules.orders.exceptions import (
    CannotRemoveLastItemError,
    ClientInventoryNotFoundError,
    CourierAssignmentError,
    DeliveryQuantityExceededError,
    EmptyCartError,
    InsufficientTaraError,
    InvalidPickupOperationError,
    OrderAccessDeniedError,
    OrderNotFoundError,
    ProductsUnavailableError,
)
from src.modules.orders.repositories import OrderRepository
from src.modules.orders.schemas import (
    OrderCreate,
    OrderItemActual,
    TaraCheckRequest,
    WarehouseSaleCreate,
)
from src.modules.orders.uow import BaseOrderUnitOfWork
from src.core.constants import WALKIN_USER_ID


class BaseOrderService(BaseService[Order, OrderCreate, BaseOrderUnitOfWork]):
    def __init__(
        self, uow: BaseOrderUnitOfWork, catalog_service: CatalogService
    ):
        super().__init__(uow=uow)
        self.catalog_service = catalog_service

    @property
    def _repo(self) -> OrderRepository:
        return self.uow.orders

    # --- БИЗНЕС-ЛОГИКА ---

    async def create_order(
        self, client_id: uuid.UUID, dto: OrderCreate
    ) -> Order:
        """
        Процесс Checkout'а.
        Формирует корзину заказа (OrderItem) и высчитывает (total_amount),
        замораживая цены из Каталога на момент покупки.
        """
        if not dto.items:
            raise EmptyCartError()

        # 1. Извлекаем уникальные ID товаров и идем за ценами в соседний домен
        product_ids = [item.product_id for item in dto.items]
        products = await self.catalog_service.get_by_ids(product_ids)
        price_map = {p.id: p.price for p in products}

        # Валидация: все ли товары найдены
        missing_ids = [pid for pid in product_ids if pid not in price_map]
        if missing_ids:
            raise ProductsUnavailableError(missing_product_ids=missing_ids)

        # 1.1 Валидация обмена тары (Task 3)
        # Ищем товары, требующие возврата тары (returnable_item_id)
        exchange_items = [
            (p, next(i for i in dto.items if i.product_id == p.id))
            for p in products
            if p.returnable_item_id is not None
        ]

        # 2. Высчитываем стоимость строк и итоговую сумму
        total_amount = 0
        order_items_data = []
        for item in dto.items:
            current_price = price_map[item.product_id]
            total_amount += current_price * item.quantity
            order_items_data.append(
                {
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "unit_price": current_price,  # Snapshot Pattern
                }
            )

        # 3. Всё — оприходование тары И создание заказа — в одной транзакции
        async with self.uow:
            capitalization_applied = False

            if exchange_items:
                # Получаем баланс пустой тары клиента (с блокировкой от Race Condition)
                inventory = (
                    await self.uow.inventories.get_inventory_with_balances(
                        dto.client_inventory_id,
                        with_for_update=True,
                    )
                )
                if not inventory:
                    raise ClientInventoryNotFoundError(
                        inventory_id=dto.client_inventory_id
                    )

                balances = {
                    b.product_id: b.quantity for b in inventory.balances
                }

                # Тара, заказанная в этой же корзине (например, новый клиент
                # заказывает воду + тару одновременно)
                ordering_tare_now = {
                    item.product_id: item.quantity for item in dto.items
                }

                shortages = []
                for product, item in exchange_items:
                    required_tare_id = product.returnable_item_id
                    available_in_inventory = balances.get(required_tare_id, 0)
                    ordering_now = ordering_tare_now.get(required_tare_id, 0)
                    effective_available = available_in_inventory + ordering_now
                    if effective_available < item.quantity:
                        shortages.append(
                            {
                                "product_id": str(product.id),
                                "product_name": product.name,
                                "returnable_item_id": str(required_tare_id),
                                "required": item.quantity,
                                "available": effective_available,
                                "deficit": item.quantity - effective_available,
                            }
                        )

                if shortages and not dto.capitalize_missing_tara:
                    raise InsufficientTaraError(shortages=shortages)

                # Автоматическое оприходование дефицита тары
                if shortages and dto.capitalize_missing_tara:
                    vendor_inv = (
                        await self.uow.inventories.get_vendor_inventory()
                    )

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

                    for shortage in shortages:
                        await self.uow.transfer_items.add(
                            {
                                "transfer_id": transfer.id,
                                "product_id": uuid.UUID(
                                    shortage["returnable_item_id"]
                                ),
                                "quantity": shortage["deficit"],
                            }
                        )
                        await self.uow.transactions.add(
                            {
                                "product_id": uuid.UUID(
                                    shortage["returnable_item_id"]
                                ),
                                "transfer_id": transfer.id,
                                "from_id": vendor_inv.id,
                                "to_id": inventory.id,
                                "quantity": shortage["deficit"],
                            }
                        )

                    capitalization_applied = True

            # 4. Сохраняем шапку Заказа с подсчитанной суммой
            new_order = await self.uow.orders.add(
                {
                    "client_id": client_id,
                    "client_inventory_id": dto.client_inventory_id,
                    "payment_method": dto.payment_method,
                    "status": OrderStatus.NEW,
                    "total_amount": total_amount,
                    "capitalization_applied": capitalization_applied,
                }
            )

            # 5. Привязываем строки корзины к новому заказу
            for item_data in order_items_data:
                item_data["order_id"] = new_order.id

            # 6. Сохраняем строки (Bulk Insert)
            await self.uow.order_items.add_many(order_items_data)

            # 7. Единый коммит: оприходование + заказ атомарно
            await self.uow.commit()

            # 8. Перечитываем с eager-loaded relationships для корректной сериализации
            return await self.uow.orders.get_with_details(new_order.id)

    async def create_warehouse_sale(
        self,
        dto: WarehouseSaleCreate,
        client_id: uuid.UUID | None,
        created_by_id: uuid.UUID,
    ) -> Order:
        """
        Создание заказа на самовывоз со склада.
        Если client_id не передан — используется WALKIN_USER_ID.
        """
        effective_client_id = client_id or WALKIN_USER_ID

        if not dto.items:
            raise EmptyCartError()

        product_ids = [item.product_id for item in dto.items]
        products = await self.catalog_service.get_by_ids(product_ids)
        price_map = {p.id: p.price for p in products}

        missing_ids = [pid for pid in product_ids if pid not in price_map]
        if missing_ids:
            raise ProductsUnavailableError(missing_product_ids=missing_ids)

        exchange_items = [
            (p, next(i for i in dto.items if i.product_id == p.id))
            for p in products
            if p.returnable_item_id is not None
        ]

        total_amount = 0
        order_items_data = []
        for item in dto.items:
            current_price = price_map[item.product_id]
            total_amount += current_price * item.quantity
            order_items_data.append(
                {
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "unit_price": current_price,
                }
            )

        async with self.uow:
            warehouse = await self.uow.inventories.get_inventory_with_balances(
                dto.warehouse_id, inv_type=InventoryType.WAREHOUSE
            )
            if not warehouse:
                raise ValueError(f"Склад {dto.warehouse_id} не найден")

            client_inventory = await self.uow.inventories.get_client_inventory(
                effective_client_id
            )
            if not client_inventory:
                raise ClientInventoryNotFoundError(
                    inventory_id=effective_client_id
                )

            capitalization_applied = False

            if exchange_items:
                inventory = (
                    await self.uow.inventories.get_inventory_with_balances(
                        client_inventory.id, with_for_update=True
                    )
                )
                if not inventory:
                    raise ClientInventoryNotFoundError(
                        inventory_id=client_inventory.id
                    )

                balances = {
                    b.product_id: b.quantity for b in inventory.balances
                }

                ordering_tare_now = {
                    item.product_id: item.quantity for item in dto.items
                }

                shortages = []
                for product, item in exchange_items:
                    required_tare_id = product.returnable_item_id
                    available_in_inventory = balances.get(required_tare_id, 0)
                    ordering_now = ordering_tare_now.get(required_tare_id, 0)
                    effective_available = available_in_inventory + ordering_now
                    if effective_available < item.quantity:
                        shortages.append(
                            {
                                "product_id": str(product.id),
                                "product_name": product.name,
                                "returnable_item_id": str(required_tare_id),
                                "required": item.quantity,
                                "available": effective_available,
                                "deficit": item.quantity - effective_available,
                            }
                        )

                if shortages and not dto.capitalize_missing_tara:
                    raise InsufficientTaraError(shortages=shortages)

                if shortages and dto.capitalize_missing_tara:
                    vendor_inv = (
                        await self.uow.inventories.get_vendor_inventory()
                    )
                    transfer = await self.uow.transfers.add(
                        {
                            "from_id": vendor_inv.id,
                            "to_id": client_inventory.id,
                            "type": TransferType.INITIAL_BALANCE,
                            "status": TransferStatus.COMPLETED,
                            "created_by_id": created_by_id,
                            "accepted_by_id": created_by_id,
                        }
                    )
                    for shortage in shortages:
                        await self.uow.transfer_items.add(
                            {
                                "transfer_id": transfer.id,
                                "product_id": uuid.UUID(
                                    shortage["returnable_item_id"]
                                ),
                                "quantity": shortage["deficit"],
                            }
                        )
                        await self.uow.transactions.add(
                            {
                                "product_id": uuid.UUID(
                                    shortage["returnable_item_id"]
                                ),
                                "transfer_id": transfer.id,
                                "from_id": vendor_inv.id,
                                "to_id": client_inventory.id,
                                "quantity": shortage["deficit"],
                            }
                        )
                    capitalization_applied = True

            new_order = await self.uow.orders.add(
                {
                    "client_id": effective_client_id,
                    "client_inventory_id": client_inventory.id,
                    "payment_method": PaymentMethod.CASH,
                    "status": OrderStatus.NEW,
                    "total_amount": total_amount,
                    "capitalization_applied": capitalization_applied,
                    "sale_type": SaleType.WAREHOUSE_PICKUP,
                    "warehouse_id": dto.warehouse_id,
                }
            )

            for item_data in order_items_data:
                item_data["order_id"] = new_order.id
            await self.uow.order_items.add_many(order_items_data)

            await self.uow.commit()
            return await self.uow.orders.get_with_details(new_order.id)

    async def complete_pickup(
        self,
        order_id: uuid.UUID,
        completed_by_id: uuid.UUID,
    ) -> Order:
        """
        Подтверждение выдачи товара со склада.
        NEW → PICKUP_COMPLETED с созданием складских и финансовых проводок.
        """
        async with self.uow:
            order = await self.uow.orders.get_with_details(
                order_id, with_for_update=True
            )
            if not order:
                raise OrderNotFoundError(order_id=order_id)

            if order.sale_type != SaleType.WAREHOUSE_PICKUP:
                raise InvalidPickupOperationError(
                    order_id=order_id,
                    reason="Заказ не является самовывозом",
                )

            if order.status != OrderStatus.NEW:
                raise InvalidPickupOperationError(
                    order_id=order_id,
                    reason=f"Ожидался статус NEW, текущий: {order.status}",
                )

            await self.uow.orders.update_status(
                order_id, OrderStatus.PICKUP_COMPLETED
            )

            await self._handle_warehouse_pickup(order, completed_by_id)

            await self.uow.commit()
            return await self.uow.orders.get_with_details(order_id)

    async def get_order_with_details(
        self, order_id: uuid.UUID, requesting_user_id: uuid.UUID | None = None
    ) -> Order:
        """
        Глубокая загрузка заказа.
        Если передан requesting_user_id (от клиента/курьера).
        Если не передан - считаем, что это запрос от Админа/CRM.
        """
        async with self.uow:
            order = await self.uow.orders.get_with_details(order_id)
            if not order:
                raise OrderNotFoundError(order_id=order_id)

            # IDOR Проверка
            if requesting_user_id and requesting_user_id not in (
                order.client_id,
                order.courier_id,
            ):
                raise OrderAccessDeniedError(
                    user_id=requesting_user_id, order_id=order_id
                )

            return order

    async def add_product_to_order(
        self, order_id: uuid.UUID, product_id: uuid.UUID, quantity: int
    ) -> Order:
        """
        Добавляет товар в существующий заказ или увеличивает количество,
        если товар уже в корзине. Пересчитывает итоговую сумму.
        """
        if quantity <= 0:
            raise ValueError("Количество должно быть строго больше нуля")

        # 1. Забираем актуальную цену из Каталога
        products = await self.catalog_service.get_by_ids([product_id])
        if not products:
            raise ProductsUnavailableError(missing_product_ids=[product_id])
        current_price = products[0].price

        async with self.uow:
            # 2. Блокируем заказ от параллельных изменений сумм
            order = await self.uow.orders.get_with_details(
                order_id, with_for_update=True
            )
            if not order:
                raise OrderNotFoundError(order_id=order_id)

            # Бизнес-проверка: менять можно только новые заказы
            if order.status != OrderStatus.NEW:
                raise ValueError(
                    "Нельзя менять состав заказа в текущем статусе"
                )

            # 3. Ищем, есть ли уже такой товар в заказе
            existing_item = (
                await self.uow.order_items.get_by_order_and_product(
                    order_id=order_id, product_id=product_id
                )
            )

            if existing_item:
                new_quantity = existing_item.quantity + quantity
                await self.uow.order_items.update_quantity(
                    order_item_id=existing_item.id, new_quantity=new_quantity
                )
            else:
                await self.uow.order_items.add(
                    {
                        "order_id": order_id,
                        "product_id": product_id,
                        "quantity": quantity,
                        "unit_price": current_price,
                    }
                )

            amount_to_add = current_price * quantity
            new_total = order.total_amount + amount_to_add
            updated_order = await self.uow.orders.update(
                order_id, {"total_amount": new_total}
            )

            await self.uow.commit()
            return updated_order

    async def remove_product_from_order(
        self, order_id: uuid.UUID, product_id: uuid.UUID
    ) -> Order:
        """
        Полностью удаляет позицию товара из заказа и пересчитывает сумму.
        """
        async with self.uow:
            # 1. Блокируем заказ
            order = await self.uow.orders.get_with_details(
                order_id, with_for_update=True
            )
            if not order:
                raise OrderNotFoundError(order_id=order_id)

            if order.status != OrderStatus.NEW:
                raise ValueError(
                    "Нельзя менять состав заказа в текущем статусе"
                )

            existing_item = (
                await self.uow.order_items.get_by_order_and_product(
                    order_id=order_id, product_id=product_id
                )
            )

            # Если товара и так нет, просто отдаем текущий заказ
            if not existing_item:
                return order

            # Защита: запрет удаления последнего товара (пустой заказ недопустим)
            if len(order.items) <= 1:
                raise CannotRemoveLastItemError()

            # 3. Высчитываем сумму для вычета до удаления
            amount_to_subtract = (
                existing_item.unit_price * existing_item.quantity
            )

            # 4. Удаляем строку
            await self.uow.order_items.delete_by_order_and_product(
                order_id=order_id, product_id=product_id
            )

            new_total = max(0, order.total_amount - amount_to_subtract)

            updated_order = await self.uow.orders.update(
                order_id, {"total_amount": new_total}
            )

            await self.uow.commit()
            return updated_order

    async def assign_courier(
        self, order_id: uuid.UUID, courier_id: uuid.UUID
    ) -> Order:
        """
        Диспетчеризация: Логист назначает заказ конкретному курьеру.
        """
        async with self.uow:
            order = await self.uow.orders.get_with_details(
                order_id, with_for_update=True
            )
            if not order:
                raise OrderNotFoundError(order_id=order_id)

            if order.sale_type == SaleType.WAREHOUSE_PICKUP:
                raise InvalidPickupOperationError(
                    order_id=order_id,
                    reason="Заказ самовывоза не может быть назначен курьеру",
                )

            if order.status in (OrderStatus.DELIVERED, OrderStatus.CANCELLED):
                raise CourierAssignmentError(
                    order_id=order_id,
                    courier_id=courier_id,
                    reason="Заказ уже закрыт или отменен",
                )

            updated_order = await self.uow.orders.update(
                order_id,
                {
                    "courier_id": courier_id,
                    "status": OrderStatus.ASSIGNED,  # Меняем статус
                },
            )
            await self.uow.commit()

            if not updated_order:
                raise OrderNotFoundError(
                    order_id=order_id, message="Ошибка при обновлении заказа"
                )

            return updated_order

    async def update_status(
        self,
        order_id: uuid.UUID,
        new_status: OrderStatus,
        actual_items: list[OrderItemActual] | None = None,
    ) -> Order:
        async with self.uow:
            # Блокируем заказ для обновления статуса и возможных движений товаров
            order = await self.uow.orders.get_with_details(
                order_id, with_for_update=True
            )
            if not order:
                raise OrderNotFoundError(order_id=order_id)

            old_status = order.status

            # Guard: pickup orders cannot use delivery statuses
            if order.sale_type == SaleType.WAREHOUSE_PICKUP and new_status in (
                OrderStatus.ASSIGNED,
                OrderStatus.IN_TRANSIT,
                OrderStatus.ARRIVED,
                OrderStatus.DELIVERED,
            ):
                raise InvalidPickupOperationError(
                    order_id=order_id,
                    reason=f"Заказ самовывоза не может перейти в статус {new_status}. "
                    "Используйте complete-pickup.",
                )

            updated_order = await self.uow.orders.update_status(
                order_id, new_status
            )
            if not updated_order:
                raise OrderNotFoundError(order_id=order_id)

            # Task 2: Автоматизация логистики при доставке
            if (
                old_status != OrderStatus.DELIVERED
                and new_status == OrderStatus.DELIVERED
            ):
                await self._handle_order_fulfillment(
                    cast(Order, updated_order), actual_items
                )

            await self.uow.commit()
            return updated_order

    async def _handle_order_fulfillment(
        self,
        order: Order,
        actual_items_dto: list[OrderItemActual] | None = None,
    ) -> None:
        """
        Автоматическое создание и проведение StockTransfer при доставке.
        1. [NEW] Корректировка заказа (если переданы actual_items)
        2. Списание полной воды: Курьер -> Клиент
        3. Забор пустой тары: Клиент -> Курьер
        """
        if not order.courier_id:
            raise ValueError("Заказ не может быть доставлен без курьера")

        # 1. Корректировка заказа (Partial Delivery)
        if actual_items_dto:
            actual_map = {
                item.product_id: item.quantity for item in actual_items_dto
            }
            new_total = 0

            # Обновляем строки заказа (с защитой от превышения)
            for item in order.items:
                if item.product_id in actual_map:
                    original_quantity = item.quantity
                    requested_quantity = actual_map[item.product_id]

                    if requested_quantity < 0:
                        raise DeliveryQuantityExceededError(
                            product_id=item.product_id,
                            ordered=original_quantity,
                            actual=requested_quantity,
                        )
                    if requested_quantity > original_quantity:
                        raise DeliveryQuantityExceededError(
                            product_id=item.product_id,
                            ordered=original_quantity,
                            actual=requested_quantity,
                        )

                    item.quantity = requested_quantity
                    await self.uow.order_items.update_quantity(
                        item.id, item.quantity
                    )

                # Только фактически доставленные позиции входят в сумму
                new_total += item.unit_price * item.quantity

            # Обновляем итоговую сумму заказа
            order.total_amount = new_total
            await self.uow.orders.update(order.id, {"total_amount": new_total})

        # Получаем активный инвентарь (машину) курьера (поиск по user_id)
        courier_inv_row = await self.uow.inventories.get_courier_inventory(
            order.courier_id
        )
        if not courier_inv_row:
            raise ValueError("У курьера нет активного инвентаря (машины)")

        # Повторно получаем с блокировкой и актуальными остатками
        courier_inventory = (
            await self.uow.inventories.get_inventory_with_balances(
                courier_inv_row.id, with_for_update=True
            )
        )
        if not courier_inventory:
            raise ValueError("У курьера нет активного инвентаря (машины)")

        # Проверяем наличие товаров у курьера перед доставкой
        courier_balances = {
            b.product_id: b.quantity for b in courier_inventory.balances
        }
        stock_shortages: dict[uuid.UUID, int] = {}
        for item in order.items:
            available = courier_balances.get(item.product_id, 0)
            if available < item.quantity:
                stock_shortages[item.product_id] = item.quantity - available
        if stock_shortages:
            raise InsufficientStockError(shortages=stock_shortages)

        # 1. Создаем накладную на доставку (Full Water OUT)
        delivery_transfer = await self.uow.transfers.add(
            {
                "from_id": courier_inventory.id,
                "to_id": order.client_inventory_id,
                "type": TransferType.CLIENT_DELIVERY,
                "status": TransferStatus.COMPLETED,
                "created_by_id": order.courier_id,
                "accepted_by_id": order.client_id,
                "order_id": order.id,
            }
        )

        # 2. Создаем накладную на возврат тары (Empty Water IN)
        # Агрегируем тару по product_id (несколько позиций могут требовать одну тару)
        # Пропускаем позиции с quantity=0 (товар не был доставлен)
        returnable_map: dict[uuid.UUID, int] = {}
        for item in order.items:
            if item.product.returnable_item_id and item.quantity > 0:
                tare_id = item.product.returnable_item_id
                returnable_map[tare_id] = (
                    returnable_map.get(tare_id, 0) + item.quantity
                )
        returnable_items = [
            {"product_id": pid, "quantity": qty}
            for pid, qty in returnable_map.items()
        ]

        return_transfer = None
        if returnable_items:
            return_transfer = await self.uow.transfers.add(
                {
                    "from_id": order.client_inventory_id,
                    "to_id": courier_inventory.id,
                    "type": TransferType.CLIENT_RETURN,
                    "status": TransferStatus.COMPLETED,
                    "created_by_id": order.courier_id,
                    "accepted_by_id": order.courier_id,
                    "order_id": order.id,
                }
            )

        # 3. Строки накладных и проводки в леджере
        # а) Доставка: Курьер → Клиент (пропускаем позиции с quantity=0)
        for item in order.items:
            if item.quantity == 0:
                continue
            await self.uow.transfer_items.add(
                {
                    "transfer_id": delivery_transfer.id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                }
            )
            await self.uow.transactions.add(
                {
                    "product_id": item.product_id,
                    "transfer_id": delivery_transfer.id,
                    "from_id": courier_inventory.id,
                    "to_id": order.client_inventory_id,
                    "quantity": item.quantity,
                }
            )

        # б) Возврат тары: Клиент → Курьер
        if return_transfer:
            for item_data in returnable_items:
                await self.uow.transfer_items.add(
                    {
                        "transfer_id": return_transfer.id,
                        "product_id": item_data["product_id"],
                        "quantity": item_data["quantity"],
                    }
                )
                await self.uow.transactions.add(
                    {
                        "product_id": item_data["product_id"],
                        "transfer_id": return_transfer.id,
                        "from_id": order.client_inventory_id,
                        "to_id": courier_inventory.id,
                        "quantity": item_data["quantity"],
                    }
                )

        # 4. Финансовое закрытие заказа
        await self._process_financial_settlement(order)

    async def _handle_warehouse_pickup(
        self,
        order: Order,
        completed_by_id: uuid.UUID,
    ) -> None:
        """
        Складские перемещения при самовывозе:
        1. Проверка остатков на складе
        2. WAREHOUSE_SALE: Warehouse → Client (товар)
        3. WAREHOUSE_TARA_RETURN: Client → Warehouse (тара)
        4. Финансовая проводка
        """
        if not order.warehouse_id:
            raise ValueError("Заказ самовывоза без warehouse_id")

        warehouse = await self.uow.inventories.get_inventory_with_balances(
            order.warehouse_id,
            inv_type=InventoryType.WAREHOUSE,
            with_for_update=True,
        )
        if not warehouse:
            raise ValueError(f"Склад {order.warehouse_id} не найден")

        # Проверка остатков на складе
        warehouse_balances = {
            b.product_id: b.quantity for b in warehouse.balances
        }
        stock_shortages: dict[uuid.UUID, int] = {}
        for item in order.items:
            available = warehouse_balances.get(item.product_id, 0)
            if available < item.quantity:
                stock_shortages[item.product_id] = item.quantity - available
        if stock_shortages:
            raise InsufficientStockError(shortages=stock_shortages)

        # 1. WAREHOUSE_SALE: Warehouse → Client
        sale_transfer = await self.uow.transfers.add(
            {
                "from_id": warehouse.id,
                "to_id": order.client_inventory_id,
                "type": TransferType.WAREHOUSE_SALE,
                "status": TransferStatus.COMPLETED,
                "created_by_id": completed_by_id,
                "accepted_by_id": order.client_id,
                "order_id": order.id,
            }
        )

        # 2. WAREHOUSE_TARA_RETURN: Client → Warehouse
        returnable_map: dict[uuid.UUID, int] = {}
        for item in order.items:
            if item.product.returnable_item_id and item.quantity > 0:
                tare_id = item.product.returnable_item_id
                returnable_map[tare_id] = (
                    returnable_map.get(tare_id, 0) + item.quantity
                )
        returnable_items = [
            {"product_id": pid, "quantity": qty}
            for pid, qty in returnable_map.items()
        ]

        tara_transfer = None
        if returnable_items:
            tara_transfer = await self.uow.transfers.add(
                {
                    "from_id": order.client_inventory_id,
                    "to_id": warehouse.id,
                    "type": TransferType.WAREHOUSE_TARA_RETURN,
                    "status": TransferStatus.COMPLETED,
                    "created_by_id": completed_by_id,
                    "accepted_by_id": completed_by_id,
                    "order_id": order.id,
                }
            )

        # 3. Строки накладных и проводки в леджере
        for item in order.items:
            if item.quantity == 0:
                continue
            await self.uow.transfer_items.add(
                {
                    "transfer_id": sale_transfer.id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                }
            )
            await self.uow.transactions.add(
                {
                    "product_id": item.product_id,
                    "transfer_id": sale_transfer.id,
                    "from_id": warehouse.id,
                    "to_id": order.client_inventory_id,
                    "quantity": item.quantity,
                }
            )

        if tara_transfer:
            for item_data in returnable_items:
                await self.uow.transfer_items.add(
                    {
                        "transfer_id": tara_transfer.id,
                        "product_id": item_data["product_id"],
                        "quantity": item_data["quantity"],
                    }
                )
                await self.uow.transactions.add(
                    {
                        "product_id": item_data["product_id"],
                        "transfer_id": tara_transfer.id,
                        "from_id": order.client_inventory_id,
                        "to_id": warehouse.id,
                        "quantity": item_data["quantity"],
                    }
                )

        # 4. Cleanup: списание товара с Walk-in inventory
        # Анонимный покупатель забрал товар и ушёл — обнуляем его inventory
        if order.client_id == WALKIN_USER_ID:
            loss_inv = await self.uow.inventories.get_loss_inventory()
            cleanup_transfer = await self.uow.transfers.add(
                {
                    "from_id": order.client_inventory_id,
                    "to_id": loss_inv.id,
                    "type": TransferType.LOSS_WRITE_OFF,
                    "status": TransferStatus.COMPLETED,
                    "created_by_id": completed_by_id,
                    "accepted_by_id": completed_by_id,
                    "order_id": order.id,
                }
            )
            for item in order.items:
                if item.quantity == 0:
                    continue
                await self.uow.transfer_items.add(
                    {
                        "transfer_id": cleanup_transfer.id,
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                    }
                )
                await self.uow.transactions.add(
                    {
                        "product_id": item.product_id,
                        "transfer_id": cleanup_transfer.id,
                        "from_id": order.client_inventory_id,
                        "to_id": loss_inv.id,
                        "quantity": item.quantity,
                    }
                )

        # 5. Финансовое закрытие
        await self._process_pickup_settlement(order)

    async def _process_financial_settlement(self, order: Order) -> None:
        """
        Финансовое закрытие заказа при доставке.
        Создает финансовые транзакции в зависимости от способа оплаты:
        - Начисляет долг клиенту (Revenue → Client)
        - CASH: перебрасывает долг на курьера (Client → Courier)
        - CARD: создает pending-транзакцию на эквайринг (Client → Card)

        ВАЖНО: Балансы accounts.balance обновляются ТРИГГЕРОМ БД
        (update_account_balances), а не приложением. Приложение
        только вставляет записи в таблицу transactions.
        """
        client_account = await self.uow.accounts.get_client_account(
            order.client_id
        )
        if not client_account:
            raise ValueError(
                f"Финансовый счет клиента {order.client_id} не найден. "
                "Создайте счет перед обработкой заказа."
            )
        revenue_account = await self.uow.accounts.get_system_revenue_account()

        # Долг клиенту (balance обновит триггер при INSERT)
        financial_txns: list[dict] = [
            {
                "from_id": revenue_account.id,
                "to_id": client_account.id,
                "amount": order.total_amount,
                "order_id": order.id,
                "status": TransactionStatus.COMPLETED,
                "reason": "Задолженность за заказ",
            }
        ]

        if order.payment_method == PaymentMethod.CASH and order.courier_id:
            courier_account = await self.uow.accounts.get_courier_account(
                order.courier_id
            )
            if courier_account:
                financial_txns.append(
                    {
                        "from_id": client_account.id,
                        "to_id": courier_account.id,
                        "amount": order.total_amount,
                        "order_id": order.id,
                        "status": TransactionStatus.COMPLETED,
                        "reason": "Оплата наличными курьеру",
                    }
                )

        elif order.payment_method == PaymentMethod.CARD:
            card_account = await self.uow.accounts.get_system_card_account()
            financial_txns.append(
                {
                    "from_id": client_account.id,
                    "to_id": card_account.id,
                    "amount": order.total_amount,
                    "order_id": order.id,
                    "status": TransactionStatus.PENDING,
                    "reason": "Перевод на карту",
                }
            )

        await self.uow.financial_transactions.add_many(financial_txns)

    async def _process_pickup_settlement(self, order: Order) -> None:
        """
        Финансовое закрытие самовывоза:
        1. Revenue → Client (долг)
        2. Client → Cash (оплата наличными на складе)
        Обе транзакции COMPLETED — деньги сразу в кассе.
        """
        client_account = await self.uow.accounts.get_client_account(
            order.client_id
        )
        if not client_account:
            raise ValueError(
                f"Финансовый счет клиента {order.client_id} не найден"
            )
        revenue_account = await self.uow.accounts.get_system_revenue_account()
        cash_account = await self.uow.accounts.get_system_cash_account()

        await self.uow.financial_transactions.add_many(
            [
                {
                    "from_id": revenue_account.id,
                    "to_id": client_account.id,
                    "amount": order.total_amount,
                    "order_id": order.id,
                    "status": TransactionStatus.COMPLETED,
                    "reason": "Задолженность за заказ (самовывоз)",
                },
                {
                    "from_id": client_account.id,
                    "to_id": cash_account.id,
                    "amount": order.total_amount,
                    "order_id": order.id,
                    "status": TransactionStatus.COMPLETED,
                    "reason": "Оплата наличными на складе",
                },
            ]
        )

    async def check_tara_availability(self, dto: TaraCheckRequest) -> dict:
        """
        Предварительная проверка тары перед оформлением заказа.
        Возвращает can_order и список нехваток.
        """
        product_ids = [item.product_id for item in dto.items]
        products = await self.catalog_service.get_by_ids(product_ids)

        exchange_items = [
            (p, next(i for i in dto.items if i.product_id == p.id))
            for p in products
            if p.returnable_item_id is not None
        ]

        if not exchange_items:
            return {"can_order": True, "shortages": []}

        async with self.uow:
            inventory = await self.uow.inventories.get_inventory_with_balances(
                dto.client_inventory_id
            )
            if not inventory:
                raise ClientInventoryNotFoundError(
                    inventory_id=dto.client_inventory_id
                )

            balances = {b.product_id: b.quantity for b in inventory.balances}

            shortages = []
            for product, item in exchange_items:
                required_tare_id = product.returnable_item_id
                available_tare = balances.get(required_tare_id, 0)
                if available_tare < item.quantity:
                    shortages.append(
                        {
                            "product_id": product.id,
                            "product_name": product.name,
                            "returnable_item_id": required_tare_id,
                            "required": item.quantity,
                            "available": available_tare,
                            "deficit": item.quantity - available_tare,
                        }
                    )

            return {"can_order": len(shortages) == 0, "shortages": shortages}

    # --- МЕТОДЫ ПОИСКА И СПИСКОВ ---

    async def get_client_history(
        self, client_id: uuid.UUID, skip: int = 0, limit: int = 20
    ) -> Sequence[Order]:
        """История заказов для мобильного приложения клиента."""
        async with self.uow:
            return await self.uow.orders.get_client_orders(
                client_id=client_id, skip=skip, limit=limit
            )

    async def get_courier_tasks(
        self, courier_id: uuid.UUID
    ) -> Sequence[Order]:
        """Активные заказы на сегодня для терминала курьера."""
        async with self.uow:
            return await self.uow.orders.get_active_courier_orders(
                courier_id=courier_id
            )

    async def search_orders(
        self,
        skip: int = 0,
        limit: int = 100,
        statuses: list[OrderStatus] | None = None,
        payment_methods: list[PaymentMethod] | None = None,
        courier_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
        client_inventory_id: uuid.UUID | None = None,
        sale_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_amount: int | None = None,
        max_amount: int | None = None,
    ) -> list[Order]:
        async with self.uow:
            return list(
                await self.uow.orders.search_orders(
                    skip=skip,
                    limit=limit,
                    statuses=statuses,
                    payment_methods=payment_methods,
                    courier_id=courier_id,
                    client_id=client_id,
                    client_inventory_id=client_inventory_id,
                    sale_type=sale_type,
                    date_from=date_from,
                    date_to=date_to,
                    min_amount=min_amount,
                    max_amount=max_amount,
                )
            )
