import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlalchemy.orm import sessionmaker

from src.core.config import settings
from src.infrastructure.database.uow import SQLAlchemyUoW

# Мы используем ту же локальную БД, но благодаря строгим rollback()
# она не будет загрязняться тестовыми данными.
test_engine: AsyncEngine = create_async_engine(settings.database_url())


@pytest.fixture(scope="function")
async def db_session():
    """
    Создает изолированную сессию БД для КАЖДОГО теста.
    Все изменения откатываются (rollback) после завершения теста.
    """
    async with test_engine.connect() as connection:
        # 1. Открываем главную транзакцию
        transaction = await connection.begin()

        # 2. Создаем сессию, привязанную к этой транзакции
        # (join_transaction_mode позволяет UoW делать commit внутри savepoint,
        # не коммитя данные в реальную базу)
        session_factory = sessionmaker(
            connection,
            class_=AsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )  # ty:ignore[no-matching-overload]
        session = session_factory()

        yield session  # Отдаем сессию тесту

        # 3. ПОСЛЕ ТЕСТА: Закрываем сессию и ОТКАТЫВАЕМ главную транзакцию
        await session.close()
        await transaction.rollback()


@pytest.fixture(scope="function")
async def client(
    db_session: AsyncSession,
):
    """
    Асинхронный HTTP клиент для тестирования эндпоинтов.
    Он подменяет реальный UoW на тестовый, чтобы роутеры работали
    внутри нашей изолированной транзакции.
    """

    def override_get_uow():
        return SQLAlchemyUoW(session_factory=lambda: db_session)

    # Подменяем зависимость FastAPI
    # Кусок из conftest.py
