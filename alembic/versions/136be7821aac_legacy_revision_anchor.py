"""legacy revision anchor

Revision ID: 136be7821aac
Revises:
Create Date: 2026-03-31

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "136be7821aac"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op anchor for legacy databases stamped with a removed revision."""


def downgrade() -> None:
    """No-op downgrade for the legacy anchor."""
