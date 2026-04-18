# tests/unit/test_inventory_search.py
import pytest

from src.modules.inventory.exceptions import (
    SearchTooLongError,
    SearchTooShortError,
    SearchUuidNotAllowedError,
)
from src.modules.inventory.search import (
    extract_phone_digits,
    ilike_pattern,
    is_phone_like,
    normalize_q,
    try_parse_int,
)


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
        assert normalize_q("Bonaqua 19L") == "Bonaqua 19L"

    def test_uuid_rejected(self):
        with pytest.raises(SearchUuidNotAllowedError):
            normalize_q("01976c55-b6a2-7f1a-86d5-0123456789ab")

    def test_uppercase_uuid_rejected(self):
        with pytest.raises(SearchUuidNotAllowedError):
            normalize_q("01976C55-B6A2-7F1A-86D5-0123456789AB")

    def test_long_hex_rejected(self):
        with pytest.raises(SearchUuidNotAllowedError):
            normalize_q("0123456789abcdef")

    def test_short_hex_rejected(self):
        # FRD §4.6: даже 8-значный hex считается фрагментом UUID.
        with pytest.raises(SearchUuidNotAllowedError):
            normalize_q("abcd1234")

    def test_seven_hex_allowed(self):
        # 7 hex символов уже не считается UUID-фрагментом.
        assert normalize_q("abcd123") == "abcd123"

    def test_0x_prefix_rejected(self):
        with pytest.raises(SearchUuidNotAllowedError):
            normalize_q("0x12345678")


class TestIlikePattern:
    def test_basic(self):
        assert ilike_pattern("hello") == "%hello%"

    def test_escape_percent(self):
        assert ilike_pattern("50%") == r"%50\%%"

    def test_escape_underscore(self):
        assert ilike_pattern("a_b") == r"%a\_b%"


class TestPhone:
    def test_phone_digits_extracted(self):
        assert extract_phone_digits("+998 (90) 123-45-67") == "998901234567"

    def test_is_phone_like_true(self):
        assert is_phone_like("+998 90 123 45 67")
        assert is_phone_like("1234")

    def test_is_phone_like_false(self):
        assert not is_phone_like("Bonaqua")
        assert not is_phone_like("123")  # < 4 цифр


class TestParseInt:
    def test_int(self):
        assert try_parse_int("42") == 42

    def test_not_int(self):
        assert try_parse_int("Bonaqua") is None
        assert try_parse_int("12.5") is None

    def test_too_long(self):
        # > 9 цифр → не int (это телефон/счёт)
        assert try_parse_int("1234567890") is None
