# src/application/inventories/uow.py
from src.common.uow import IUnitOfWork
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.catalog.repositories import ProductRepository
from src.modules.inventory.repositories import (
    InventoryRepository,
    StockTransactionRepository,
)
from src.modules.users.repositories import UserRepository


class IInventoryUnitOfWork(IUnitOfWork):
    inventories: InventoryRepository
    stock_transactions: StockTransactionRepository
    products: ProductRepository
    users: UserRepository


class InventoryUnitOfWork(BaseSQLAlchemyUoW, IInventoryUnitOfWork):
    async def __aenter__(self) -> "InventoryUnitOfWork":
        await super().__aenter__()

        self.inventories = InventoryRepository(session=self.session)
        self.stock_transactions = StockTransactionRepository(session=self.session)
        self.products = ProductRepository(session=self.session)
        self.users = UserRepository(session=self.session)

        return self
