from __future__ import annotations

import asyncio
from collections.abc import Iterable

import asyncpg
from alembic.config import Config

from alembic import command

HEAD_REVISION = "91852d520f58"
INIT_REVISION = "6c8a17d92a32"
INIT_TABLES = frozenset(
    {
        "products",
        "users",
        "accounts",
        "identities",
        "inventories",
        "inventory_balances",
        "orders",
        "order_items",
        "stock_transfers",
        "transactions",
        "stock_transactions",
        "stock_transfer_items",
    }
)
TRIGGER_NAMES = frozenset(
    {
        "trigger_update_account_balances",
        "trigger_update_inventory_balances",
    }
)


def choose_bootstrap_revision(
    current_versions: set[str],
    existing_tables: set[str],
    existing_triggers: set[str],
) -> str | None:
    if current_versions:
        return None

    if not existing_tables:
        return None

    missing_tables = INIT_TABLES - existing_tables
    if missing_tables:
        missing = ", ".join(sorted(missing_tables))
        raise RuntimeError(
            "Detected a partially initialized schema without Alembic state. "
            f"Missing tables: {missing}"
        )

    if existing_triggers >= TRIGGER_NAMES:
        return HEAD_REVISION

    return INIT_REVISION


async def fetch_existing_versions(conn: asyncpg.Connection) -> set[str]:
    has_version_table = await conn.fetchval(
        "SELECT to_regclass('public.alembic_version') IS NOT NULL"
    )
    if not has_version_table:
        return set()

    rows = await conn.fetch("SELECT version_num FROM alembic_version")
    return {row["version_num"] for row in rows}


async def fetch_existing_tables(
    conn: asyncpg.Connection,
    table_names: Iterable[str],
) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename = ANY($1::text[])
        """,
        list(table_names),
    )
    return {row["tablename"] for row in rows}


async def fetch_existing_triggers(
    conn: asyncpg.Connection,
    trigger_names: Iterable[str],
) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT t.tgname
        FROM pg_trigger AS t
        JOIN pg_class AS c ON c.oid = t.tgrelid
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE NOT t.tgisinternal
          AND n.nspname = 'public'
          AND t.tgname = ANY($1::text[])
        """,
        list(trigger_names),
    )
    return {row["tgname"] for row in rows}


async def bootstrap_alembic_state() -> str | None:
    conn = await asyncpg.connect()
    try:
        current_versions = await fetch_existing_versions(conn)
        existing_tables = await fetch_existing_tables(conn, INIT_TABLES)
        existing_triggers = await fetch_existing_triggers(conn, TRIGGER_NAMES)
    finally:
        await conn.close()

    target_revision = choose_bootstrap_revision(
        current_versions=current_versions,
        existing_tables=existing_tables,
        existing_triggers=existing_triggers,
    )

    if target_revision is None:
        if current_versions:
            versions = ", ".join(sorted(current_versions))
            print(f"Alembic state already present: {versions}")
        else:
            print("Fresh database detected; no Alembic bootstrap needed.")
        return None

    print(
        "Legacy schema detected without Alembic state. "
        f"Stamping revision {target_revision}."
    )
    command.stamp(Config("alembic.ini"), target_revision)
    return target_revision


def main() -> None:
    asyncio.run(bootstrap_alembic_state())


if __name__ == "__main__":
    main()
