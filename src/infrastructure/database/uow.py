from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.uow import IUnitOfWork
from src.core.exceptions import ConflictError
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


class SQLAlchemyUoW(IUnitOfWork):
    def __init__(self, session_factory: Any):
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SQLAlchemyUoW:
        self._session = self._session_factory()
        self.products = ProductRepository(session=self._session)
        self.accounts = AccountRepository(session=self._session)
        self.transactions = TransactionRepository(session=self._session)
        self.stock_transactions = StockTransactionRepository(
            session=self._session
        )
        self.inventories = InventoryRepository(session=self._session)
        self.transfers = TransferRepository(session=self._session)
        self.transfer_items = TransferItemRepository(session=self._session)
        self.orders = OrderRepository(session=self._session)
        self.order_items = OrderItemRepository(session=self._session)
        self.users = UserRepository(session=self._session)
        self.identities = IdentityRepository(session=self._session)
        return self

    async def __aexit__(
        self, exc_type: Any, exc_val: Any, exc_tb: Any
    ) -> None:
        if exc_type:
            await self.rollback()

        if self._session:
            await self._session.close()

    async def flush(self) -> None:
        if self._session:
            await self._session.flush()

    async def commit(self) -> None:
        if self._session:
            try:
                await self._session.commit()
            except IntegrityError as e:
                await self.rollback()
                raise ConflictError(
                    message="Конфликт! Запись с такими параметрами уже существует.",  # noqa: E501
                    error_code="DB_INTEGRITY_ERROR",
                ) from e

    async def rollback(self) -> None:
        if self._session:
            await self._session.rollback()
