"""Cursor-pagination helpers (FRD §4.4, §15.2).

Курсор — opaque base64url-токен, кодирующий пару
``(sort_value, id)`` последней строки предыдущей страницы.
Используется для бесконечной прокрутки и стабильного экспорта
журналов append-only данных (например, `stock_transactions`).

Формат токена: ``base64url("v1|<kind>|<uuid>|<sort_value>")``
где ``kind ∈ {dt, s, i}`` — тип значения сортировки
(datetime/строка/int). UUID идёт перед sort_value, чтобы
sort_value мог свободно содержать любые символы (включая ``|``)
без поломки парсера.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from src.core.exceptions import UnprocessableEntityError


class CursorInvalidError(UnprocessableEntityError):
    """Курсор пагинации повреждён или несовместим со схемой."""

    def __init__(self) -> None:
        super().__init__(
            message="Курсор пагинации недействителен или повреждён",
            error_code="CURSOR_INVALID",
            details={},
        )


class CursorPaginationMeta(BaseModel):
    """Мета-информация для cursor-пагинированных ответов."""

    mode: Literal["cursor"] = "cursor"
    size: int
    has_more: bool
    next_cursor: str | None = None


SortValue = datetime | str | int


def encode_cursor(sort_value: SortValue, row_id: uuid.UUID) -> str:
    """Закодировать `(sort_value, id)` в opaque base64url-строку."""
    if isinstance(sort_value, datetime):
        kind = "dt"
        sv = sort_value.isoformat()
    elif isinstance(sort_value, bool):
        # bool is subclass of int; treat as int explicitly
        kind = "i"
        sv = str(int(sort_value))
    elif isinstance(sort_value, int):
        kind = "i"
        sv = str(sort_value)
    else:
        kind = "s"
        sv = str(sort_value)
    raw = f"v1|{kind}|{row_id}|{sv}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(token: str) -> tuple[SortValue, uuid.UUID]:
    """Декодировать токен. Бросает ``CursorInvalidError`` при ошибке."""
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode("utf-8")
        # maxsplit=3 → последний кусок содержит весь sort_value
        # (даже если в нём есть '|'), а row_id фиксированной длины.
        parts = raw.split("|", 3)
        if len(parts) != 4:
            raise ValueError("malformed cursor payload")
        version, kind, raw_id, sv = parts
        if version != "v1":
            raise ValueError(f"unsupported cursor version: {version}")
        row_id = uuid.UUID(raw_id)
        value: SortValue
        if kind == "dt":
            value = datetime.fromisoformat(sv)
        elif kind == "i":
            value = int(sv)
        elif kind == "s":
            value = sv
        else:
            raise ValueError(f"unknown cursor kind: {kind}")
    except (
        ValueError,
        binascii.Error,
        UnicodeDecodeError,
    ) as exc:
        raise CursorInvalidError() from exc
    return value, row_id


def build_cursor_meta(
    rows: list,
    size: int,
    sort_value_of,
) -> tuple[list, CursorPaginationMeta]:
    """Срезать перебор ``size+1`` строк и построить мета.

    Args:
        rows: результат запроса, вытащенный с ``limit=size+1``.
        size: запрошенный размер страницы.
        sort_value_of: callable ``(row) -> SortValue`` для извлечения
            ключа сортировки из последней строки.
    """
    has_more = len(rows) > size
    page_rows = rows[:size]
    next_cursor: str | None = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = encode_cursor(sort_value_of(last), last.id)
    return page_rows, CursorPaginationMeta(
        size=size,
        has_more=has_more,
        next_cursor=next_cursor,
    )
