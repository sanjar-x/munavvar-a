# src/application/courier/uow.py
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
)
from src.modules.orders.repositories import OrderRepository
from src.modules.users.repositories import (
    IdentityRepository,
    PhoneNumberRepository,
    UserRepository,
)


class ICourierUnitOfWork(IUnitOfWork):
    products: ProductRepository
    identities: IdentityRepository
    phone_numbers: PhoneNumberRepository
    users: UserRepository
    accounts: AccountRepository
    transactions: TransactionRepository
    inventories: InventoryRepository
    stock_transactions: StockTransactionRepository
    orders: OrderRepository


class CourierUnitOfWork(BaseSQLAlchemyUoW, ICourierUnitOfWork):
    async def __aenter__(self) -> CourierUnitOfWork:
        await super().__aenter__()
        self.products = ProductRepository(session=self.session)
        self.identities = IdentityRepository(session=self.session)
        self.phone_numbers = PhoneNumberRepository(session=self.session)
        self.users = UserRepository(session=self.session)
        self.accounts = AccountRepository(session=self.session)
        self.transactions = TransactionRepository(session=self.session)
        self.inventories = InventoryRepository(session=self.session)
        self.stock_transactions = StockTransactionRepository(
            session=self.session
        )
        self.orders = OrderRepository(session=self.session)

        return self
