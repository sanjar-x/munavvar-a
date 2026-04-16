"""Replace contract credit limits with per-product quantity quotas.

Revision ID: a1b2c3d4e5f6
Revises: 014cf8e85d99
Create Date: 2025-07-24 12:00:00.000000+00:00

Changes:
- contracts: drop credit_limit, credit_used columns + CHECK constraints
- contract_price_items: add quantity, quantity_used + CHECK constraints
- orders: replace reserved_credit_amount (BIGINT) with
  quantities_reserved (BOOLEAN)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "014cf8e85d99"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Preflight: fail if any contracts have non-zero credit ──
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT count(*) FROM contracts"
            " WHERE credit_used != 0 OR credit_limit != 0"
        )
    ).scalar()
    if row and row > 0:
        raise RuntimeError(
            f"Cannot migrate: {row} contract(s) have non-zero"
            " credit_limit or credit_used."
            " Migrate credit data first."
        )

    # ── contracts: drop credit columns ──────────────────────
    op.drop_constraint(
        "ck_contract_credit_used_le_limit",
        "contracts",
        type_="check",
    )
    op.drop_constraint(
        "ck_contract_credit_used_non_neg",
        "contracts",
        type_="check",
    )
    op.drop_constraint(
        "ck_contract_credit_limit_non_neg",
        "contracts",
        type_="check",
    )
    op.drop_column("contracts", "credit_used")
    op.drop_column("contracts", "credit_limit")

    # ── contract_price_items: add quantity columns ──────────
    op.add_column(
        "contract_price_items",
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment=("Допустимое кол-во по договору. 0 = без ограничений."),
        ),
    )
    op.add_column(
        "contract_price_items",
        sa.Column(
            "quantity_used",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment=(
                "Использованное кол-во (lifetime). "
                "Увеличивается при создании заказа, "
                "уменьшается только при отмене."
            ),
        ),
    )
    op.create_check_constraint(
        "ck_contract_price_item_quantity_non_neg",
        "contract_price_items",
        "quantity >= 0",
    )
    op.create_check_constraint(
        "ck_contract_price_item_quantity_used_non_neg",
        "contract_price_items",
        "quantity_used >= 0",
    )
    op.create_check_constraint(
        "ck_contract_price_item_quantity_used_le_limit",
        "contract_price_items",
        "quantity_used <= quantity OR quantity = 0",
    )

    # ── orders: replace reserved_credit_amount → bool ───────
    # First add the new column
    op.add_column(
        "orders",
        sa.Column(
            "quantities_reserved",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment=(
                "True если по этому заказу зарезервированы "
                "квоты в contract_price_items."
            ),
        ),
    )
    # Backfill: mark non-settled orders with active reservations
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE orders SET quantities_reserved = true"
            " WHERE reserved_credit_amount IS NOT NULL"
            "   AND reserved_credit_amount > 0"
            "   AND status NOT IN"
            "       ('delivered', 'pickup_completed', 'cancelled')"
        )
    )
    # Now drop the old column
    op.drop_column("orders", "reserved_credit_amount")


def downgrade() -> None:
    # ── orders: restore reserved_credit_amount ──────────────
    op.drop_column("orders", "quantities_reserved")
    op.add_column(
        "orders",
        sa.Column(
            "reserved_credit_amount",
            sa.BIGINT(),
            nullable=True,
            comment=(
                "Зарезервированная сумма кредита. "
                "NULL для не-CONTRACT заказов."
            ),
        ),
    )

    # ── contract_price_items: drop quantity columns ─────────
    op.drop_constraint(
        "ck_contract_price_item_quantity_used_le_limit",
        "contract_price_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_contract_price_item_quantity_used_non_neg",
        "contract_price_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_contract_price_item_quantity_non_neg",
        "contract_price_items",
        type_="check",
    )
    op.drop_column("contract_price_items", "quantity_used")
    op.drop_column("contract_price_items", "quantity")

    # ── contracts: restore credit columns ───────────────────
    op.add_column(
        "contracts",
        sa.Column(
            "credit_limit",
            sa.BIGINT(),
            nullable=False,
            server_default="0",
            comment=("Кредитный лимит в сумах (UZS). 0 = без ограничений."),
        ),
    )
    op.add_column(
        "contracts",
        sa.Column(
            "credit_used",
            sa.BIGINT(),
            nullable=False,
            server_default="0",
            comment=("In-flight сумма заказов, ещё не попавших на счёт."),
        ),
    )
    op.create_check_constraint(
        "ck_contract_credit_limit_non_neg",
        "contracts",
        "credit_limit >= 0",
    )
    op.create_check_constraint(
        "ck_contract_credit_used_non_neg",
        "contracts",
        "credit_used >= 0",
    )
    op.create_check_constraint(
        "ck_contract_credit_used_le_limit",
        "contracts",
        "credit_used <= credit_limit OR credit_limit = 0",
    )
