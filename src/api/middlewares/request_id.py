import uuid

import structlog
from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.context import set_request_id


class RequestIDMiddleware:
    """
    Высокопроизводительный ASGI Middleware для внедрения Request ID.
    Является точкой входа (Outermost Middleware), поэтому отвечает за очистку.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. ОЧИСТКА КОНТЕКСТА: Делаем это здесь, на самом верхнем уровне!
        structlog.contextvars.clear_contextvars()

        # Оптимизация: передаем scope, так как нам нужны только заголовк.
        # Это гарантирует, что мы случайно не «проглотим» receive stream.
        request = Request(scope)

        # 2. Получаем ID от балансировщика или генерируем новый
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # 3. Сохраняем в кастомный контекст проекта
        set_request_id(request_id)

        # 4. Биндим Request ID в structlog.
        # Теперь он доживет до самого конца запроса.
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # 5. Перехватываем ответ для добавления заголовка клиенту
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing_headers = list(message.get("headers", []))
                existing_headers.append(
                    (b"x-request-id", request_id.encode("latin1"))
                )
                message["headers"] = existing_headers

            await send(message)

        # 6. Передаем управление дальше по цепочке
        await self.app(request.scope, receive, send_wrapper)
