# src/modules/contracts/uow.py
from src.common.uow import IUnitOfWork
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.contracts.repositories import (
    ContractPriceItemRepository,
    ContractRepository,
    InvoiceRepository,
)
from src.modules.finances.repositories import (
    AccountRepository,
    TransactionRepository,
)
from src.modules.orders.repositories import OrderRepository


class IContractUnitOfWork(IUnitOfWork):
    contracts: ContractRepository
    price_items: ContractPriceItemRepository
    invoices: InvoiceRepository
    orders: OrderRepository
    accounts: AccountRepository       # для актов сверки
    transactions: TransactionRepository  # для платёжных записей


class ContractUnitOfWork(BaseSQLAlchemyUoW, IContractUnitOfWork):
    async def __aenter__(self) -> "ContractUnitOfWork":
        await super().__aenter__()
        self.contracts = ContractRepository(session=self.session)
        self.price_items = ContractPriceItemRepository(session=self.session)
        self.invoices = InvoiceRepository(session=self.session)
        self.orders = OrderRepository(session=self.session)
        self.accounts = AccountRepository(session=self.session)
        self.transactions = TransactionRepository(session=self.session)
        return self
