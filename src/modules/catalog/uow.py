# src/modules/catalog/uow.py
from src.common.uow import IUnitOfWork
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.catalog.repositories import ProductRepository


# 3.1 Доменный интерфейс
class ICatalogUnitOfWork(IUnitOfWork):
    products: ProductRepository


# 3.2 Доменная реализация (DomainSQLAlchemyUoW)
class CatalogUnitOfWork(BaseSQLAlchemyUoW, ICatalogUnitOfWork):
    async def __aenter__(self) -> CatalogUnitOfWork:
        await super().__aenter__()
        self.products = ProductRepository(session=self.session)
        return self
