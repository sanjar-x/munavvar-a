# src/modules/orders/repository.py
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Result, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.common.repository import BaseRepository
from src.modules.orders.models import Order, OrderItem, OrderStatus


class OrderRepository(BaseRepository[Order]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Order, session=session)

    async def get_with_details(self, order_id: uuid.UUID) -> Order | None:
        query = (
            select(Order)
            .where(Order.id == order_id, Order.is_active.is_(True))
            .options(selectinload(Order.items).joinedload(OrderItem.product))
        )
        result: Result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_client_orders(
        self, client_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> Sequence[Order]:
        query = (
            select(Order)
            .where(Order.client_id == client_id, Order.is_active.is_(True))
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
            .options(selectinload(Order.items))
        )
        result: Result = await self.session.execute(query)
        return result.scalars().all()

    async def get_courier_tasks(
        self, courier_id: uuid.UUID, statuses: list[OrderStatus] | None = None
    ) -> Sequence[Order]:
        query = select(Order).where(
            Order.courier_id == courier_id, Order.is_active.is_(True)
        )

        if statuses:
            query = query.where(Order.status.in_(statuses))

        query = query.order_by(Order.created_at.desc()).options(
            selectinload(Order.items).joinedload(OrderItem.product)
        )

        result: Result = await self.session.execute(query)
        return result.scalars().all()


class OrderItemRepository(BaseRepository[OrderItem]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=OrderItem, session=session)

    async def add_multi(self, items_data: list[dict[str, Any]]) -> None:
        """BULK INSERT: Вставляет все позиции корзины одним SQL-запросом"""
        if not items_data:
            return
        await self.session.execute(insert(self.model).values(items_data))
