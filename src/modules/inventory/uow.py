# src/modules/inventory/uow.py
from src.common.uow import IUnitOfWork
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.inventory.repositories import (
    InventoryRepository,
    StockTransactionRepository,
    StockTransferItemRepository,
    StockTransferRepository,
)


# 1. Доменный интерфейс
class IInventoryUnitOfWork(IUnitOfWork):
    inventories: InventoryRepository
    transfers: StockTransferRepository
    transfer_items: StockTransferItemRepository
    transactions: StockTransactionRepository


# 2. Доменная реализация (DomainSQLAlchemyUoW)
class InventoryUnitOfWork(BaseSQLAlchemyUoW, IInventoryUnitOfWork):
    async def __aenter__(self) -> "InventoryUnitOfWork":
        # Вызываем __aenter__ базового класса, чтобы инициализировать self.session
        await super().__aenter__()

        # Инициализируем репозитории домена, прокидывая в них единую транзакционную сессию
        self.inventories = InventoryRepository(session=self.session)
        self.transfers = StockTransferRepository(session=self.session)
        self.transfer_items = StockTransferItemRepository(session=self.session)
        self.transactions = StockTransactionRepository(session=self.session)

        return self
