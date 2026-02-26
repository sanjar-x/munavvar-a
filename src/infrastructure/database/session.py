# src/infrastructure/database/session.py
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings

logger: Any = structlog.get_logger(__name__)

# =============================================================================
# 1. СОЗДАНИЕ ДВИЖКА (ENGINE) И НАСТРОЙКА CONNECTION POOL
# =============================================================================
# Движок — это глобальный объект. Он создается один раз при старте приложения.
engine: AsyncEngine = create_async_engine(
    url=settings.database_url,
    # Включает вывод всех SQL-запросов в консоль, если мы в режиме DEBUG (dev).
    echo=settings.DEBUG,
    # --- Настройки пула соединений (Connection Pooling) ---
    # pool_size: Сколько постоянных соединений держать открытыми.
    pool_size=15,
    # max_overflow: Сколько дополнительных соединений можно открыть.
    max_overflow=10,
    # pool_timeout: Сколько запрос будет ждать свободного соединения из пула,
    # прежде чем выбросить TimeoutError.
    pool_timeout=30,
    # pool_pre_ping: ПЕССИМИСТИЧНАЯ ПРОВЕРКА.
    # Алхимия отправлятет `SELECT 1` перед выдачей соединения из пула.
    # Это спасает приложение от падений, если PostgreSQL перезагрузился
    # или Docker оборвал сетевое соединение.
    pool_pre_ping=True,
)


# =============================================================================
# 2. ФАБРИКА СЕССИЙ (SESSION MAKER)
# =============================================================================
# Создает новые экземпляры сессий (транзакций) для каждого HTTP-запроса.
async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    # КРИТИЧЕСКИ ВАЖНО ДЛЯ АСИНХРОННОЙ АЛХИМИИ!
    # Если оставить True (по умолчанию), то после session.commit()
    # выбросит страшную ошибку MissingGreenletError.
    expire_on_commit=False,
)


# =============================================================================
# 3. ФУНКЦИИ ЖИЗНЕННОГО ЦИКЛА (LIFESPAN & DEPENDENCY)
# =============================================================================


async def close_db_connection() -> None:
    """
    Корректно закрывает все соединения с базой данных.
    Вызывается при остановке FastAPI (Ctrl+C / SIGTERM).
    """
    logger.info("Закрытие пула соединений с PostgreSQL...")
    await engine.dispose()
    logger.info("Соединения с БД успешно закрыты.")


async def get_session():
    """
    Dependency (Зависимость) для FastAPI.
    Выдает новую асинхронную сессию для каждого HTTP-запроса
    и гарантированно закрывает её после ответа.
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            # Возвращаем соединение обратно в пул.
            await session.close()
