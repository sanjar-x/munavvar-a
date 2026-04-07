# src/modules/catalog/services.py
import uuid
from collections.abc import Sequence
from typing import Any

from src.common.service import BaseService
from src.infrastructure.database.models import Product
from src.modules.catalog.dtos import ProductDTO, product_to_dto
from src.modules.catalog.enums import ProductType
from src.modules.catalog.exceptions import (
    InvalidReturnableItemError,
    ProductHasAssociatedProductsError,
    ProductHasStockError,
    ProductNotFoundError,
)
from src.modules.catalog.repositories import ProductRepository
from src.modules.catalog.schemas import ProductCreate
from src.modules.catalog.uow import CatalogUnitOfWork


class CatalogService(
    BaseService[
        Product,
        ProductCreate,
        CatalogUnitOfWork,
        ProductDTO,
    ]
):
    def __init__(self, uow: CatalogUnitOfWork):
        super().__init__(uow=uow)

    @property
    def _repo(self) -> ProductRepository:
        return self.uow.products

    async def get_catalog(
        self,
        skip: int = 0,
        limit: int = 100,
        product_type: ProductType | None = None,
    ) -> Sequence[ProductDTO]:
        """
        Выдача витрины для клиентского приложения (B2C/B2B).
        Если передан product_type, фильтруем по нему (например, только WATER).
        """
        async with self.uow:
            if product_type:
                products = await self._repo.get_catalog_by_type(
                    product_type=product_type,
                    skip=skip,
                    limit=limit,
                )
            else:
                products = await self._repo.get_multi(
                    skip=skip, limit=limit, active_only=False
                )
            return [product_to_dto(p) for p in products]

    async def get_by_ids(
        self, product_ids: list[uuid.UUID]
    ) -> Sequence[ProductDTO]:
        """
        PUBLIC API для соседних доменов (Orders).
        Используется корзиной для получения актуальных цен при чекауте.
        """
        if not product_ids:
            return []
        async with self.uow:
            products = await self._repo.get_multi_by_ids(product_ids)
            return [product_to_dto(p) for p in products]

    async def search_by_attribute(
        self,
        key: str,
        value: Any,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ProductDTO]:
        """
        Продвинутый поиск для UI.
        Позволяет найти все кулеры цвета "white"
        или компрессорного типа охлаждения.
        """
        async with self.uow:
            products = await self._repo.get_by_json_attribute(
                key=key,
                value=value,
                skip=skip,
                limit=limit,
            )
            return [product_to_dto(p) for p in products]

    # ==========================================
    # COMMANDS (МУТАЦИИ ДЛЯ АДМИНКИ)
    # ==========================================

    async def add_product(self, dto: ProductCreate) -> ProductDTO:
        """
        Создание нового товара с жесткой бизнес-валидацией.
        """
        # Бизнес-правило 1: Только у воды (WATER)
        # может быть привязана возвратная тара
        if dto.returnable_item_id and dto.type != ProductType.WATER:
            raise InvalidReturnableItemError(
                message=(
                    "Возвратная тара может быть привязана"
                    " только к товарам типа WATER"
                )
            )

        if dto.type == ProductType.WATER and not dto.returnable_item_id:
            raise InvalidReturnableItemError(
                message=(
                    "Товар типа WATER не может быть создан"
                    " без привязки к возвратной таре (CONTAINER)"
                )
            )

        async with self.uow:
            if dto.returnable_item_id:
                bottle = await self._repo.get(dto.returnable_item_id)
                if not bottle:
                    raise ProductNotFoundError(
                        product_id=dto.returnable_item_id,
                        message="Указанная возвратная тара не найдена",
                    )

                if bottle.type != ProductType.CONTAINER:
                    raise InvalidReturnableItemError(
                        message=(
                            "В качестве возвратной тары"
                            " можно указать только товар типа CONTAINER"
                        )
                    )

            data = dto.model_dump(exclude_unset=True)
            new_product = await self._repo.add(data)
            await self.uow.commit()
            return product_to_dto(new_product)

    async def hard_delete(self, product_id: uuid.UUID) -> bool:
        """
        Полное удаление товара из БД.
        Запрещено если на складах/транспортах есть остатки.
        """
        async with self.uow:
            product = await self._repo.get(product_id, active_only=False)
            if not product:
                raise ProductNotFoundError(product_id=product_id)

            if await self._repo.has_stock(product_id):
                raise ProductHasStockError(product_id=product_id)

            if await self._repo.has_associated_products(product_id):
                raise ProductHasAssociatedProductsError(product_id=product_id)

            await self._repo.delete(product_id)
            await self.uow.commit()
            return True
