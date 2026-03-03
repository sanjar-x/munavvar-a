# src/modules/orders/uow.py
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.orders.repositories import (
    OrderItemRepository,
    OrderRepository,
)


class OrderUnitOfWork(BaseSQLAlchemyUoW):
    orders: OrderRepository
    order_items: OrderItemRepository

    async def __aenter__(self) -> "OrderUnitOfWork":
        await super().__aenter__()

        self.orders = OrderRepository(session=self.session)
        self.order_items = OrderItemRepository(session=self.session)

        return self
