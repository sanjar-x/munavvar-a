# src/modules/orders/services.py
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from src.common.service import BaseService
from src.core.constants import WALKIN_USER_ID
from src.core.exceptions import BadRequestError, NotFoundError
from src.infrastructure.database.models import Order, StockTransfer
from src.modules.catalog.public import CatalogService
from src.modules.contracts.enums import ContractStatus
from src.modules.contracts.exceptions import (
    ContractExpiredError,
    ContractNotActiveError,
    ContractRequiredError,
    CreditLimitExceededError,
)
from src.modules.contracts.models import Contract
from src.modules.finances.enums import TransactionStatus
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.inventory.exceptions import (
    InsufficientStockError,
    InventoryNotFoundError,
)
from src.modules.orders.enums import OrderStatus, PaymentMethod, SaleType
from src.modules.orders.exceptions import (
    CannotRemoveLastItemError,
    ClientInventoryNotFoundError,
    CourierAssignmentError,
    DeliveryQuantityExceededError,
    EmptyCartError,
    InsufficientTaraError,
    InvalidOrderStatusError,
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
from src.modules.users.enums import Role


class BaseOrderService(BaseService[Order, OrderCreate, BaseOrderUnitOfWork]):
    _DELIVERY_ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
        OrderStatus.NEW: {OrderStatus.CANCELLED},
        OrderStatus.ASSIGNED: {
            OrderStatus.IN_TRANSIT,
            OrderStatus.CANCELLED,
        },
        OrderStatus.IN_TRANSIT: {
            OrderStatus.ARRIVED,
            OrderStatus.CANCELLED,
        },
        OrderStatus.ARRIVED: {
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
        },
    }
    _PICKUP_ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
        OrderStatus.NEW: {OrderStatus.CANCELLED},
    }

    def __init__(
        self, uow: BaseOrderUnitOfWork, catalog_service: CatalogService
    ):
        super().__init__(uow=uow)
        self.catalog_service = catalog_service

    @property
    def _repo(self) -> OrderRepository:
        return self.uow.orders

    @classmethod
    def _get_allowed_statuses(
        cls, *, sale_type: SaleType, current_status: OrderStatus
    ) -> list[OrderStatus]:
        transition_map = (
            cls._PICKUP_ALLOWED_TRANSITIONS
            if sale_type == SaleType.WAREHOUSE_PICKUP
            else cls._DELIVERY_ALLOWED_TRANSITIONS
        )
        return sorted(
            transition_map.get(current_status, set()),
            key=lambda status: status.value,
        )

    @classmethod
    def _ensure_status_transition_allowed(
        cls,
        *,
        order: Order,
        new_status: OrderStatus,
    ) -> None:
        if order.status == new_status:
            return

        if order.sale_type == SaleType.WAREHOUSE_PICKUP:
            if new_status == OrderStatus.PICKUP_COMPLETED:
                raise InvalidPickupOperationError(
                    order_id=order.id,
                    reason=(
                        "Статус PICKUP_COMPLETED нельзя выставить вручную. "
                        "Используйте complete-pickup."
                    ),
                )
            if new_status in (
                OrderStatus.ASSIGNED,
                OrderStatus.IN_TRANSIT,
                OrderStatus.ARRIVED,
                OrderStatus.DELIVERED,
            ):
                raise InvalidPickupOperationError(
                    order_id=order.id,
                    reason=(
                        f"Заказ самовывоза не может перейти в статус {new_status}. "
                        "Используйте complete-pickup."
                    ),
                )

        allowed_statuses = cls._get_allowed_statuses(
            sale_type=order.sale_type,
            current_status=order.status,
        )
        if new_status not in allowed_statuses:
            raise InvalidOrderStatusError(
                order_id=order.id,
                current_status=order.status,
                target_status=new_status,
                allowed_statuses=allowed_statuses,
                message=(
                    "Недопустимый переход статуса заказа: "
                    f"{order.status} -> {new_status}"
                ),
            )

    # --- БИЗНЕС-ЛОГИКА ---

    async def create_order(
        self,
        client_id: uuid.UUID,
        dto: OrderCreate,
        client_role: Role = Role.CLIENT_B2C,
    ) -> Order:
        """
        Процесс Checkout'а.
        Формирует корзину заказа (OrderItem) и высчитывает (total_amount),
        замораживая цены из Каталога на момент покупки.

        Для B2B-клиентов с payment_method=CONTRACT — обязательно нужен
        активный договор. Цены и кредитный лимит проверяются ВНУТРИ
        транзакции после SELECT FOR UPDATE (защита от TOCTOU).
        """
        if not dto.items:
            raise EmptyCartError()

        # 1. Каталожные цены: собственный UoW CatalogService — это
        #    намеренно вне основной транзакции (snapshot read, без блокировки).
        product_ids = [item.product_id for item in dto.items]
        products = await self.catalog_service.get_by_ids(product_ids)
        price_map = {p.id: p.price for p in products}

        missing_ids = [pid for pid in product_ids if pid not in price_map]
        if missing_ids:
            raise ProductsUnavailableError(missing_product_ids=missing_ids)

        # 1.1 Товары, требующие возврата тары
        exchange_items = [
            (p, next(i for i in dto.items if i.product_id == p.id))
            for p in products
            if p.returnable_item_id is not None
        ]

        # 3. Всё — оприходование тары, договор, создание заказа — атомарно
        async with self.uow:
            capitalization_applied = False

            # --- Блок A: CONTRACT-специфичная логика ---
            # Весь этот блок выполняется ВНУТРИ async with self.uow,
            # ПОСЛЕ SELECT FOR UPDATE на строку договора, чтобы исключить
            # гонку TOCTOU (статус мог измениться между внешней проверкой
            # и реальной фиксацией заказа).
            contract: Contract | None = None
            if dto.payment_method == PaymentMethod.CONTRACT:
                contract = await self._get_and_validate_contract_locked(
                    client_id=client_id,
                    client_role=client_role,
                )
                # Переопределяем каталожные цены договорными ценами
                contract_prices = (
                    await self.uow.contracts.get_price_map_for_products(
                        contract.id, product_ids
                    )
                )
                price_map.update(contract_prices)

            # 2. Высчитываем стоимость строк и итоговую сумму
            #    (ВНУТРИ транзакции, чтобы использовать
            #    актуальные договорные цены)
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

            # --- Блок B: Проверка и резервирование кредитного лимита ---
            if contract is not None:
                await self._check_and_reserve_credit(
                    contract=contract,
                    amount=total_amount,
                )

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
                                "product_id": product.id,
                                "product_name": product.name,
                                "returnable_item_id": required_tare_id,
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
                    await self._create_stock_transfer(
                        from_id=vendor_inv.id,
                        to_id=inventory.id,
                        transfer_type=TransferType.INITIAL_BALANCE,
                        items=[
                            {
                                "product_id": s["returnable_item_id"],
                                "quantity": s["deficit"],
                            }
                            for s in shortages
                        ],
                        created_by_id=client_id,
                        accepted_by_id=client_id,
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
                    "contract_id": contract.id if contract else None,
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
                raise InventoryNotFoundError(
                    inventory_id=dto.warehouse_id,
                    message=f"Склад {dto.warehouse_id} не найден",
                )

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
                                "product_id": product.id,
                                "product_name": product.name,
                                "returnable_item_id": required_tare_id,
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
                    await self._create_stock_transfer(
                        from_id=vendor_inv.id,
                        to_id=client_inventory.id,
                        transfer_type=TransferType.INITIAL_BALANCE,
                        items=[
                            {
                                "product_id": s["returnable_item_id"],
                                "quantity": s["deficit"],
                            }
                            for s in shortages
                        ],
                        created_by_id=created_by_id,
                        accepted_by_id=created_by_id,
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
        self,
        order_id: uuid.UUID,
        product_id: uuid.UUID,
        quantity: int,
        requesting_user_id: uuid.UUID | None = None,
    ) -> Order:
        """
        Добавляет товар в существующий заказ или увеличивает количество,
        если товар уже в корзине. Пересчитывает итоговую сумму.
        """
        if quantity <= 0:
            raise BadRequestError(
                message="Количество должно быть строго больше нуля",
                error_code="INVALID_QUANTITY",
                details={"provided_quantity": quantity},
            )

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

            # IDOR Проверка
            if requesting_user_id and order.client_id != requesting_user_id:
                raise OrderAccessDeniedError(
                    user_id=requesting_user_id, order_id=order_id
                )

            # Бизнес-проверка: менять можно только новые заказы
            if order.status != OrderStatus.NEW:
                raise InvalidOrderStatusError(
                    order_id=order_id,
                    current_status=order.status,
                    expected_status=OrderStatus.NEW,
                    message=("Нельзя менять состав заказа в текущем статусе"),
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
        self,
        order_id: uuid.UUID,
        product_id: uuid.UUID,
        requesting_user_id: uuid.UUID | None = None,
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

            # IDOR Проверка
            if requesting_user_id and order.client_id != requesting_user_id:
                raise OrderAccessDeniedError(
                    user_id=requesting_user_id, order_id=order_id
                )

            if order.status != OrderStatus.NEW:
                raise InvalidOrderStatusError(
                    order_id=order_id,
                    current_status=order.status,
                    expected_status=OrderStatus.NEW,
                    message=("Нельзя менять состав заказа в текущем статусе"),
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

            if order.status not in (
                OrderStatus.NEW,
                OrderStatus.ASSIGNED,
            ):
                raise CourierAssignmentError(
                    order_id=order_id,
                    courier_id=courier_id,
                    reason=(
                        "Назначение или смена курьера разрешены только "
                        "для заказов в статусах NEW и ASSIGNED"
                    ),
                )

            courier = await self.uow.users.get_courier(id=courier_id)
            if not courier:
                raise CourierAssignmentError(
                    order_id=order_id,
                    courier_id=courier_id,
                    reason=(
                        "Назначить можно только активного пользователя "
                        f"с ролью {Role.COURIER.value}"
                    ),
                )

            courier_inventory = (
                await self.uow.inventories.get_courier_inventory(courier_id)
            )
            if not courier_inventory:
                raise CourierAssignmentError(
                    order_id=order_id,
                    courier_id=courier_id,
                    reason="У курьера нет активного инвентаря (машины)",
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
        requesting_user_id: uuid.UUID | None = None,
    ) -> Order:
        async with self.uow:
            # Блокируем заказ для обновления статуса и возможных движений товаров
            order = await self.uow.orders.get_with_details(
                order_id, with_for_update=True
            )
            if not order:
                raise OrderNotFoundError(order_id=order_id)

            if requesting_user_id and requesting_user_id != order.courier_id:
                raise OrderAccessDeniedError(
                    user_id=requesting_user_id,
                    order_id=order_id,
                )

            old_status = order.status

            self._ensure_status_transition_allowed(
                order=order,
                new_status=new_status,
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

            # CONTRACT: возврат зарезервированного кредита при отмене.
            # decrement вызывается только если заказ ещё не был исполнен
            # (DELIVERED/PICKUP_COMPLETED уже сделали decrement в settlement).
            _settled_statuses = {
                OrderStatus.DELIVERED,
                OrderStatus.PICKUP_COMPLETED,
            }
            if (
                new_status == OrderStatus.CANCELLED
                and order.payment_method == PaymentMethod.CONTRACT
                and order.contract_id is not None
                and old_status not in _settled_statuses
            ):
                await self.uow.contracts.decrement_credit_used(
                    order.contract_id, order.total_amount
                )

            await self.uow.commit()
            return updated_order

    async def _get_and_validate_contract_locked(
        self,
        client_id: uuid.UUID,
        client_role: Role,
    ) -> Contract:
        """Получить активный договор клиента с блокировкой FOR UPDATE.

        Вызывается ВНУТРИ async with self.uow.
        Проверяет статус и срок действия ПОСЛЕ захвата строки,
        что исключает TOCTOU-гонку.
        """
        if client_role != Role.CLIENT_B2B:
            raise BadRequestError(
                message=(
                    "Оплата по договору доступна только для "
                    "юридических лиц (CLIENT_B2B)"
                ),
                error_code="CONTRACT_PAYMENT_NOT_ALLOWED",
                details={"client_role": str(client_role)},
            )

        contract = await self.uow.contracts.get_active_for_client(
            client_id, with_for_update=True
        )
        if contract is None:
            raise ContractRequiredError(client_id=client_id)

        # Проверяем статус ПОСЛЕ SELECT FOR UPDATE
        if contract.status != ContractStatus.ACTIVE:
            raise ContractNotActiveError(
                contract_id=contract.id,
                status=str(contract.status),
            )

        # Проверяем срок действия (UTC-safe)
        today = datetime.now(UTC).date()
        if contract.end_date and contract.end_date < today:
            raise ContractExpiredError(contract_id=contract.id)

        return contract

    async def _check_and_reserve_credit(
        self,
        contract: Contract,
        amount: int,
    ) -> None:
        """Проверить кредитный лимит и зарезервировать сумму.

        Вызывается ВНУТРИ async with self.uow ПОСЛЕ
        _get_and_validate_contract_locked (строка уже залочена).
        credit_limit = 0 означает безлимитный кредит.
        """
        if contract.credit_limit != 0:
            total_exposure = contract.credit_used + amount
            if total_exposure > contract.credit_limit:
                raise CreditLimitExceededError(
                    contract_id=contract.id,
                    credit_limit=contract.credit_limit,
                    current_exposure=contract.credit_used,
                    order_amount=amount,
                )

        await self.uow.contracts.increment_credit_used(contract.id, amount)

    @staticmethod
    def _build_returnable_items(
        order_items: list,
    ) -> list[dict[str, uuid.UUID | int]]:
        """Aggregates container quantities paired with delivered water items."""
        returnable_map: dict[uuid.UUID, int] = {}
        for item in order_items:
            if item.product.returnable_item_id and item.quantity > 0:
                tare_id = item.product.returnable_item_id
                returnable_map[tare_id] = (
                    returnable_map.get(tare_id, 0) + item.quantity
                )

        return [
            {"product_id": product_id, "quantity": quantity}
            for product_id, quantity in returnable_map.items()
        ]

    async def _create_stock_transfer(
        self,
        *,
        from_id: uuid.UUID,
        to_id: uuid.UUID,
        transfer_type: TransferType,
        items: list[dict[str, Any]],
        created_by_id: uuid.UUID,
        accepted_by_id: uuid.UUID | None = None,
        order_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> StockTransfer:
        """
        Вспомогательный метод: создаёт накладную (StockTransfer),
        строки накладной (StockTransferItem) и проводки в леджере
        (StockTransaction) за один вызов.

        items — список словарей {"product_id": UUID, "quantity": int}.
        Позиции с quantity == 0 пропускаются.
        """
        transfer_data: dict[str, Any] = {
            "from_id": from_id,
            "to_id": to_id,
            "type": transfer_type,
            "status": TransferStatus.COMPLETED,
            "created_by_id": created_by_id,
            "accepted_by_id": accepted_by_id or created_by_id,
        }
        if order_id is not None:
            transfer_data["order_id"] = order_id
        if reason is not None:
            transfer_data["reason"] = reason

        transfer = await self.uow.transfers.add(transfer_data)
        await self.uow.flush()

        effective_items = [i for i in items if i.get("quantity", 0) > 0]

        await self.uow.transfer_items.add_many(
            [
                {
                    "transfer_id": transfer.id,
                    "product_id": i["product_id"],
                    "quantity": i["quantity"],
                }
                for i in effective_items
            ]
        )
        await self.uow.transactions.add_many(
            [
                {
                    "transfer_id": transfer.id,
                    "product_id": i["product_id"],
                    "from_id": from_id,
                    "to_id": to_id,
                    "quantity": i["quantity"],
                }
                for i in effective_items
            ]
        )

        return transfer

    async def _handle_order_fulfillment(
        self,
        order: Order,
        actual_items_dto: list[OrderItemActual] | None = None,
    ) -> None:
        """
        Автоматическое создание и проведение StockTransfer при доставке.
        1. [NEW] Корректировка заказа (если переданы actual_items)
        2. Списание полной воды: Курьер -> Клиент
        3. Начисление физической тары клиенту: VIRTUAL_VENDOR -> Клиент
        4. Забор пустой тары: Клиент -> Курьер
        """
        if not order.courier_id:
            raise BadRequestError(
                message="Заказ не может быть доставлен без курьера",
                error_code="COURIER_NOT_ASSIGNED",
                details={"order_id": str(order.id)},
            )

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
            raise BadRequestError(
                message="У курьера нет активного инвентаря (машины)",
                error_code="COURIER_INVENTORY_NOT_FOUND",
                details={"courier_id": str(order.courier_id)},
            )

        # Повторно получаем с блокировкой и актуальными остатками
        courier_inventory = (
            await self.uow.inventories.get_inventory_with_balances(
                courier_inv_row.id, with_for_update=True
            )
        )
        if not courier_inventory:
            raise BadRequestError(
                message="У курьера нет активного инвентаря (машины)",
                error_code="COURIER_INVENTORY_NOT_FOUND",
                details={"courier_id": str(order.courier_id)},
            )

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

        # 1. Накладная на доставку (Full Water OUT): Курьер → Клиент
        delivery_items = [
            {"product_id": i.product_id, "quantity": i.quantity}
            for i in order.items
            if i.quantity > 0
        ]
        await self._create_stock_transfer(
            from_id=courier_inventory.id,
            to_id=order.client_inventory_id,
            transfer_type=TransferType.CLIENT_DELIVERY,
            items=delivery_items,
            created_by_id=order.courier_id,
            accepted_by_id=order.client_id,
            order_id=order.id,
        )

        # 2. Начисляем клиенту физическую тару, связанную с доставленной водой
        returnable_items = self._build_returnable_items(order.items)
        if returnable_items:
            vendor_inv = await self.uow.inventories.get_vendor_inventory()

            # б) VIRTUAL_VENDOR → Клиент (начисление физической тары)
            await self._create_stock_transfer(
                from_id=vendor_inv.id,
                to_id=order.client_inventory_id,
                transfer_type=TransferType.INITIAL_BALANCE,
                items=returnable_items,
                created_by_id=order.courier_id,
                accepted_by_id=order.client_id,
                order_id=order.id,
                reason="Container issued with delivery",
            )

            # 3. в) Возврат тары: Клиент → Курьер
            await self._create_stock_transfer(
                from_id=order.client_inventory_id,
                to_id=courier_inventory.id,
                transfer_type=TransferType.CLIENT_RETURN,
                items=returnable_items,
                created_by_id=order.courier_id,
                accepted_by_id=order.courier_id,
                order_id=order.id,
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
        3. VIRTUAL_VENDOR -> Client (физическая тара в полной бутыли)
        4. WAREHOUSE_TARA_RETURN: Client → Warehouse (тара)
        5. Финансовая проводка
        """
        if not order.warehouse_id:
            raise BadRequestError(
                message="Заказ самовывоза без warehouse_id",
                error_code="WAREHOUSE_ID_MISSING",
                details={"order_id": str(order.id)},
            )

        warehouse = await self.uow.inventories.get_inventory_with_balances(
            order.warehouse_id,
            inv_type=InventoryType.WAREHOUSE,
            with_for_update=True,
        )
        if not warehouse:
            raise InventoryNotFoundError(
                inventory_id=order.warehouse_id,
                message=f"Склад {order.warehouse_id} не найден",
            )

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

        sale_items = [
            {"product_id": i.product_id, "quantity": i.quantity}
            for i in order.items
            if i.quantity > 0
        ]

        # 1. WAREHOUSE_SALE: Warehouse → Client
        await self._create_stock_transfer(
            from_id=warehouse.id,
            to_id=order.client_inventory_id,
            transfer_type=TransferType.WAREHOUSE_SALE,
            items=sale_items,
            created_by_id=completed_by_id,
            accepted_by_id=order.client_id,
            order_id=order.id,
        )

        # 2. Начисляем клиенту физическую тару, связанную с выданной водой
        returnable_items = self._build_returnable_items(order.items)
        if returnable_items:
            vendor_inv = await self.uow.inventories.get_vendor_inventory()

            # VIRTUAL_VENDOR → Client (начисление физической тары)
            await self._create_stock_transfer(
                from_id=vendor_inv.id,
                to_id=order.client_inventory_id,
                transfer_type=TransferType.INITIAL_BALANCE,
                items=returnable_items,
                created_by_id=completed_by_id,
                accepted_by_id=order.client_id,
                order_id=order.id,
                reason="Container issued with warehouse pickup",
            )

            # 3. WAREHOUSE_TARA_RETURN: Client → Warehouse
            await self._create_stock_transfer(
                from_id=order.client_inventory_id,
                to_id=warehouse.id,
                transfer_type=TransferType.WAREHOUSE_TARA_RETURN,
                items=returnable_items,
                created_by_id=completed_by_id,
                accepted_by_id=completed_by_id,
                order_id=order.id,
            )

        # 5. Cleanup: списание товара с Walk-in inventory
        # Анонимный покупатель забрал товар и ушёл — обнуляем его inventory
        if order.client_id == WALKIN_USER_ID:
            loss_inv = await self.uow.inventories.get_loss_inventory()
            cleanup_items = [
                {"product_id": i.product_id, "quantity": i.quantity}
                for i in order.items
                if i.quantity > 0
            ]
            cleanup_items.extend(returnable_items)
            await self._create_stock_transfer(
                from_id=order.client_inventory_id,
                to_id=loss_inv.id,
                transfer_type=TransferType.LOSS_WRITE_OFF,
                items=cleanup_items,
                created_by_id=completed_by_id,
                accepted_by_id=completed_by_id,
                order_id=order.id,
            )

        # 6. Финансовое закрытие
        await self._process_pickup_settlement(order)

    async def _process_financial_settlement(self, order: Order) -> None:
        """
        Финансовое закрытие заказа при доставке.
        Создает финансовые транзакции в зависимости от способа оплаты:
        - Начисляет долг клиенту (Revenue → Client)
        - CASH: перебрасывает долг на курьера (Client → Courier)
        - CARD: создает pending-транзакцию на эквайринг (Client → Card)
        - CONTRACT: только долг клиенту, оплата позже по договору

        ВАЖНО: Балансы accounts.balance обновляются ТРИГГЕРОМ БД
        (update_account_balances), а не приложением. Приложение
        только вставляет записи в таблицу transactions.
        """
        client_account = await self.uow.accounts.get_client_account(
            order.client_id
        )
        if not client_account:
            raise NotFoundError(
                message=(
                    f"Финансовый счет клиента {order.client_id} не найден. "
                    "Создайте счет перед обработкой заказа."
                ),
                error_code="CLIENT_ACCOUNT_NOT_FOUND",
                details={"client_id": str(order.client_id)},
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

        if order.payment_method == PaymentMethod.CASH:
            if order.courier_id:
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

        # CONTRACT: только Revenue → Client, долг остается
        # на балансе клиента до оплаты по договору

        await self.uow.financial_transactions.add_many(financial_txns)

        # При CONTRACT-оплате — возвращаем зарезервированный кредит,
        # т.к. долг теперь перешёл в финансовый баланс клиента.
        if (
            order.payment_method == PaymentMethod.CONTRACT
            and order.contract_id is not None
        ):
            await self.uow.contracts.decrement_credit_used(
                order.contract_id, order.total_amount
            )

    async def _process_pickup_settlement(self, order: Order) -> None:
        """
        Финансовое закрытие самовывоза.
        Создает транзакции в зависимости от способа оплаты:
        - CASH: Revenue→Client + Client→Cash (обе COMPLETED)
        - CARD: Revenue→Client (COMPLETED) + Client→Card (PENDING)
        - CONTRACT: только Revenue→Client (COMPLETED), долг остается
        """
        client_account = await self.uow.accounts.get_client_account(
            order.client_id
        )
        if not client_account:
            raise NotFoundError(
                message=(
                    f"Финансовый счет клиента {order.client_id} не найден"
                ),
                error_code="CLIENT_ACCOUNT_NOT_FOUND",
                details={"client_id": str(order.client_id)},
            )
        revenue_account = await self.uow.accounts.get_system_revenue_account()

        # Долг клиенту (самовывоз)
        financial_txns: list[dict] = [
            {
                "from_id": revenue_account.id,
                "to_id": client_account.id,
                "amount": order.total_amount,
                "order_id": order.id,
                "status": TransactionStatus.COMPLETED,
                "reason": "Задолженность за заказ (самовывоз)",
            }
        ]

        if order.payment_method == PaymentMethod.CASH:
            cash_account = await self.uow.accounts.get_system_cash_account()
            financial_txns.append(
                {
                    "from_id": client_account.id,
                    "to_id": cash_account.id,
                    "amount": order.total_amount,
                    "order_id": order.id,
                    "status": TransactionStatus.COMPLETED,
                    "reason": ("Оплата наличными на складе (самовывоз)"),
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
                    "reason": ("Перевод на карту (самовывоз)"),
                }
            )

        # CONTRACT: только Revenue → Client, долг остается
        # на балансе клиента до оплаты по договору

        await self.uow.financial_transactions.add_many(financial_txns)

        # При CONTRACT-оплате — возвращаем зарезервированный кредит.
        if (
            order.payment_method == PaymentMethod.CONTRACT
            and order.contract_id is not None
        ):
            await self.uow.contracts.decrement_credit_used(
                order.contract_id, order.total_amount
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
        sale_type: SaleType | None = None,
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
