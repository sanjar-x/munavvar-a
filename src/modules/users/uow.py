# src/modules/users/uow.py

from src.common.uow import IUnitOfWork
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.finances.repositories import AccountRepository
from src.modules.inventory.repositories import (
    InventoryRepository,
    StockTransactionRepository,
    StockTransferItemRepository,
    StockTransferRepository,
)
from src.modules.users.repositories import IdentityRepository, UserRepository


# 1. Доменный интерфейс (Абстракция для сервисов)
class IUserUnitOfWork(IUnitOfWork):
    users: UserRepository
    identities: IdentityRepository
    accounts: AccountRepository
    inventories: InventoryRepository
    transfers: StockTransferRepository
    transfer_items: StockTransferItemRepository
    transactions: StockTransactionRepository


# 2. Доменная реализация (Связывает инфраструктуру и домен)
class UserUnitOfWork(BaseSQLAlchemyUoW, IUserUnitOfWork):
    async def __aenter__(self) -> "UserUnitOfWork":
        await super().__aenter__()

        self.users = UserRepository(session=self.session)
        self.identities = IdentityRepository(session=self.session)
        self.accounts = AccountRepository(session=self.session)
        self.inventories = InventoryRepository(session=self.session)
        self.transfers = StockTransferRepository(session=self.session)
        self.transfer_items = StockTransferItemRepository(session=self.session)
        self.transactions = StockTransactionRepository(session=self.session)

        return self
