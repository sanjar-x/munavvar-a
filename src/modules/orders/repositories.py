# src/modules/orders/repositories.py
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Result, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.common.repository import BaseRepository
from src.infrastructure.database.models import (
    Inventory,
    Order,
    OrderItem,
    OrderStatusLog,
    StockTransfer,
    StockTransferItem,
    User,
)
from src.modules.orders.enums import OrderStatus, PaymentMethod, SaleType


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

    @staticmethod
    def _details_options():
        return (
            joinedload(Order.client).selectinload(User.identities),
            joinedload(Order.courier).selectinload(User.identities),
            joinedload(Order.client_inventory).joinedload(Inventory.user),
            selectinload(Order.items).joinedload(OrderItem.product),
            selectinload(Order.stock_transfers)
            .selectinload(StockTransfer.items)
            .joinedload(StockTransferItem.product),
            selectinload(Order.stock_transfers).joinedload(
                StockTransfer.from_inventory
            ),
            selectinload(Order.stock_transfers).joinedload(
                StockTransfer.to_inventory
            ),
        )

    async def get_client_orders(
        self,
        client_id: uuid.UUID,
        skip: int = 0,
        limit: int = 20,
        status: OrderStatus | None = None,
    ) -> Sequence[Order]:
        """
        Для приложения клиента: История его заказов.
        Сортировка от новых к старым.
        """
        query = (
            select(self.model)
            .where(self.model.client_id == client_id)
            .options(*self._details_options())
            .order_by(desc(self.model.created_at))
            .offset(skip)
            .limit(limit)
        )
        if status:
            query = query.where(self.model.status == status)
        result: Result = await self.session.execute(query)
        return result.scalars().all()

    async def count_client_orders(
        self,
        client_id: uuid.UUID,
        status: OrderStatus | None = None,
    ) -> int:
        """Общее количество заказов клиента (для пагинации)."""
        query = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.client_id == client_id)
        )
        if status:
            query = query.where(self.model.status == status)
        return await self.session.scalar(query) or 0

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
            .options(*self._details_options())
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
            .options(*self._details_options())
        )

        if with_for_update:
            query = query.with_for_update(of=self.model)

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
        sale_type: SaleType | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_amount: int | None = None,
        max_amount: int | None = None,
        contract_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[Order], int]:
        """
        Универсальный поиск заказов по всем доступным атрибутам модели.
        Возвращает кортеж (список заказов, общее количество).
        """
        base_query = select(self.model).where(self.model.is_active.is_(True))

        if statuses:
            base_query = base_query.where(self.model.status.in_(statuses))
        if payment_methods:
            base_query = base_query.where(
                self.model.payment_method.in_(payment_methods)
            )

        # Точные совпадения по ID
        if courier_id:
            base_query = base_query.where(self.model.courier_id == courier_id)
        if client_id:
            base_query = base_query.where(self.model.client_id == client_id)
        if client_inventory_id:
            base_query = base_query.where(
                self.model.client_inventory_id == client_inventory_id
            )
        if sale_type:
            base_query = base_query.where(self.model.sale_type == sale_type)
        if contract_id:
            base_query = base_query.where(
                self.model.contract_id == contract_id
            )

        # Диапазоны дат (предполагается, что created_at есть в BaseModel)
        if date_from:
            base_query = base_query.where(self.model.created_at >= date_from)
        if date_to:
            base_query = base_query.where(self.model.created_at <= date_to)

        # Диапазоны сумм
        if min_amount is not None:
            base_query = base_query.where(
                self.model.total_amount >= min_amount
            )
        if max_amount is not None:
            base_query = base_query.where(
                self.model.total_amount <= max_amount
            )

        count_query = select(func.count()).select_from(base_query.subquery())
        total: int = await self.session.scalar(count_query) or 0

        items_query = (
            base_query.options(*self._details_options())
            .order_by(desc(self.model.created_at))
            .offset(skip)
            .limit(limit)
        )

        result: Result = await self.session.execute(items_query)
        return result.scalars().all(), total

    async def get_delivered_by_contract(
        self,
        contract_id: uuid.UUID,
        date_from: date,
        date_to: date,
    ) -> Sequence[Order]:
        """Все выполненные заказы по договору за период.
        Используется при генерации Invoice и акта сверки.

        date_from/date_to — включительно (полные сутки по UTC).
        """
        from_dt = datetime.combine(date_from, datetime.min.time()).replace(
            tzinfo=UTC
        )
        # Захватываем весь день date_to — берём начало следующего дня
        to_dt = datetime.combine(
            date_to + timedelta(days=1), datetime.min.time()
        ).replace(tzinfo=UTC)
        query = (
            select(self.model)
            .where(
                self.model.contract_id == contract_id,
                self.model.status.in_(
                    [
                        OrderStatus.DELIVERED,
                        OrderStatus.PICKUP_COMPLETED,
                    ]
                ),
                self.model.created_at >= from_dt,
                self.model.created_at < to_dt,
                self.model.is_active.is_(True),
            )
            .order_by(self.model.created_at)
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

    async def bulk_cancel_by_contract(
        self,
        contract_id: uuid.UUID,
    ) -> list[tuple[uuid.UUID, int | None]]:
        """Отмена всех NEW/ASSIGNED заказов по договору.
        Возвращает список (order_id, reserved_credit_amount)
        для корректного возврата кредита.
        """
        cancellable = [OrderStatus.NEW, OrderStatus.ASSIGNED]
        stmt = (
            update(self.model)
            .where(
                self.model.contract_id == contract_id,
                self.model.status.in_(cancellable),
                self.model.is_active.is_(True),
            )
            .values(
                status=OrderStatus.CANCELLED,
                reserved_credit_amount=0,
            )
            .returning(
                self.model.id,
                self.model.reserved_credit_amount,
            )
        )
        result: Result = await self.session.execute(stmt)
        return list(result.all())

    async def count_inflight_by_contract(
        self,
        contract_id: uuid.UUID,
    ) -> int:
        """Количество активных (не завершённых) заказов по договору.
        Используется для предупреждения при приостановке.
        """
        inflight = [
            OrderStatus.IN_TRANSIT,
            OrderStatus.ARRIVED,
        ]
        query = (
            select(func.count())
            .select_from(self.model)
            .where(
                self.model.contract_id == contract_id,
                self.model.status.in_(inflight),
                self.model.is_active.is_(True),
            )
        )
        return await self.session.scalar(query) or 0

    async def get_stale_orders(
        self,
        older_than: datetime,
        status: OrderStatus = OrderStatus.NEW,
        limit: int = 500,
    ) -> Sequence[Order]:
        """Найти заказы в статусе дольше порога.

        Используется job-ом автоматической экспирации.
        FOR UPDATE SKIP LOCKED — безопасно для параллельных
        запусков (Railway cron / ручной вызов).
        """
        query = (
            select(self.model)
            .where(
                self.model.status == status,
                self.model.created_at < older_than,
                self.model.is_active.is_(True),
            )
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()


class OrderStatusLogRepository(BaseRepository[OrderStatusLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=OrderStatusLog, session=session)

    async def log_transition(
        self,
        order_id: uuid.UUID,
        old_status: OrderStatus | None,
        new_status: OrderStatus,
        changed_by_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> OrderStatusLog:
        return await self.add(
            {
                "order_id": order_id,
                "old_status": old_status,
                "new_status": new_status,
                "changed_by_id": changed_by_id,
                "reason": reason,
            }
        )
