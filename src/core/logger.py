import logging
import sys
from typing import Any, TextIO

import structlog

from src.core.config import settings


def setup_logging() -> None:
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    if settings.ENVIRONMENT == "dev" or settings.DEBUG:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler: logging.StreamHandler[TextIO | Any] = logging.StreamHandler(
        stream=sys.stdout
    )
    handler.setFormatter(fmt=formatter)

    root_logger: logging.Logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(hdlr=handler)
    root_logger.setLevel(level=logging.INFO)

    for _log in ["uvicorn", "uvicorn.error", "fastapi"]:
        logger_instance = logging.getLogger(_log)
        logger_instance.handlers.clear()
        logger_instance.propagate = True

    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = False
