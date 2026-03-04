# src\application\order\uow.py
from src.common.uow import IUnitOfWork
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.catalog.repositories import ProductRepository
from src.modules.finances.repositories import (
    AccountRepository,
    TransactionRepository,
)
from src.modules.inventory.repositories import (
    InventoryRepository,
    StockTransactionRepository,
    StockTransferRepository,
)
from src.modules.orders.repositories import (
    OrderItemRepository,
    OrderRepository,
)
from src.modules.users.repositories import (
    UserRepository,
)


class IOrderUnitOfWork(IUnitOfWork):
    products: ProductRepository
    accounts: AccountRepository
    transactions: TransactionRepository
    inventories: InventoryRepository
    stock_transactions: StockTransactionRepository
    stock_transfers: StockTransferRepository
    order_items: OrderItemRepository
    orders: OrderRepository
    users: UserRepository


class OrderUnitOfWork(BaseSQLAlchemyUoW, IOrderUnitOfWork):
    async def __aenter__(self) -> "OrderUnitOfWork":
        await super().__aenter__()
        self.products = ProductRepository(session=self.session)
        self.accounts = AccountRepository(session=self.session)
        self.transactions = TransactionRepository(session=self.session)
        self.inventories = InventoryRepository(session=self.session)
        self.stock_transactions = StockTransactionRepository(
            session=self.session
        )
        self.stock_transfers = StockTransferRepository(session=self.session)
        self.order_items = OrderItemRepository(session=self.session)
        self.orders = OrderRepository(session=self.session)
        self.users = UserRepository(session=self.session)

        return self
