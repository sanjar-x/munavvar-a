# src/modules/catalog/repositories.py
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Result, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.common.repository import BaseRepository
from src.infrastructure.database.models import Product
from src.modules.catalog.enums import ProductType


class ProductRepository(BaseRepository[Product]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Product, session=session)

    async def get_product(self, product_id: uuid.UUID) -> Product | None:
        product: Product | None = await self.get(product_id)
        return product

    async def get_multi_by_ids(
        self, product_ids: list[uuid.UUID]
    ) -> Sequence[Product]:
        if not product_ids:
            return []

        query = (
            select(self.model)
            .where(
                self.model.id.in_(product_ids), self.model.is_active.is_(True)
            )
            .options(selectinload(self.model.returnable_item))
        )
        result: Result[Any] = await self.session.execute(query)
        return result.scalars().all()

    async def get_catalog_by_type(
        self, product_type: ProductType, skip: int = 0, limit: int = 100
    ) -> Sequence[Product]:
        """
        ДЛЯ ФРОНТЕНДА: Выдача товаров конкретной категории на витрину.
        """
        query = (
            select(self.model)
            .where(
                self.model.type == product_type, self.model.is_active.is_(True)
            )
            .options(selectinload(self.model.returnable_item))
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result: Result[Any] = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_json_attribute(
        self, key: str, value: Any, skip: int = 0, limit: int = 100
    ) -> Sequence[Product]:
        """
        DBA МАГИЯ: Поиск товаров по значению внутри JSONB поля attributes.
        Например: await uow.products.get_by_json_attribute("material", "PC")
        """
        query = (
            select(self.model)
            .where(
                self.model.attributes.op("->>")(key) == str(value),
                self.model.is_active.is_(True),
            )
            .offset(skip)
            .limit(limit)
        )
        result: Result[Any] = await self.session.execute(query)
        return result.scalars().all()
