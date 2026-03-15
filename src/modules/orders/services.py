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
    TransferStatus,
    TransferType,
)
from src.modules.orders.enums import OrderStatus, PaymentMethod
from src.modules.orders.exceptions import (
    CannotRemoveLastItemError,
    ClientInventoryNotFoundError,
    CourierAssignmentError,
    DeliveryQuantityExceededError,
    EmptyCartError,
    InsufficientTaraError,
    OrderAccessDeniedError,
    OrderNotFoundError,
    ProductsUnavailableError,
)
from src.modules.orders.repositories import OrderRepository
from src.modules.orders.schemas import OrderCreate, OrderItemActual, TaraCheckRequest
from src.modules.orders.uow import BaseOrderUnitOfWork


class BaseOrderService(BaseService[Order, OrderCreate, BaseOrderUnitOfWork]):
    def __init__(self, uow: BaseOrderUnitOfWork, catalog_service: CatalogService):
        super().__init__(uow=uow)
        self.catalog_service = catalog_service

    @property
    def _repo(self) -> OrderRepository:
        return self.uow.orders

    # --- БИЗНЕС-ЛОГИКА ---

    async def create_order(self, client_id: uuid.UUID, dto: OrderCreate) -> Order:
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

        capitalization_applied = False

        if exchange_items:
            async with self.uow:
                # Получаем баланс пустой тары клиента (с блокировкой от Race Condition)
                inventory = await self.uow.inventories.get_inventory_with_balances(
                    dto.client_inventory_id,
                    with_for_update=True,
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
                        shortages.append({
                            "product_id": str(product.id),
                            "product_name": product.name,
                            "returnable_item_id": str(required_tare_id),
                            "required": item.quantity,
                            "available": available_tare,
                            "deficit": item.quantity - available_tare,
                        })

                if shortages and not dto.capitalize_missing_tara:
                    raise InsufficientTaraError(shortages=shortages)

                # Автоматическое оприходование дефицита тары
                if shortages and dto.capitalize_missing_tara:
                    vendor_inv = await self.uow.inventories.get_vendor_inventory()

                    transfer = await self.uow.transfers.add({
                        "from_id": vendor_inv.id,
                        "to_id": inventory.id,
                        "type": TransferType.INITIAL_BALANCE,
                        "status": TransferStatus.COMPLETED,
                        "created_by_id": client_id,
                        "accepted_by_id": client_id,
                    })

                    for shortage in shortages:
                        await self.uow.transfer_items.add({
                            "transfer_id": transfer.id,
                            "product_id": uuid.UUID(shortage["returnable_item_id"]),
                            "quantity": shortage["deficit"],
                        })
                        await self.uow.transactions.add({
                            "product_id": uuid.UUID(shortage["returnable_item_id"]),
                            "transfer_id": transfer.id,
                            "from_id": vendor_inv.id,
                            "to_id": inventory.id,
                            "quantity": shortage["deficit"],
                        })

                    capitalization_applied = True
                    await self.uow.commit()

        total_amount = 0
        order_items_data = []

        # 2. Высчитываем стоимость строк и итоговую сумму
        for item in dto.items:
            current_price = price_map[item.product_id]
            total_amount += current_price * item.quantity

            order_items_data.append({
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": current_price,  # Snapshot Pattern
            })

        async with self.uow:
            # 3. Сохраняем шапку Заказа с подсчитанной суммой
            new_order = await self.uow.orders.add({
                "client_id": client_id,
                "client_inventory_id": dto.client_inventory_id,
                "payment_method": dto.payment_method,
                "status": OrderStatus.NEW,
                "total_amount": total_amount,
            })

            # 4. Привязываем строки корзины к новому заказу
            for item_data in order_items_data:
                item_data["order_id"] = new_order.id

            # 5. Сохраняем строки (Bulk Insert)
            await self.uow.order_items.add_many(order_items_data)

            await self.uow.commit()

            # Transient-атрибут для Pydantic-сериализации (не колонка БД)
            new_order.capitalization_applied = capitalization_applied
            return new_order

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
                raise ValueError("Нельзя менять состав заказа в текущем статусе")

            # 3. Ищем, есть ли уже такой товар в заказе
            existing_item = await self.uow.order_items.get_by_order_and_product(
                order_id=order_id, product_id=product_id
            )

            if existing_item:
                new_quantity = existing_item.quantity + quantity
                await self.uow.order_items.update_quantity(
                    order_item_id=existing_item.id, new_quantity=new_quantity
                )
            else:
                await self.uow.order_items.add({
                    "order_id": order_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": current_price,
                })

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
                raise ValueError("Нельзя менять состав заказа в текущем статусе")

            existing_item = await self.uow.order_items.get_by_order_and_product(
                order_id=order_id, product_id=product_id
            )

            # Если товара и так нет, просто отдаем текущий заказ
            if not existing_item:
                return order

            # Защита: запрет удаления последнего товара (пустой заказ недопустим)
            if len(order.items) <= 1:
                raise CannotRemoveLastItemError()

            # 3. Высчитываем сумму для вычета до удаления
            amount_to_subtract = existing_item.unit_price * existing_item.quantity

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

    async def assign_courier(self, order_id: uuid.UUID, courier_id: uuid.UUID) -> Order:
        """
        Диспетчеризация: Логист назначает заказ конкретному курьеру.
        """
        async with self.uow:
            order = await self.uow.orders.get_with_details(
                order_id, with_for_update=True
            )
            if not order:
                raise OrderNotFoundError(order_id=order_id)

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
            updated_order = await self.uow.orders.update_status(order_id, new_status)
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
        self, order: Order, actual_items_dto: list[OrderItemActual] | None = None
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
            actual_map = {item.product_id: item.quantity for item in actual_items_dto}
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
                    await self.uow.order_items.update_quantity(item.id, item.quantity)

                new_total += item.unit_price * item.quantity

            # Обновляем итоговую сумму заказа
            order.total_amount = new_total
            await self.uow.orders.update(order.id, {"total_amount": new_total})

        # Получаем активный инвентарь (машину) курьера
        courier_inventory = await self.uow.inventories.get_courier_inventory(
            order.courier_id
        )
        if not courier_inventory:
            raise ValueError("У курьера нет активного инвентаря (машины)")

        # 1. Создаем накладную на доставку (Full Water OUT)
        delivery_transfer = await self.uow.transfers.add({
            "from_id": courier_inventory.id,
            "to_id": order.client_inventory_id,
            "type": TransferType.CLIENT_DELIVERY,
            "status": TransferStatus.COMPLETED,
            "created_by_id": order.courier_id,
            "accepted_by_id": order.client_id,
            "order_id": order.id,
        })

        # 2. Создаем накладную на возврат тары (Empty Water IN)
        # Сначала проверим, какие товары в заказе имеют возвратную тару
        returnable_items = []
        for item in order.items:
            if item.product.returnable_item_id:
                returnable_items.append({
                    "product_id": item.product.returnable_item_id,
                    "quantity": item.quantity,
                })

        return_transfer = None
        if returnable_items:
            return_transfer = await self.uow.transfers.add({
                "from_id": order.client_inventory_id,
                "to_id": courier_inventory.id,
                "type": TransferType.CLIENT_RETURN,
                "status": TransferStatus.COMPLETED,
                "created_by_id": order.courier_id,
                "accepted_by_id": order.courier_id,
                "order_id": order.id,
            })

        # 3. Проводим транзакции для обеих накладных
        # а) Доставка
        for item in order.items:
            await self.uow.transactions.add({
                "product_id": item.product_id,
                "transfer_id": delivery_transfer.id,
                "from_id": courier_inventory.id,
                "to_id": order.client_inventory_id,
                "quantity": item.quantity,
            })

        # б) Возврат тары
        if return_transfer:
            for item_data in returnable_items:
                await self.uow.transactions.add({
                    "product_id": item_data["product_id"],
                    "transfer_id": return_transfer.id,
                    "from_id": order.client_inventory_id,
                    "to_id": courier_inventory.id,
                    "quantity": item_data["quantity"],
                })

        # 4. Финансовое закрытие заказа
        await self._process_financial_settlement(order)

    async def _process_financial_settlement(self, order: Order) -> None:
        """
        Финансовое закрытие заказа при доставке.
        Перенесено из OrderService.delivery() для единообразия.
        Создает финансовые транзакции в зависимости от способа оплаты:
        - Начисляет долг клиенту (Revenue → Client)
        - CASH: перебрасывает долг на курьера (Client → Courier)
        - CARD: создает pending-транзакцию на эквайринг (Client → Card)
        """
        client_account = await self.uow.accounts.get_client_account(order.client_id)
        if not client_account:
            return
        revenue_account = await self.uow.accounts.get_system_revenue_account()

        # Начислить долг клиенту
        client_account.balance += order.total_amount
        financial_txns = [
            {
                "from_id": revenue_account.id,
                "to_id": client_account.id,
                "amount": order.total_amount,
                "order_id": order.id,
                "status": TransactionStatus.COMPLETED,
                "reason": "Задолженность за заказ",
            }
        ]

        if order.payment_method == PaymentMethod.CASH:
            courier_account = await self.uow.accounts.get_courier_account(
                order.courier_id
            )
            if courier_account:
                client_account.balance -= order.total_amount
                courier_account.balance += order.total_amount
                financial_txns.append({
                    "from_id": client_account.id,
                    "to_id": courier_account.id,
                    "amount": order.total_amount,
                    "order_id": order.id,
                    "status": TransactionStatus.COMPLETED,
                    "reason": "Оплата наличными курьеру",
                })

        elif order.payment_method == PaymentMethod.CARD:
            card_account = await self.uow.accounts.get_system_card_account()
            financial_txns.append({
                "from_id": client_account.id,
                "to_id": card_account.id,
                "amount": order.total_amount,
                "order_id": order.id,
                "status": TransactionStatus.PENDING,
                "reason": "Перевод на карту",
            })

        await self.uow.financial_transactions.add_many(financial_txns)

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
                raise ClientInventoryNotFoundError(inventory_id=dto.client_inventory_id)

            balances = {b.product_id: b.quantity for b in inventory.balances}

            shortages = []
            for product, item in exchange_items:
                required_tare_id = product.returnable_item_id
                available_tare = balances.get(required_tare_id, 0)
                if available_tare < item.quantity:
                    shortages.append({
                        "product_id": product.id,
                        "product_name": product.name,
                        "returnable_item_id": required_tare_id,
                        "required": item.quantity,
                        "available": available_tare,
                        "deficit": item.quantity - available_tare,
                    })

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

    async def get_courier_tasks(self, courier_id: uuid.UUID) -> Sequence[Order]:
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
                    date_from=date_from,
                    date_to=date_to,
                    min_amount=min_amount,
                    max_amount=max_amount,
                )
            )
