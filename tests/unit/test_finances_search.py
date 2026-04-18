# tests/unit/test_finances_search.py
import pytest

from src.modules.finances.exceptions import (
    SearchTooLongError,
    SearchTooShortError,
    SearchUuidNotAllowedError,
)
from src.modules.finances.search import ilike_pattern, normalize_q


class TestNormalizeQ:
    def test_none_returns_none(self):
        assert normalize_q(None) is None

    def test_empty_whitespace_returns_none(self):
        assert normalize_q("   ") is None
        assert normalize_q("") is None

    def test_too_short_raises(self):
        with pytest.raises(SearchTooShortError):
            normalize_q("a")

    def test_too_long_raises(self):
        with pytest.raises(SearchTooLongError):
            normalize_q("a" * 101)

    def test_trim(self):
        assert normalize_q("  hello  ") == "hello"

    def test_normal_value(self):
        assert normalize_q("Ivan Petrov") == "Ivan Petrov"

    def test_uuid_rejected(self):
        with pytest.raises(SearchUuidNotAllowedError):
            normalize_q("01976c55-b6a2-7f1a-86d5-0123456789ab")

    def test_uppercase_uuid_rejected(self):
        with pytest.raises(SearchUuidNotAllowedError):
            normalize_q("01976C55-B6A2-7F1A-86D5-0123456789AB")

    def test_long_hex_rejected(self):
        with pytest.raises(SearchUuidNotAllowedError):
            normalize_q("0123456789abcdef")

    def test_short_hex_allowed(self):
        # 8 hex digits — это валидный order_short_id-поиск в v1
        # не запрещаем, пусть ищет как обычный текст
        assert normalize_q("abcd1234") == "abcd1234"


class TestIlikePattern:
    def test_basic(self):
        assert ilike_pattern("hello") == "%hello%"

    def test_escape_percent(self):
        assert ilike_pattern("50%") == r"%50\%%"

    def test_escape_underscore(self):
        assert ilike_pattern("a_b") == r"%a\_b%"

    def test_escape_backslash(self):
        assert ilike_pattern("a\\b") == r"%a\\b%"
