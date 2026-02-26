from src.common.service import BaseService
from src.common.uow import IUnitOfWork
from src.modules.catalog.enums import ProductType
from src.modules.catalog.models import Product
from src.modules.catalog.repositories import ProductRepository
from src.modules.catalog.schemas import ProductCreate


class CatalogService(BaseService[Product, ProductCreate]):
    def __init__(self, uow: IUnitOfWork):
        super().__init__(uow=uow, repo_name="products")

    @property
    def _repo(self) -> ProductRepository:
        return self.uow.products

    async def get_catalog(
        self, skip: int, limit: int, product_type: ProductType | None
    ):
        async with self.uow:
            if product_type:
                return await self._repo.get_catalog_by_type(
                    product_type=product_type,
                    skip=skip,
                    limit=limit,
                )
            else:
                return await self._repo.get_multi(
                    skip=skip,
                    limit=limit,
                )
