"""triggers

Revision ID: 014cf8e85d99
Revises: 109a87243062
Create Date: 2026-04-16 00:01:28.107734

"""

from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014cf8e85d99"
down_revision: str | Sequence[str] | None = "109a87243062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQL-файлы с PL/pgSQL функциями и триггерами
_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "infrastructure"
    / "database"
    / "scripts"
)


def _split_sql(raw: str) -> list[str]:
    """Split multi-statement SQL respecting $$ dollar-quoting.

    asyncpg cannot execute multiple statements in one prepared
    statement, so we must split CREATE FUNCTION / DROP TRIGGER /
    CREATE TRIGGER into separate calls.
    """
    stmts: list[str] = []
    buf: list[str] = []
    inside_dollar = False

    for line in raw.splitlines():
        buf.append(line)
        # Odd number of $$ on a line toggles the flag
        if line.count("$$") % 2 == 1:
            inside_dollar = not inside_dollar
        # Statement boundary: line ends with `;` outside $$
        if not inside_dollar and line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []

    # Leftover (shouldn't happen with well-formed SQL)
    tail = "\n".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def _exec_sql_file(name: str) -> None:
    """Read a .sql file and execute each statement separately."""
    raw = (_SCRIPTS / name).read_text()
    for stmt in _split_sql(raw):
        op.execute(text(stmt))


# ---------------------------------------------------------------------------
# Downgrade SQL (single statements — safe to inline)
# ---------------------------------------------------------------------------
_DROP_ACCOUNT_TRIGGER = (
    "DROP TRIGGER IF EXISTS trigger_update_account_balances ON transactions"
)
_DROP_INVENTORY_TRIGGER = (
    "DROP TRIGGER IF EXISTS"
    " trigger_update_inventory_balances"
    " ON stock_transactions"
)
_DROP_ACCOUNT_FN = "DROP FUNCTION IF EXISTS update_account_balances()"
_DROP_INVENTORY_FN = "DROP FUNCTION IF EXISTS update_inventory_balances()"


def upgrade() -> None:
    _exec_sql_file("update_account_balances.sql")
    _exec_sql_file("update_inventory_balances.sql")


def downgrade() -> None:
    op.execute(text(_DROP_INVENTORY_TRIGGER))
    op.execute(text(_DROP_INVENTORY_FN))
    op.execute(text(_DROP_ACCOUNT_TRIGGER))
    op.execute(text(_DROP_ACCOUNT_FN))
