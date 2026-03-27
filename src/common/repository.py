# src\common\repository.py
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.base import BaseModel


class BaseRepository[ModelType: BaseModel]:
    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(
        self,
        id: uuid.UUID,
        active_only: bool = True,
        with_for_update: bool = False,
    ) -> ModelType | None:
        query = select(self.model).where(self.model.id == id)
        if active_only:
            query = query.where(self.model.is_active.is_(True))
        if with_for_update:
            query = query.with_for_update()

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by(
        self, active_only: bool = True, **kwargs: Any
    ) -> ModelType | None:
        query = select(self.model).filter_by(**kwargs)
        if active_only:
            query = query.where(self.model.is_active.is_(True))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True,
        **kwargs: Any,
    ) -> Sequence[ModelType]:
        """Объединенный метод с поддержкой фильтрации (kwargs) и пагинации."""
        query = select(self.model)
        if kwargs:
            query = query.filter_by(**kwargs)
        if active_only:
            query = query.where(self.model.is_active.is_(True))

        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def add(self, obj_data: dict[str, Any]) -> ModelType:
        db_obj = self.model(**obj_data)
        self.session.add(db_obj)
        await self.session.flush()
        return db_obj

    async def add_many(
        self, objs_data: list[dict[str, Any]]
    ) -> Sequence[ModelType]:
        """Bulk Insert для массового добавления товаров в накладную/леджер."""
        if not objs_data:
            return []

        stmt = insert(self.model).values(objs_data).returning(self.model)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update(
        self, id: uuid.UUID, obj_data: dict[str, Any]
    ) -> ModelType:
        # Защита от случайного обновления ID
        obj_data.pop("id", None)

        statement = (
            update(self.model)
            .where(self.model.id == id)
            .values(**obj_data)
            .returning(self.model)
        )
        result = await self.session.execute(statement)
        return result.scalar_one()

    async def archive(self, id: uuid.UUID) -> bool:
        statement = (
            update(self.model)
            .where(self.model.id == id)
            .values(is_active=False)
        )
        result = await self.session.execute(statement)
        return result.rowcount > 0

    async def delete(self, id: uuid.UUID) -> bool:
        statement = delete(self.model).where(self.model.id == id)
        result = await self.session.execute(statement)
        return result.rowcount > 0

    async def count(self, active_only: bool = True, **kwargs: Any) -> int:
        """Подсчет количества записей с учетом фильтров."""
        query = select(func.count()).select_from(self.model)
        if kwargs:
            query = query.filter_by(**kwargs)
        if active_only:
            query = query.where(self.model.is_active.is_(True))

        result = await self.session.execute(query)
        return result.scalar() or 0
