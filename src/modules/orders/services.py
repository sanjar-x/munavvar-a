# src/modules/orders/services.py
import uuid
from collections.abc import Sequence
from datetime import datetime

from src.common.service import BaseService
from src.modules.catalog.services import CatalogService
from src.modules.orders.enums import OrderStatus
from src.modules.orders.exceptions import (
    CourierAssignmentError,
    EmptyCartError,
    OrderAccessDeniedError,
    OrderNotFoundError,
    ProductsUnavailableError,
)
from src.modules.orders.models import Order
from src.modules.orders.repositories import OrderRepository
from src.modules.orders.schemas import OrderCreate
from src.modules.orders.uow import OrderUnitOfWork


class OrderService(BaseService[Order, OrderCreate, OrderUnitOfWork]):
    def __init__(self, uow: OrderUnitOfWork, catalog_service: CatalogService):
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
        Формирует корзину заказа (OrderItem) и высчитывает итоговую сумму (total_amount),
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

        total_amount = 0
        order_items_data = []

        # 2. Высчитываем стоимость строк и итоговую сумму
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

        async with self.uow:
            # 3. Сохраняем шапку Заказа с подсчитанной суммой
            new_order = await self.uow.orders.add(
                {
                    "client_id": client_id,
                    "payment_method": dto.payment_method,
                    "status": OrderStatus.NEW,
                    "total_amount": total_amount,
                }
            )

            # 4. Привязываем строки корзины к новому заказу
            for item_data in order_items_data:
                item_data["order_id"] = new_order.id

            # 5. Сохраняем строки (Bulk Insert)
            await self.uow.order_items.add_many(order_items_data)

            await self.uow.commit()
            return new_order

    async def get_order_with_details(
        self, order_id: uuid.UUID, requesting_user_id: uuid.UUID | None = None
    ) -> Order:
        """
        Глубокая загрузка заказа.
        Если передан requesting_user_id (от клиента/курьера), проверяем права доступа (IDOR).
        Если не передан - считаем, что это запрос от Админа/CRM.
        """
        async with self.uow:
            order = await self.uow.orders.get_with_details(order_id)
            if not order:
                raise OrderNotFoundError(order_id=order_id)

            # IDOR Проверка
            if requesting_user_id:
                if requesting_user_id not in (
                    order.client_id,
                    order.courier_id,
                ):
                    raise OrderAccessDeniedError(
                        user_id=requesting_user_id, order_id=order_id
                    )

            return order

    async def assign_courier(
        self, order_id: uuid.UUID, courier_id: uuid.UUID
    ) -> Order:
        """
        Диспетчеризация: Логист назначает заказ конкретному курьеру.
        """
        async with self.uow:
            # Блокируем заказ (чтобы два логиста одновременно не назначили разных курьеров)
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
        self, order_id: uuid.UUID, new_status: OrderStatus
    ) -> Order:
        """
        Легковесный метод для обновления статусов (например, курьер жмет 'В ПУТИ').
        """
        async with self.uow:
            updated_order = await self.uow.orders.update_status(
                order_id, new_status
            )
            if not updated_order:
                raise OrderNotFoundError(order_id=order_id)
            await self.uow.commit()
            return updated_order

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
        limit: int = 50,
        status: OrderStatus | None = None,
        courier_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Sequence[Order]:
        """Универсальный поиск заказов для Администратора/CRM."""
        async with self.uow:
            return await self.uow.orders.search_orders(
                skip=skip,
                limit=limit,
                status=status,
                courier_id=courier_id,
                client_id=client_id,
                date_from=date_from,
                date_to=date_to,
            )
