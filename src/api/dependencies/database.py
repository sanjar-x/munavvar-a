# src/api/dependencies/database.py
from src.common.uow import IUnitOfWork
from src.infrastructure.database.session import async_session_maker
from src.infrastructure.database.uow import SQLAlchemyUoW


def get_uow() -> IUnitOfWork:
    """
    FastAPI зависимость (Dependency).
    Создает и возвращает экземпляр Unit of Work, передавая фабрику сессий БД.
    """
    return SQLAlchemyUoW(session_factory=async_session_maker)
