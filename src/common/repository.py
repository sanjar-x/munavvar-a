import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.base import BaseModel


class BaseRepository[ModelType: BaseModel]:
    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(self, id: uuid.UUID) -> ModelType | None:
        return await self.session.get(self.model, id)

    async def get_by(self, **kwargs: Any) -> ModelType | None:
        query = select(self.model).filter_by(**kwargs)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_multi(
        self, skip: int = 0, limit: int = 100, active_only: bool = True
    ) -> Sequence[ModelType]:
        query = select(self.model)

        if active_only:
            query = query.where(self.model.is_active.is_(True))

        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_multi_by(
        self, skip: int = 0, limit: int = 100, **kwargs: Any
    ) -> Sequence[ModelType]:
        """Универсальный поиск СПИСКА записей по совпадению с пагинацией."""
        query = (
            select(self.model).filter_by(**kwargs).offset(skip).limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def add(self, obj_data: dict[str, Any]) -> ModelType:
        """Создание новой записи."""
        db_obj = self.model(**obj_data)
        self.session.add(db_obj)
        await self.session.flush()
        return db_obj

    async def update(
        self, id: uuid.UUID, obj_data: dict[str, Any]
    ) -> ModelType | None:
        """Массовое обновление записи с возвратом обновленного объекта."""
        if not obj_data:
            return await self.get(id)

        statement = (
            update(self.model)
            .where(self.model.id == id)
            .values(**obj_data)
            .returning(
                self.model
            )  # Магия: просим БД вернуть обновленную строку
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def archive(self, id: uuid.UUID) -> bool:
        """Логическое удаление (архивация)."""
        statement = (
            update(self.model)
            .where(self.model.id == id)
            .values(is_active=False)
        )
        result = await self.session.execute(statement)
        return result.rowcount > 0

    async def delete(self, id: uuid.UUID) -> bool:
        """Физическое удаление из базы данных."""
        statement = delete(self.model).where(self.model.id == id)
        result = await self.session.execute(statement)
        return result.rowcount > 0
