# src\infrastructure\database\uow.py
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.uow import IUnitOfWork
from src.core.exceptions import ConflictError


class BaseSQLAlchemyUoW(IUnitOfWork):
    def __init__(self, session_factory: Any):
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        """Безопасный доступ к сессии. Гарантирует, что сессия существует."""
        if self._session is None:
            raise RuntimeError(
                "Сессия БД не инициализирована. UoW должен использоваться "
                "строго внутри контекстного менеджера `async with`."
            )
        return self._session

    async def __aenter__(self) -> BaseSQLAlchemyUoW:
        self._session = self._session_factory()
        return self

    async def __aexit__(
        self, exc_type: Any, exc_val: Any, exc_tb: Any
    ) -> None:
        if exc_type:
            await self.rollback()

        if self._session:
            await self._session.close()

    async def flush(self) -> None:
        if self._session:
            await self._session.flush()

    async def commit(self) -> None:
        if self._session:
            try:
                await self._session.commit()
            except IntegrityError as e:
                await self.rollback()
                raise ConflictError(
                    message=(
                        "Конфликт! Запись уже существует"
                        " или нарушает ограничения БД."
                    ),
                    error_code="DB_INTEGRITY_ERROR",
                ) from e

    async def rollback(self) -> None:
        if self._session:
            await self._session.rollback()
