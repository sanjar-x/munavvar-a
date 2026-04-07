"""convert sale_type to native enum

Revision ID: 9a9cbfcda833
Revises: b8e855f8adba
Create Date: 2026-04-01 12:07:57.791776

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a9cbfcda833"
down_revision: str | Sequence[str] | None = "b8e855f8adba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    sale_type_enum = sa.Enum(
        "delivery",
        "warehouse_pickup",
        name="sale_type_enum",
    )
    sale_type_enum.create(op.get_bind(), checkfirst=True)

    # Drop varchar default before type change — PG can't auto-cast it
    op.alter_column(
        "orders",
        "sale_type",
        existing_type=sa.VARCHAR(length=30),
        server_default=None,
    )

    op.alter_column(
        "orders",
        "sale_type",
        existing_type=sa.VARCHAR(length=30),
        type_=sale_type_enum,
        existing_nullable=False,
        postgresql_using="sale_type::sale_type_enum",
    )

    # Re-add default as enum value
    op.alter_column(
        "orders",
        "sale_type",
        existing_type=sale_type_enum,
        server_default="delivery",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "orders",
        "sale_type",
        existing_type=sa.Enum(
            "delivery",
            "warehouse_pickup",
            name="sale_type_enum",
        ),
        type_=sa.VARCHAR(length=30),
        existing_comment="Тип продажи: delivery (доставка) или warehouse_pickup (самовывоз)",
        existing_nullable=False,
        existing_server_default=sa.text("'delivery'::character varying"),
        postgresql_using="sale_type::varchar",
    )

    sa.Enum(name="sale_type_enum").drop(op.get_bind(), checkfirst=True)
