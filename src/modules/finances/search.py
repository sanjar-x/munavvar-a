# src/modules/finances/search.py
"""Free-text search helper для финансовых эндпоинтов.

См. `research/FINANCES_SEARCH_FILTERS_FRD.md` §4.2.

Контракт:
- `q` длиной 2..100, обязательно валидируется.
- UUID / длинные hex-строки запрещены (искать по id надо явно через
  `order_id`, `account_id`, ...).
- Значение нормализуется (trim, lower), возвращается шаблон для ILIKE.
"""

from __future__ import annotations

import re

from src.common.search import ilike_pattern as _common_ilike_pattern
from src.modules.finances.exceptions import (
    SearchTooLongError,
    SearchTooShortError,
    SearchUuidNotAllowedError,
)

__all__ = ["normalize_q", "ilike_pattern"]

MIN_LEN = 2
MAX_LEN = 100

# Дефисованный UUID — 8-4-4-4-12 hex. Также запрещаем любые
# hex-строки ≥ 9 символов: этого достаточно, чтобы отсечь
# пользовательский ввод "чистого" id.
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_LONG_HEX_RE = re.compile(r"^[0-9a-f]{9,}$", re.IGNORECASE)


def normalize_q(raw: str | None) -> str | None:
    """Вернуть нормализованное `q` (trimmed) или None если пусто.

    Валидирует длину и отсутствие UUID. При нарушении — выбрасывает
    соответствующее AppException.
    """
    if raw is None:
        return None
    q = raw.strip()
    if not q:
        return None
    if len(q) < MIN_LEN:
        raise SearchTooShortError(length=len(q))
    if len(q) > MAX_LEN:
        raise SearchTooLongError(length=len(q))
    compact = q.replace("-", "")
    if _UUID_RE.match(q) or _LONG_HEX_RE.match(compact):
        raise SearchUuidNotAllowedError()
    return q


def ilike_pattern(q: str) -> str:
    """Безопасный ILIKE-шаблон: экранируем `%`/`_` во вводе.

    Реэкспорт из `src.common.search` — сохраняется для совместимости
    с тестами и прежним публичным API модуля финансов.
    """
    return _common_ilike_pattern(q)
