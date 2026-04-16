"""add_expense_and_admin_account_types

Revision ID: 1d156127d709
Revises: a1b2c3d4e5f6
Create Date: 2026-04-16 14:19:22.553363

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1d156127d709"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add 'expense' and 'admin' values to account_type_enum."""
    op.execute("ALTER TYPE account_type_enum ADD VALUE 'expense'")
    op.execute("ALTER TYPE account_type_enum ADD VALUE 'admin'")


def downgrade() -> None:
    """PG enums do not support DROP VALUE; no-op."""
