# src/modules/orders/uow.py
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.contracts.repositories import ContractRepository
from src.modules.finances.repositories import (
    AccountRepository,
)
from src.modules.finances.repositories import (
    TransactionRepository as FinancialTransactionRepository,
)
from src.modules.inventory.repositories import (
    InventoryRepository,
    StockTransactionRepository,
    StockTransferItemRepository,
    StockTransferRepository,
)
from src.modules.orders.repositories import (
    OrderItemRepository,
    OrderRepository,
    OrderStatusLogRepository,
)
from src.modules.users.repositories import UserRepository


class BaseOrderUnitOfWork(BaseSQLAlchemyUoW):
    orders: OrderRepository
    order_items: OrderItemRepository
    status_logs: OrderStatusLogRepository
    users: UserRepository
    inventories: InventoryRepository
    transfers: StockTransferRepository
    transfer_items: StockTransferItemRepository
    transactions: StockTransactionRepository
    accounts: AccountRepository
    financial_transactions: FinancialTransactionRepository
    contracts: ContractRepository

    async def __aenter__(self) -> BaseOrderUnitOfWork:
        await super().__aenter__()

        self.orders = OrderRepository(session=self.session)
        self.order_items = OrderItemRepository(session=self.session)
        self.status_logs = OrderStatusLogRepository(session=self.session)
        self.users = UserRepository(session=self.session)
        self.inventories = InventoryRepository(session=self.session)
        self.transfers = StockTransferRepository(session=self.session)
        self.transfer_items = StockTransferItemRepository(session=self.session)
        self.transactions = StockTransactionRepository(session=self.session)
        self.accounts = AccountRepository(session=self.session)
        self.financial_transactions = FinancialTransactionRepository(
            session=self.session
        )
        self.contracts = ContractRepository(session=self.session)

        return self
