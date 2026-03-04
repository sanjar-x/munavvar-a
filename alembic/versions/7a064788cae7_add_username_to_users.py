"""add_username_to_users

Revision ID: 7a064788cae7
Revises: aec319431748
Create Date: 2026-03-04 20:59:14.127883

"""

from collections.abc import Sequence
from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a064788cae7"
down_revision: Union[str, Sequence[str], None] = "aec319431748"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("users", "full_name", new_column_name="username")


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("users", "username", new_column_name="full_name")
