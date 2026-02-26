import contextvars
from typing import Final

# Уникальный ключ для переменной
REQUEST_ID_CTX_KEY: Final[str] = "request_id"

# Сама переменная контекста.
# "UNKNOWN" будет отдаваться, если мы попытаемся прочитать лог вне HTTP-запроса
# (например, при старте приложения или в фоновом воркере без ID).
_request_id_ctx_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    REQUEST_ID_CTX_KEY, default="UNKNOWN"
)


def get_request_id() -> str:
    """Получить ID текущего запроса из любого места в коде."""
    return _request_id_ctx_var.get()


def set_request_id(request_id: str) -> contextvars.Token[str]:
    """Установить ID для текущего асинхронного контекста."""
    return _request_id_ctx_var.set(request_id)
