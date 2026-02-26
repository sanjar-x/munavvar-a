import uuid
from collections.abc import Sequence

from pydantic import BaseModel as PydanticSchema

from src.common.repository import BaseRepository
from src.common.uow import IUnitOfWork
from src.infrastructure.database.base import BaseModel


class BaseService[
    ModelType: BaseModel,
    CreateSchemaType: PydanticSchema,
]:
    def __init__(self, uow: IUnitOfWork, repo_name: str):
        self.uow = uow
        self.repo_name = repo_name

    @property
    def _repo(self) -> BaseRepository[ModelType]:
        return getattr(self.uow, self.repo_name)

    async def get(self, id: uuid.UUID) -> ModelType | None:
        async with self.uow:
            return await self._repo.get(id)

    async def get_multi(
        self, skip: int = 0, limit: int = 100, active_only: bool = True
    ) -> Sequence[ModelType]:
        async with self.uow:
            return await self._repo.get_multi(
                skip=skip, limit=limit, active_only=active_only
            )

    async def add(self, schema: CreateSchemaType) -> ModelType:
        data = schema.model_dump(exclude_unset=True)
        async with self.uow:
            obj = await self._repo.add(data)
            await self.uow.commit()
            return obj

    async def update[AnyUpdateSchema: PydanticSchema](
        self, id: uuid.UUID, schema: AnyUpdateSchema
    ):
        data = schema.model_dump(exclude_unset=True)
        if not data:
            return await self.get(id)

        async with self.uow:
            db_obj = await self._repo.update(id, data)
            if db_obj:
                await self.uow.commit()
            return db_obj

    async def archive(self, id: uuid.UUID) -> bool:
        async with self.uow:
            is_deleted = await self._repo.archive(id)
            if is_deleted:
                await self.uow.commit()
            return is_deleted

    async def delete(self, id: uuid.UUID) -> bool:
        async with self.uow:
            is_deleted = await self._repo.delete(id)
            if is_deleted:
                await self.uow.commit()
            return is_deleted
