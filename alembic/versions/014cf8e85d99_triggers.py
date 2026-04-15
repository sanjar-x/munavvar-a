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


def _read_sql(name: str) -> str:
    return (_SCRIPTS / name).read_text()


# ---------------------------------------------------------------------------
# Downgrade SQL
# ---------------------------------------------------------------------------
DROP_ACCOUNT_BALANCES_TRIGGER = """
DROP TRIGGER IF EXISTS trigger_update_account_balances
    ON transactions;
"""

DROP_INVENTORY_BALANCES_TRIGGER = """
DROP TRIGGER IF EXISTS trigger_update_inventory_balances
    ON stock_transactions;
"""

DROP_ACCOUNT_FUNCTION = """
DROP FUNCTION IF EXISTS update_account_balances();
"""

DROP_INVENTORY_FUNCTION = """
DROP FUNCTION IF EXISTS update_inventory_balances();
"""


def upgrade() -> None:
    # Читаем SQL из source-файлов (содержат $$-кавычки,
    # которые asyncpg ломает если вставить как строку).
    # text() говорит SQLAlchemy не парсить параметры.
    account_sql = _read_sql("update_account_balances.sql")
    inventory_sql = _read_sql("update_inventory_balances.sql")

    op.execute(text(account_sql))
    op.execute(text(inventory_sql))


def downgrade() -> None:
    op.execute(text(DROP_INVENTORY_BALANCES_TRIGGER))
    op.execute(text(DROP_INVENTORY_FUNCTION))
    op.execute(text(DROP_ACCOUNT_BALANCES_TRIGGER))
    op.execute(text(DROP_ACCOUNT_FUNCTION))
