import time
from typing import ClassVar

import structlog
from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger("api.access")


class AccessLoggerMiddleware:
    """
    Высокопроизводительный гибридный ASGI Middleware.
    Сохраняет скорость чистого ASGI, не блокирует стриминг,
    но использует Request для удобного парсинга параметров.
    """

    EXCLUDED_PATHS: ClassVar[set[str]] = {
        "/health",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/favicon.ico",
    }

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        await self.dispatch(request, receive, send)

    async def dispatch(
        self, request: Request, receive: Receive, send: Send
    ) -> None:

        ip = request.headers.get("X-Forwarded-For", "")
        if not ip:
            ip = request.client.host if request.client else "unknown"
        else:
            ip = ip.split(",")[0].strip()

        structlog.contextvars.bind_contextvars(
            ip=ip,
            method=request.method,
            path=request.url.path,
        )

        if request.url.path in self.EXCLUDED_PATHS:
            await self.app(request.scope, receive, send)
            return

        start_time = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)

                process_time_ms = round(
                    (time.perf_counter() - start_time) * 1000, 2
                )

                existing_headers = list(message.get("headers", []))
                existing_headers.append(
                    (b"x-process-time", str(process_time_ms).encode("latin1"))
                )
                message["headers"] = existing_headers

            await send(message)

        try:
            await self.app(request.scope, receive, send_wrapper)

        except Exception:
            status_code = 500
            raise

        finally:
            process_time = round((time.perf_counter() - start_time) * 1000, 2)

            if status_code >= 500:
                log_method = logger.error
            elif status_code >= 400:
                log_method = logger.warning
            else:
                log_method = logger.info

            log_method(
                "HTTP Access Log",
                status=status_code,
                duration=process_time,
            )
