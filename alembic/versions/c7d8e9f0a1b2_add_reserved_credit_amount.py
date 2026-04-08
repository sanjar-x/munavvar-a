"""Add reserved_credit_amount to orders.

Stores the original credit reservation amount at order creation
for correct credit_used release on partial delivery or cancel.

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2025-07-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "reserved_credit_amount",
            sa.BigInteger(),
            nullable=True,
            comment=(
                "Зарезервированная сумма кредита при создании заказа. "
                "Используется для корректного возврата credit_used "
                "при частичной доставке или отмене. "
                "NULL для не-CONTRACT заказов."
            ),
        ),
    )

    # Backfill: для открытых CONTRACT-заказов, которые ещё не
    # завершены/отменены, ставим reserved_credit_amount = total_amount.
    # Это лучшее приближение для существующих данных.
    op.execute("""
        UPDATE orders
        SET reserved_credit_amount = total_amount
        WHERE contract_id IS NOT NULL
          AND status NOT IN ('delivered', 'pickup_completed', 'cancelled')
          AND reserved_credit_amount IS NULL
    """)

    # Для завершённых/отменённых CONTRACT-заказов — 0 (кредит уже
    # был возвращён).
    op.execute("""
        UPDATE orders
        SET reserved_credit_amount = 0
        WHERE contract_id IS NOT NULL
          AND status IN ('delivered', 'pickup_completed', 'cancelled')
          AND reserved_credit_amount IS NULL
    """)


def downgrade() -> None:
    op.drop_column("orders", "reserved_credit_amount")
