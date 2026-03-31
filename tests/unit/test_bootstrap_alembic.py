from scripts.bootstrap_alembic import (
    HEAD_REVISION,
    INIT_REVISION,
    INIT_TABLES,
    TRIGGER_NAMES,
    choose_bootstrap_revision,
)


def test_returns_none_for_fresh_database() -> None:
    assert choose_bootstrap_revision(set(), set(), set()) is None


def test_returns_none_when_alembic_state_already_exists() -> None:
    assert (
        choose_bootstrap_revision({"91852d520f58"}, INIT_TABLES, TRIGGER_NAMES)
        is None
    )


def test_stamps_init_revision_when_tables_exist_without_triggers() -> None:
    assert (
        choose_bootstrap_revision(set(), INIT_TABLES, set()) == INIT_REVISION
    )


def test_stamps_head_when_tables_and_triggers_exist() -> None:
    assert (
        choose_bootstrap_revision(set(), INIT_TABLES, TRIGGER_NAMES)
        == HEAD_REVISION
    )


def test_raises_for_partially_initialized_schema() -> None:
    existing_tables = INIT_TABLES - {"transactions"}

    try:
        choose_bootstrap_revision(set(), existing_tables, set())
    except RuntimeError as exc:
        assert "Missing tables: transactions" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for partial schema")
