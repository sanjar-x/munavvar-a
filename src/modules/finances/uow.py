# src/modules/finances/uow.py
from src.common.uow import IUnitOfWork
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.finances.repositories import (
    AccountRepository,
    TransactionRepository,
)


# 1. Доменный интерфейс (Абстракция для сервисов)
class IFinancesUnitOfWork(IUnitOfWork):
    accounts: AccountRepository
    transactions: TransactionRepository


# 2. Доменная реализация (Связывает инфраструктуру и домен)
class FinancesUnitOfWork(BaseSQLAlchemyUoW, IFinancesUnitOfWork):
    async def __aenter__(self) -> "FinancesUnitOfWork":
        await super().__aenter__()
        # Атрибут создается ТОЛЬКО здесь!
        self.accounts = AccountRepository(session=self.session)
        self.transactions = TransactionRepository(session=self.session)
        return self
