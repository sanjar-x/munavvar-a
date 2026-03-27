import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from structlog.stdlib import BoundLogger

from src.core.exceptions import AppException

logger: BoundLogger = structlog.get_logger("api.exceptions")


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Перехватывает наши кастомные бизнес-ошибки."""
    # Логируем бизнес-ошибки
    log_method = logger.error if exc.status_code >= 500 else logger.warning
    log_method(
        "Бизнес-ошибка",
        error_code=exc.error_code,
        status_code=exc.status_code,
        message=exc.message,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details or {},
            }
        },
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Переопределяет стандартную ошибку 422 от FastAPI (Pydantic)."""
    # Senior-парсинг: склеиваем вложенные пути точкой (например: items.0.price)
    # и сохраняем тип ошибки (type) для удобной обработки на фронтенде.
    details = [
        {
            "field": ".".join(map(str, error["loc"])),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]

    logger.warning("Ошибка валидации схемы (422)", validation_errors=details)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Ошибка валидации входных данных.",
                "details": details,
            }
        },
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """
    Перехватывает стандартные ошибки HTTP
    Гарантирует, что фронтенд всегда получит наш стандартный JSON-формат.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_ERROR_{exc.status_code}",
                "message": str(exc.detail),
                "details": {},
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Перехватывает все непредвиденные системные ошибки (Crash/Panic)."""
    logger.error(
        "Необработанное системное исключение сервера (500)",
        exc_info=exc,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Внутренняя ошибка сервера.",
                "details": {},
            }
        },
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Регистрирует все глобальные обработчики в приложении."""
    # Обрати внимание: типы совпали, линтер больше не требует ty:ignore
    app.add_exception_handler(AppException, app_exception_handler)  # ty:ignore[invalid-argument-type]
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,  # ty:ignore[invalid-argument-type]
    )
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # ty:ignore[invalid-argument-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
