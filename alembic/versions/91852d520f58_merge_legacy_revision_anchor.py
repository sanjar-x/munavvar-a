"""merge legacy revision anchor

Revision ID: 91852d520f58
Revises: e169f5901a8e, 136be7821aac
Create Date: 2026-03-31

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "91852d520f58"
down_revision: str | Sequence[str] | None = (
    "e169f5901a8e",
    "136be7821aac",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge the current migration chain with a legacy stamped revision."""


def downgrade() -> None:
    """No-op downgrade for the merge revision."""
