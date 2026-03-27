"""unified_transfer_api

Revision ID: c1d2e3f4g5h6
Revises: 8e058e9a7678
Create Date: 2026-03-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4g5h6"
down_revision: Union[str, Sequence[str], None] = "8e058e9a7678"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transfer_type_enum ADD VALUE IF NOT EXISTS 'FACTORY_SHIPMENT'")
    op.execute("ALTER TYPE transfer_type_enum ADD VALUE IF NOT EXISTS 'FACTORY_RETURN'")

    op.add_column(
        "stock_transfers",
        sa.Column(
            "reason",
            sa.String(255),
            nullable=True,
            comment="Причина (для списания LOSS_WRITE_OFF)",
        ),
    )
    op.add_column(
        "stock_transfers",
        sa.Column(
            "route_sheet_id",
            sa.UUID(),
            nullable=True,
            comment="ID маршрутного листа (для COURIER_LOAD)",
        ),
    )
    op.create_index(
        op.f("ix_stock_transfers_route_sheet_id"),
        "stock_transfers",
        ["route_sheet_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_stock_transfers_route_sheet_id"), table_name="stock_transfers")
    op.drop_column("stock_transfers", "route_sheet_id")
    op.drop_column("stock_transfers", "reason")
