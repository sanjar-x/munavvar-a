# src/modules/orders/uow.py
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.inventory.repositories import (
    InventoryRepository,
    StockTransactionRepository,
    StockTransferRepository,
)
from src.modules.orders.repositories import (
    OrderItemRepository,
    OrderRepository,
)


class BaseOrderUnitOfWork(BaseSQLAlchemyUoW):
    orders: OrderRepository
    order_items: OrderItemRepository
    inventories: InventoryRepository
    transfers: StockTransferRepository
    transactions: StockTransactionRepository

    async def __aenter__(self) -> "BaseOrderUnitOfWork":
        await super().__aenter__()

        self.orders = OrderRepository(session=self.session)
        self.order_items = OrderItemRepository(session=self.session)
        self.inventories = InventoryRepository(session=self.session)
        self.transfers = StockTransferRepository(session=self.session)
        self.transactions = StockTransactionRepository(session=self.session)

        return self
