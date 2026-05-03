"""Soft quota limits: allow overspend, add Order.quota_exceeded.

Revision ID: d4e5f6a7b8c9
Revises: c3f8a9d4e2b1
Create Date: 2026-05-01 12:00:00.000000+00:00

Changes:
- contract_price_items: drop CHECK ck_contract_price_item_quantity_used_le_limit
  (quantity_used may now exceed quantity — soft limit)
- orders: add quota_exceeded BOOLEAN NOT NULL DEFAULT FALSE
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str = "c3f8a9d4e2b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_contract_price_item_quantity_used_le_limit",
        "contract_price_items",
        type_="check",
    )
    op.add_column(
        "orders",
        sa.Column(
            "quota_exceeded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment=(
                "Флаг: заказ создан с превышением квоты по договору. "
                "Бизнес использует для контроля перерасхода."
            ),
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "quota_overspend",
            JSONB(),
            nullable=True,
            comment=(
                "Детали перерасхода квоты: "
                "[{product_id, limit, used, requested, overspend}]"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "quota_overspend")
    op.drop_column("orders", "quota_exceeded")
    op.create_check_constraint(
        "ck_contract_price_item_quantity_used_le_limit",
        "contract_price_items",
        "quantity_used <= quantity OR quantity = 0",
    )
