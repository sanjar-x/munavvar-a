"""Общие утилиты безопасного free-text search.

Используется доменными модулями (`finances`, `inventory`, ...)
для единообразного экранирования LIKE/ILIKE-шаблонов.
"""

from __future__ import annotations


def ilike_pattern(q: str) -> str:
    """Безопасный ILIKE-шаблон: экранируем `\\`, `%` и `_` во вводе.

    Порядок важен: сначала backslash, иначе повторно экранируем
    уже экранированные `%`/`_`.
    """
    escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"
