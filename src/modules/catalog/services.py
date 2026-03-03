# src/modules/catalog/services.py
import uuid
from collections.abc import Sequence
from typing import Any

from src.common.service import BaseService
from src.core.exceptions import BadRequestError, NotFoundError
from src.modules.catalog.enums import ProductType
from src.modules.catalog.models import Product
from src.modules.catalog.repositories import ProductRepository
from src.modules.catalog.schemas import ProductCreate
from src.modules.catalog.uow import CatalogUnitOfWork


class CatalogService(BaseService[Product, ProductCreate, CatalogUnitOfWork]):
    def __init__(self, uow: CatalogUnitOfWork):
        super().__init__(uow=uow)

    @property
    def _repo(self) -> ProductRepository:
        return self.uow.products

    # ==========================================
    # QUERIES (ЧТЕНИЕ)
    # ==========================================

    async def get_catalog(
        self,
        skip: int = 0,
        limit: int = 100,
        product_type: ProductType | None = None,
    ) -> Sequence[Product]:
        """
        Выдача витрины для клиентского приложения (B2C/B2B).
        Если передан product_type, фильтруем по нему (например, только WATER).
        """
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
                    active_only=True,  # На витрине только активные товары!
                )

    async def get_by_ids(
        self, product_ids: list[uuid.UUID]
    ) -> Sequence[Product]:
        """
        PUBLIC API для соседних доменов (Orders).
        Используется корзиной для получения актуальных цен при чекауте.
        """
        if not product_ids:
            return []
        async with self.uow:
            return await self._repo.get_multi_by_ids(product_ids)

    async def search_by_attribute(
        self, key: str, value: Any, skip: int = 0, limit: int = 100
    ) -> Sequence[Product]:
        """
        Продвинутый поиск для UI.
        Позволяет найти все кулеры цвета "white" или компрессорного типа охлаждения.
        """
        async with self.uow:
            return await self._repo.get_by_json_attribute(
                key=key, value=value, skip=skip, limit=limit
            )

    # ==========================================
    # COMMANDS (МУТАЦИИ ДЛЯ АДМИНКИ)
    # ==========================================

    async def add_product(self, dto: ProductCreate) -> Product:
        """
        Создание нового товара с жесткой бизнес-валидацией.
        """
        # Бизнес-правило 1: Только у воды (WATER) может быть привязана возвратная тара (CONTAINER)
        if dto.returnable_item_id and dto.type != ProductType.WATER:
            raise BadRequestError(
                message="Возвратная тара может быть привязана только к товарам типа WATER"
            )

        async with self.uow:
            # Бизнес-правило 2: Проверяем, что привязываемая тара реально существует и это именно тара
            if dto.returnable_item_id:
                bottle = await self._repo.get(dto.returnable_item_id)
                if not bottle:
                    raise NotFoundError(
                        message="Указанная возвратная тара не найдена"
                    )
                if bottle.type != ProductType.CONTAINER:
                    raise BadRequestError(
                        message="В качестве возвратной тары можно указать только товар типа BOTTLE"
                    )

            # Используем родительский метод _repo.add для сохранения
            data = dto.model_dump(exclude_unset=True)
            new_product = await self._repo.add(data)
            await self.uow.commit()
            return new_product

    # Примечание: методы get(), get_multi(), update(), archive() и delete()
    # уже доступны благодаря наследованию от BaseService.
    # Если для update() потребуется особая валидация тары, мы переопределим его (override).
