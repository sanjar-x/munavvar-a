from scripts.bootstrap_alembic import (  # ty:ignore[unresolved-import]
    HEAD_REVISION,
    INIT_REVISION,
    INIT_TABLES,
    LEGACY_REVISION,
    TRIGGER_NAMES,
    BootstrapPlan,
    choose_bootstrap_plan,
)


def test_returns_none_for_fresh_database() -> None:
    assert choose_bootstrap_plan(set(), set(), set()) is None


def test_returns_none_when_alembic_state_already_exists() -> None:
    assert (
        choose_bootstrap_plan({"91852d520f58"}, INIT_TABLES, TRIGGER_NAMES)
        is None
    )


def test_stamps_init_revision_when_tables_exist_without_triggers() -> None:
    assert choose_bootstrap_plan(set(), INIT_TABLES, set()) == BootstrapPlan(
        revision=INIT_REVISION
    )


def test_stamps_head_when_tables_and_triggers_exist() -> None:
    assert choose_bootstrap_plan(
        set(), INIT_TABLES, TRIGGER_NAMES
    ) == BootstrapPlan(revision=HEAD_REVISION)


def test_repairs_legacy_only_version_state_without_triggers() -> None:
    assert choose_bootstrap_plan(
        {LEGACY_REVISION}, INIT_TABLES, set()
    ) == BootstrapPlan(
        revision=INIT_REVISION,
        purge_existing_versions=True,
    )


def test_repairs_legacy_only_version_state_with_triggers() -> None:
    assert choose_bootstrap_plan(
        {LEGACY_REVISION},
        INIT_TABLES,
        TRIGGER_NAMES,
    ) == BootstrapPlan(
        revision=HEAD_REVISION,
        purge_existing_versions=True,
    )


def test_returns_none_for_partially_initialized_schema() -> None:
    existing_tables = INIT_TABLES - {"transactions"}

    assert choose_bootstrap_plan(set(), existing_tables, set()) is None
