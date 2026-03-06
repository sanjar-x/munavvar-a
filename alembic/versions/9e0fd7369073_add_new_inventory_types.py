"""add new inventory types

Revision ID: 9e0fd7369073
Revises: 7a064788cae7
Create Date: 2026-03-06 12:23:33.553484

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e0fd7369073"
down_revision: Union[str, Sequence[str], None] = "7a064788cae7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE inventory_type_enum ADD VALUE IF NOT EXISTS 'CLIENT'")
    op.execute("ALTER TYPE inventory_type_enum ADD VALUE IF NOT EXISTS 'COURIER'")
    op.execute("ALTER TYPE inventory_type_enum ADD VALUE IF NOT EXISTS 'VIRTUAL_LOSS'")
    op.execute(
        "ALTER TYPE inventory_type_enum ADD VALUE IF NOT EXISTS 'VIRTUAL_VENDOR'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
