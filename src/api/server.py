# src/api/server.py

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from structlog.stdlib import BoundLogger

from src.api.exceptions.handlers import setup_exception_handlers
from src.api.middlewares.logger import AccessLoggerMiddleware
from src.api.middlewares.request_id import RequestIDMiddleware
from src.api.v1 import api_v1_router
from src.core.config import settings
from src.core.logger import setup_logging

setup_logging()

logger: BoundLogger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Запуск Enterprise API",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
    )
    # Инициализация БД и Redis...
    yield
    logger.info("Остановка Enterprise API. Очистка ресурсов...")
    # Закрытие пулов...


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        docs_url=f"{settings.API_V1_STR}/docs"
        if settings.ENVIRONMENT != "prod"
        else None,
        redoc_url=None,
        openapi_url=f"{settings.API_V1_STR}/openapi.json"
        if settings.ENVIRONMENT != "prod"
        else None,
        lifespan=lifespan,
    )

    # 1. CORS (Слой 3 - самый внутренний)
    if settings.CORS_ORIGINS:
        if settings.ENVIRONMENT == "prod" and "*" in settings.CORS_ORIGINS:
            raise ValueError(
                "Wildcard CORS ('*') не разрешён в продакшене. "
                "Укажите конкретные origins в CORS_ORIGINS."
            )
        app.add_middleware(
            CORSMiddleware,  # ty:ignore[invalid-argument-type]
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 2. Логирование (Слой 2 - посередине)
    # Ждет, пока Request ID сгенерируется, затем замеряет время запроса
    app.add_middleware(AccessLoggerMiddleware)  # ty:ignore[invalid-argument-type]

    # 3. Request ID (Слой 1 - самый внешний)
    # Выполнится ПЕРВЫМ: очистит лог-контекст и создаст ID
    app.add_middleware(RequestIDMiddleware)  # ty:ignore[invalid-argument-type]

    setup_exception_handlers(app)
    app.include_router(router=api_v1_router, prefix=settings.API_V1_STR)

    @app.get("/health", tags=["System"])
    async def health_check():
        from sqlalchemy.exc import SQLAlchemyError

        from src.infrastructure.database.session import async_session_maker

        try:
            async with async_session_maker() as session:
                await session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            from fastapi import Response

            return Response(
                content='{"status": "db_unavailable"}',
                status_code=503,
                media_type="application/json",
            )
        return {"status": "ok"}

    return app
