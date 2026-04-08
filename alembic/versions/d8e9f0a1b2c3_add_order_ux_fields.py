# alembic/versions/d8e9f0a1b2c3_add_order_ux_fields.py
"""add order ux fields

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2025-07-08

Adds:
- orders.cancellation_reason (VARCHAR 500)
- orders.notes (VARCHAR 500)
- order_status_logs table (audit trail)
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: str = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Reuse the existing order_status enum type from init migration
order_status_enum = sa.Enum(
    "new",
    "assigned",
    "in_transit",
    "arrived",
    "delivered",
    "cancelled",
    "pickup_ready",
    "pickup_completed",
    name="order_status_enum",
    create_type=False,
)


def upgrade() -> None:
    # --- Orders: new nullable text columns ---
    op.add_column(
        "orders",
        sa.Column(
            "cancellation_reason",
            sa.String(500),
            nullable=True,
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "notes",
            sa.String(500),
            nullable=True,
        ),
    )

    # --- Order status audit log ---
    op.create_table(
        "order_status_logs",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
        ),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "old_status",
            order_status_enum,
            nullable=True,
        ),
        sa.Column(
            "new_status",
            order_status_enum,
            nullable=False,
        ),
        sa.Column(
            "changed_by_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reason",
            sa.String(500),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
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
    )


def downgrade() -> None:
    op.drop_table("order_status_logs")
    op.drop_column("orders", "notes")
    op.drop_column("orders", "cancellation_reason")
