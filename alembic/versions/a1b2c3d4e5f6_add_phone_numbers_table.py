"""add phone_numbers table

Revision ID: a1b2c3d4e5f6
Revises: db4934c22d35
Create Date: 2026-05-01 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "db4934c22d35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "phone_numbers",
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "phone",
            sa.String(length=20),
            nullable=False,
            comment="Дополнительный номер телефона",
        ),
        sa.Column(
            "label",
            sa.String(length=50),
            nullable=True,
            comment="Метка: Личный, Рабочий и т.д.",
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone", name="uq_phone_numbers_phone"),
    )
    op.create_index(
        "ix_phone_numbers_user_id",
        "phone_numbers",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_phone_numbers_user_id",
        table_name="phone_numbers",
    )
    op.drop_table("phone_numbers")
