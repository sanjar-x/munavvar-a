# src/modules/orders/repositories.py
import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Result, delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.common.repository import BaseRepository
from src.infrastructure.database.models import (
    Inventory,
    Order,
    OrderItem,
    StockTransfer,
)
from src.modules.orders.enums import OrderStatus, PaymentMethod


class OrderItemRepository(BaseRepository[OrderItem]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=OrderItem, session=session)

    async def get_by_order_and_product(
        self, order_id: uuid.UUID, product_id: uuid.UUID
    ) -> OrderItem | None:
        query = select(self.model).where(
            self.model.order_id == order_id,
            self.model.product_id == product_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_by_order_and_product(
        self, order_id: uuid.UUID, product_id: uuid.UUID
    ) -> None:
        stmt = delete(self.model).where(
            self.model.order_id == order_id,
            self.model.product_id == product_id,
        )
        await self.session.execute(stmt)

    async def update_quantity(
        self, order_item_id: uuid.UUID, new_quantity: int
    ) -> None:
        stmt = (
            update(self.model)
            .where(self.model.id == order_item_id)
            .values(quantity=new_quantity)
        )
        await self.session.execute(stmt)


class OrderRepository(BaseRepository[Order]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Order, session=session)

    async def get_client_orders(
        self, client_id: uuid.UUID, skip: int = 0, limit: int = 20
    ) -> Sequence[Order]:
        """
        Для приложения клиента: История его заказов.
        Сортировка от новых к старым.
        """
        query = (
            select(self.model)
            .where(self.model.client_id == client_id)
            .options(
                joinedload(self.model.courier),
                joinedload(self.model.client_inventory).joinedload(
                    Inventory.user
                ),
            )
            .order_by(desc(self.model.created_at))
            .offset(skip)
            .limit(limit)
        )
        result: Result = await self.session.execute(query)
        return result.scalars().all()

    async def get_active_courier_orders(
        self, courier_id: uuid.UUID
    ) -> Sequence[Order]:
        """
        Для приложения курьера: Список заказов "На сегодня",
        которые еще не доставлены или не отменены.
        """
        query = (
            select(self.model)
            .where(
                self.model.courier_id == courier_id,
                self.model.status.in_(
                    [
                        OrderStatus.ASSIGNED,
                        OrderStatus.IN_TRANSIT,
                        OrderStatus.ARRIVED,
                    ]
                ),
            )
            .options(
                joinedload(self.model.client),
                joinedload(self.model.client_inventory).joinedload(
                    Inventory.user
                ),
                selectinload(self.model.items).joinedload(OrderItem.product),
            )
            .order_by(self.model.created_at.asc())
        )
        result: Result = await self.session.execute(query)
        return result.scalars().all()

    async def get_with_details(
        self, order_id: uuid.UUID, with_for_update: bool = False
    ) -> Order | None:
        query = (
            select(self.model)
            .where(self.model.id == order_id)
            .options(
                joinedload(self.model.client),
                joinedload(self.model.client_inventory).joinedload(
                    Inventory.user
                ),
                joinedload(self.model.courier),
                selectinload(self.model.items).joinedload(OrderItem.product),
                selectinload(self.model.stock_transfers).selectinload(
                    StockTransfer.items
                ),
            )
        )

        if with_for_update:
            query = query.with_for_update()

        result: Result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def search_orders(
        self,
        skip: int = 0,
        limit: int = 50,
        statuses: list[OrderStatus] | None = None,
        payment_methods: list[PaymentMethod] | None = None,
        courier_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
        client_inventory_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_amount: int | None = None,
        max_amount: int | None = None,
    ) -> Sequence[Order]:
        """
        Универсальный поиск заказов по всем доступным атрибутам модели.
        """
        query = select(self.model)

        if statuses:
            query = query.where(self.model.status.in_(statuses))
        if payment_methods:
            query = query.where(self.model.payment_method.in_(payment_methods))

        # Точные совпадения по ID
        if courier_id:
            query = query.where(self.model.courier_id == courier_id)
        if client_id:
            query = query.where(self.model.client_id == client_id)
        if client_inventory_id:
            query = query.where(
                self.model.client_inventory_id == client_inventory_id
            )

        # Диапазоны дат (предполагается, что created_at есть в BaseModel)
        if date_from:
            query = query.where(self.model.created_at >= date_from)
        if date_to:
            query = query.where(self.model.created_at <= date_to)

        # Диапазоны сумм
        if min_amount is not None:
            query = query.where(self.model.total_amount >= min_amount)
        if max_amount is not None:
            query = query.where(self.model.total_amount <= max_amount)

        query = (
            query.options(
                joinedload(self.model.client),
                joinedload(self.model.client_inventory),
                joinedload(self.model.courier),
                selectinload(self.model.items).joinedload(OrderItem.product),
                selectinload(self.model.stock_transfers).selectinload(
                    StockTransfer.items
                ),
            )
            .order_by(desc(self.model.updated_at))
            .offset(skip)
            .limit(limit)
        )

        result: Result = await self.session.execute(query)
        return result.scalars().all()

    async def update_status(
        self, order_id: uuid.UUID, new_status: OrderStatus
    ) -> Order | None:
        stmt = (
            update(self.model)
            .where(self.model.id == order_id)
            .values(status=new_status)
            .returning(self.model)
        )
        result: Result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
