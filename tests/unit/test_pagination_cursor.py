# tests/unit/test_pagination_cursor.py
"""Тесты для cursor-пагинации (FRD §15.2)."""

import uuid
from datetime import UTC, datetime

import pytest

from src.common.pagination import (
    CursorInvalidError,
    CursorPaginationMeta,
    build_cursor_meta,
    decode_cursor,
    encode_cursor,
)


class TestCursorCodec:
    def test_datetime_roundtrip(self):
        ts = datetime(2024, 5, 1, 12, 30, 45, tzinfo=UTC)
        rid = uuid.uuid4()
        token = encode_cursor(ts, rid)
        sort_value, parsed_id = decode_cursor(token)
        assert sort_value == ts
        assert parsed_id == rid

    def test_string_roundtrip(self):
        rid = uuid.uuid4()
        token = encode_cursor("Главный склад", rid)
        sort_value, parsed_id = decode_cursor(token)
        assert sort_value == "Главный склад"
        assert parsed_id == rid

    def test_int_roundtrip(self):
        rid = uuid.uuid4()
        token = encode_cursor(42, rid)
        sort_value, parsed_id = decode_cursor(token)
        assert sort_value == 42
        assert parsed_id == rid

    def test_token_is_url_safe(self):
        token = encode_cursor("a", uuid.uuid4())
        # base64url использует только [A-Za-z0-9_-] (без padding)
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_invalid_base64_raises(self):
        with pytest.raises(CursorInvalidError):
            decode_cursor("!!!not-base64!!!")

    def test_invalid_payload_raises(self):
        import base64

        bad = base64.urlsafe_b64encode(b"plain text").decode().rstrip("=")
        with pytest.raises(CursorInvalidError):
            decode_cursor(bad)

    def test_invalid_uuid_raises(self):
        import base64

        # Format is v1|<kind>|<uuid>|<sort_value>; corrupt the uuid slot.
        bad = (
            base64.urlsafe_b64encode(b"v1|s|not-a-uuid|name")
            .decode()
            .rstrip("=")
        )
        with pytest.raises(CursorInvalidError):
            decode_cursor(bad)

    def test_unsupported_version_raises(self):
        import base64

        rid = uuid.uuid4()
        bad = (
            base64.urlsafe_b64encode(f"v9|s|{rid}|name".encode())
            .decode()
            .rstrip("=")
        )
        with pytest.raises(CursorInvalidError):
            decode_cursor(bad)

    def test_unknown_kind_raises(self):
        import base64

        rid = uuid.uuid4()
        bad = (
            base64.urlsafe_b64encode(f"v1|x|{rid}|val".encode())
            .decode()
            .rstrip("=")
        )
        with pytest.raises(CursorInvalidError):
            decode_cursor(bad)

    def test_empty_token_raises(self):
        with pytest.raises(CursorInvalidError):
            decode_cursor("")

    def test_pipe_in_sort_value_roundtrip(self):
        """Имя склада может содержать `|` — токен не должен ломаться."""
        rid = uuid.uuid4()
        weird = "Цех|3|тестовый"
        token = encode_cursor(weird, rid)
        sort_value, parsed_id = decode_cursor(token)
        assert sort_value == weird
        assert parsed_id == rid

    def test_cross_type_cursor_distinguishable(self):
        """Service-уровень должен отвергать cursor чужого типа.

        Codec сам по себе только различает типы через `kind` —
        проверка совместимости с конкретной сортировкой делается в
        сервисах. Тест документирует, что `kind` сохраняется при
        roundtrip и доступен через `isinstance`.
        """
        rid = uuid.uuid4()
        dt_token = encode_cursor(datetime(2024, 1, 1, tzinfo=UTC), rid)
        str_token = encode_cursor("name", rid)
        dt_value, _ = decode_cursor(dt_token)
        str_value, _ = decode_cursor(str_token)
        assert isinstance(dt_value, datetime)
        assert isinstance(str_value, str)
        assert not isinstance(str_value, datetime)


class _Row:
    """Лёгкий стенд для строк, проходящих через ``build_cursor_meta``."""

    def __init__(self, name: str, row_id: uuid.UUID | None = None):
        self.name = name
        self.id = row_id or uuid.uuid4()


class TestBuildCursorMeta:
    def test_no_more_pages(self):
        rows = [_Row("a"), _Row("b")]
        page, meta = build_cursor_meta(
            rows, size=5, sort_value_of=lambda r: r.name
        )
        assert page == rows
        assert isinstance(meta, CursorPaginationMeta)
        assert meta.size == 5
        assert meta.has_more is False
        assert meta.next_cursor is None

    def test_has_more_emits_cursor(self):
        rows = [_Row("a"), _Row("b"), _Row("c")]
        page, meta = build_cursor_meta(
            rows, size=2, sort_value_of=lambda r: r.name
        )
        assert len(page) == 2
        assert meta.has_more is True
        assert meta.next_cursor is not None
        sort_value, parsed_id = decode_cursor(meta.next_cursor)
        # Next cursor must point at the last row of the page, not overflow
        assert sort_value == "b"
        assert parsed_id == rows[1].id

    def test_empty_rows(self):
        page, meta = build_cursor_meta(
            [], size=10, sort_value_of=lambda r: r.name
        )
        assert page == []
        assert meta.has_more is False
        assert meta.next_cursor is None

    def test_exact_size_no_overflow(self):
        rows = [_Row("a"), _Row("b")]
        page, meta = build_cursor_meta(
            rows, size=2, sort_value_of=lambda r: r.name
        )
        # size=2 + we got 2 → no overflow → no next cursor
        assert page == rows
        assert meta.has_more is False
        assert meta.next_cursor is None
