import logging
import sys
from typing import Any

import structlog

from src.core.config import settings


def setup_logging() -> None:
    """
    Настраивает Structlog для вывода структурированных логов.
    Перехватывает стандартные логи FastAPI, Uvicorn и SQLAlchemy.
    """
    # 1. ОБЩИЕ ПРОЦЕССОРЫ (Выполняются для всех логов)
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # 2. НАСТРОЙКА ЯДРА STRUCTLOG
    structlog.configure(
        processors=shared_processors
        + [
            # Заворачивает словарь для передачи в стандартный logging.
            # ВАЖНО: Должен быть строго последним в этом списке!
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 3. НАСТРОЙКА РЕНДЕРИНГА
    if settings.ENVIRONMENT == "local" or settings.DEBUG:
        # Для локальной разработки - красивые цветные логи в консоли
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # Для продакшена - строгий JSON для DataDog / ELK / Grafana
        renderer = structlog.processors.JSONRenderer()

    # 4. СВЯЗКА СО СТАНДАРТНЫМ LOGGING
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            # Очищает служебные метаданные.
            # ВАЖНО: Должен быть строго первым в этом списке!
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # 5. ПЕРЕХВАТ ЛОГОВ UVICORN / FASTAPI
    for _log in ["uvicorn", "uvicorn.error", "fastapi"]:
        logger_instance = logging.getLogger(_log)
        logger_instance.handlers.clear()
        logger_instance.propagate = True

    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = False
