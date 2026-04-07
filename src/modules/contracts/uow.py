# src/modules/contracts/uow.py
from src.common.uow import IUnitOfWork
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.contracts.repositories import (
    ContractPriceItemRepository,
    ContractRepository,
    InvoiceRepository,
)
from src.modules.orders.repositories import OrderRepository


class IContractUnitOfWork(IUnitOfWork):
    contracts: ContractRepository
    price_items: ContractPriceItemRepository
    invoices: InvoiceRepository
    orders: OrderRepository  # нужен для generate_invoice()


class ContractUnitOfWork(BaseSQLAlchemyUoW, IContractUnitOfWork):
    async def __aenter__(self) -> "ContractUnitOfWork":
        await super().__aenter__()
        self.contracts = ContractRepository(session=self.session)
        self.price_items = ContractPriceItemRepository(session=self.session)
        self.invoices = InvoiceRepository(session=self.session)
        self.orders = OrderRepository(session=self.session)
        return self
