"""Free-text search helper для inventory-эндпоинтов.

См. `research/INVENTORY_SEARCH_FILTERS_FRD.md` §4.2, §6.2.

Контракт:
- `q` длиной 2..100 (после trim), обязательно валидируется.
- UUID и его фрагменты (hex ≥ 8 подряд) запрещены: искать по id
  нужно через структурные фильтры (`inventory_id`, `transfer_id`, ...).
- Канал телефона: строка из ≥ 4 цифр (после удаления `+`, `-`, ` `, `(`, `)`).
- Канал целого: чистое число до 9 цифр (если не телефон).
- Возвращает нормализованную строку (trim) или None.
"""

from __future__ import annotations

import re

from src.common.search import ilike_pattern as _common_ilike_pattern
from src.modules.inventory.exceptions import (
    SearchTooLongError,
    SearchTooShortError,
    SearchUuidNotAllowedError,
)

__all__ = [
    "MAX_LEN",
    "MIN_LEN",
    "extract_phone_digits",
    "ilike_pattern",
    "is_phone_like",
    "normalize_q",
    "try_parse_int",
]

MIN_LEN = 2
MAX_LEN = 100

# Канонический UUID 8-4-4-4-12.
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
# Любая hex-последовательность ≥ 8 подряд (после удаления дефисов и
# 0x-префикса) — отсекаем фрагменты UUID, которыми пользователь
# мог бы пытаться искать «по короткому id».
_LONG_HEX_RE = re.compile(r"^[0-9a-f]{8,}$", re.IGNORECASE)
_PHONE_CHARS_RE = re.compile(r"[\s+\-()]+")
_DIGITS_ONLY_RE = re.compile(r"^[0-9]{1,9}$")


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

    # Убираем дефисы и опциональный 0x-префикс перед hex-проверкой.
    compact = q.replace("-", "")
    if compact.lower().startswith("0x"):
        compact = compact[2:]
    if _UUID_RE.match(q) or _LONG_HEX_RE.match(compact):
        raise SearchUuidNotAllowedError()
    return q


def ilike_pattern(q: str) -> str:
    """Безопасный ILIKE-шаблон с экранированием `\\`/`%`/`_`."""
    return _common_ilike_pattern(q)


def extract_phone_digits(q: str) -> str:
    """Снять разделители телефона и оставить только цифры."""
    return _PHONE_CHARS_RE.sub("", q)


def is_phone_like(q: str) -> bool:
    """Похоже ли `q` на ввод телефона: ≥ 4 цифр после очистки."""
    digits = extract_phone_digits(q)
    return digits.isdigit() and len(digits) >= 4


def try_parse_int(q: str) -> int | None:
    """Если `q` — целое до 9 цифр, вернуть int, иначе None."""
    if _DIGITS_ONLY_RE.match(q):
        return int(q)
    return None
