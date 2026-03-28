"""triggers

Revision ID: e169f5901a8e
Revises: 6c8a17d92a32
Create Date: 2026-03-28 12:51:40.130632

"""

import re
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e169f5901a8e"
down_revision: str | None = "6c8a17d92a32"
branch_labels: str | None = None
depends_on: str | None = None

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "infrastructure"
    / "database"
    / "scripts"
)


def _split_sql(sql: str) -> list[str]:
    """Split SQL script into individual statements.

    Handles $$ dollar-quoted blocks so the function body
    is not split on internal semicolons.
    """
    # Split on $$ first to isolate dollar-quoted blocks
    parts = sql.split("$$")
    statements: list[str] = []
    buf = ""

    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Inside dollar-quoted block -- keep as-is
            buf += "$$" + part + "$$"
        else:
            # Outside dollar-quoted block -- split on ;
            segments = part.split(";")
            for j, seg in enumerate(segments):
                if j == 0:
                    buf += seg
                else:
                    stmt = buf.strip()
                    if stmt:
                        statements.append(stmt)
                    buf = seg

    final = buf.strip()
    if final:
        statements.append(final)

    return statements


def upgrade() -> None:
    account_sql = (
        SCRIPTS_DIR / "update_account_balances.sql"
    ).read_text(encoding="utf-8")
    for stmt in _split_sql(account_sql):
        op.execute(stmt)

    inventory_sql = (
        SCRIPTS_DIR / "update_inventory_balances.sql"
    ).read_text(encoding="utf-8")
    for stmt in _split_sql(inventory_sql):
        op.execute(stmt)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trigger_update_inventory_balances "
        "ON stock_transactions"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "update_inventory_balances()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trigger_update_account_balances "
        "ON transactions"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "update_account_balances()"
    )
