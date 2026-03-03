# src/use_cases/delivery/uow.py
from src.common.uow import IUnitOfWork
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.finances.repositories import (
    AccountRepository,
)
from src.modules.finances.repositories import (
    TransactionRepository as FinanceTransactionRepository,
)
from src.modules.inventory.repositories import (
    InventoryRepository,
    StockTransactionRepository,
    StockTransferRepository,
)
from src.modules.orders.repositories import OrderRepository
from src.modules.users.repositories import (
    UserRepository,
)


class IDeliveryUnitOfWork(IUnitOfWork):
    """Интерфейс для композитного UoW доставки."""

    users: UserRepository
    orders: OrderRepository
    inventories: InventoryRepository
    stock_transfers: StockTransferRepository
    stock_transactions: StockTransactionRepository
    accounts: AccountRepository
    finances: FinanceTransactionRepository


class DeliveryUnitOfWork(BaseSQLAlchemyUoW, IDeliveryUnitOfWork):
    """Реализация UoW, объединяющая 3 домена в одну транзакцию."""

    async def __aenter__(self) -> "DeliveryUnitOfWork":
        await super().__aenter__()
        self.users = UserRepository(session=self.session)
        self.orders = OrderRepository(session=self.session)
        self.inventories = InventoryRepository(session=self.session)
        self.stock_transfers = StockTransferRepository(session=self.session)
        self.stock_transactions = StockTransactionRepository(
            session=self.session
        )
        self.accounts = AccountRepository(session=self.session)
        self.finances = FinanceTransactionRepository(session=self.session)
        return self
