from abc import ABC, abstractmethod
from typing import Any

import structlog

from src.modules.catalog.repositories import (
    ProductRepository,
)
from src.modules.finances.repositories import (
    AccountRepository,
    TransactionRepository,
)
from src.modules.logistics.inventory.repositories import (
    InventoryRepository,
    StockTransactionRepository,
)
from src.modules.logistics.warehouse.repositories import (
    TransferItemRepository,
    TransferRepository,
)
from src.modules.orders.repositories import (
    OrderItemRepository,
    OrderRepository,
)
from src.modules.users.repositories import IdentityRepository, UserRepository

logger: Any = structlog.get_logger(__name__)


class IUnitOfWork(ABC):
    products: ProductRepository
    accounts: AccountRepository
    transactions: TransactionRepository
    inventories: InventoryRepository
    transfers: TransferRepository
    transfer_items: TransferItemRepository
    stock_transactions: StockTransactionRepository
    orders: OrderRepository
    items: OrderItemRepository
    users: UserRepository
    identities: IdentityRepository

    @abstractmethod
    async def __aenter__(self) -> IUnitOfWork:
        pass

    @abstractmethod
    async def __aexit__(
        self, exc_type: Any, exc_val: Any, exc_tb: Any
    ) -> None:
        pass

    @abstractmethod
    async def flush(self) -> None:
        pass

    @abstractmethod
    async def commit(self) -> None:
        pass

    @abstractmethod
    async def rollback(self) -> None:
        pass
