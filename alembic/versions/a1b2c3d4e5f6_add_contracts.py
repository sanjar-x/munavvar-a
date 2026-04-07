"""Add contracts module (contracts, contract_price_items, invoices,
orders.contract_id).

Revision ID: a1b2c3d4e5f6
Revises: 9a9cbfcda833
Create Date: 2025-01-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "9a9cbfcda833"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Новые ENUM типы
    op.execute("""
        CREATE TYPE contract_status_enum AS ENUM (
            'draft', 'active', 'suspended', 'terminated', 'expired'
        )
    """)
    op.execute("""
        CREATE TYPE invoice_status_enum AS ENUM (
            'draft', 'issued', 'partially_paid',
            'paid', 'overdue', 'cancelled'
        )
    """)

    # 2. Таблица contracts
    op.create_table(
        "contracts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("number", sa.String(50), nullable=False, unique=True),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "active",
                "suspended",
                "terminated",
                "expired",
                name="contract_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column(
            "credit_limit",
            sa.BigInteger,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "credit_used",
            sa.BigInteger,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "payment_due_days",
            sa.Integer,
            nullable=False,
            server_default="30",
        ),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("inn", sa.String(14), nullable=False),
        sa.Column("legal_address", sa.Text, nullable=True),
        sa.Column("bank_account_number", sa.String(25), nullable=True),
        sa.Column("bank_name", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("signed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "signed_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "suspended_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column("suspension_reason", sa.String(512), nullable=True),
        sa.Column(
            "terminated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column("termination_reason", sa.String(512), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint(
            "credit_limit >= 0",
            name="ck_contract_credit_limit_non_neg",
        ),
        sa.CheckConstraint(
            "credit_used >= 0",
            name="ck_contract_credit_used_non_neg",
        ),
        sa.CheckConstraint(
            "credit_used <= credit_limit OR credit_limit = 0",
            name="ck_contract_credit_used_le_limit",
        ),
        sa.CheckConstraint(
            "payment_due_days > 0",
            name="ck_contract_payment_due_days_pos",
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date > start_date",
            name="ck_contract_dates_order",
        ),
        comment="Договоры с юридическими лицами (B2B)",
    )
    # Индексы на contracts
    op.create_index("idx_contract_client_id", "contracts", ["client_id"])
    op.create_index("idx_contract_status", "contracts", ["status"])
    op.create_index(
        "idx_contract_client_status",
        "contracts",
        ["client_id", "status"],
    )
    # Partial unique: один активный договор на клиента
    # op.create_index() не поддерживает WHERE → используем raw SQL
    op.execute("""
        CREATE UNIQUE INDEX uq_one_active_contract_per_client
        ON contracts (client_id)
        WHERE status = 'active' AND is_active = true
    """)

    # 3. Таблица contract_price_items
    op.create_table(
        "contract_price_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id",
            UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("price", sa.BigInteger, nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "contract_id",
            "product_id",
            name="uq_contract_price_item_product",
        ),
        sa.CheckConstraint(
            "price >= 0",
            name="ck_contract_price_item_price_non_neg",
        ),
        comment=(
            "Индивидуальный прайс-лист по договору. "
            "При отсутствии позиции — фолбэк на products.price."
        ),
    )
    op.create_index(
        "idx_contract_price_items_contract_id",
        "contract_price_items",
        ["contract_id"],
    )
    op.create_index(
        "idx_contract_price_items_product_id",
        "contract_price_items",
        ["product_id"],
    )

    # 4. Добавить contract_id в orders
    op.add_column(
        "orders",
        sa.Column(
            "contract_id",
            UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="RESTRICT"),
            nullable=True,
            comment=(
                "Договор (обязателен при payment_method=CONTRACT, "
                "иначе NULL). ondelete=RESTRICT: нельзя удалить "
                "договор с привязанными заказами."
            ),
        ),
    )
    # Partial index: индексируем только строки с контрактом
    op.execute("""
        CREATE INDEX idx_orders_contract_id
        ON orders (contract_id)
        WHERE contract_id IS NOT NULL
    """)

    # 5. Таблица invoices
    op.create_table(
        "invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id",
            UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("number", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "issued",
                "partially_paid",
                "paid",
                "overdue",
                "cancelled",
                name="invoice_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("period_from", sa.Date, nullable=False),
        sa.Column("period_to", sa.Date, nullable=False),
        sa.Column(
            "amount",
            sa.BigInteger,
            nullable=False,
            server_default="0",
        ),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("issued_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "contract_id",
            "number",
            name="uq_invoice_contract_number",
        ),
        sa.CheckConstraint(
            "period_to > period_from",
            name="ck_invoice_period_order",
        ),
        sa.CheckConstraint(
            "amount >= 0",
            name="ck_invoice_amount_non_neg",
        ),
        comment=("Счета-фактуры, выставляемые по биллинговому циклу договора"),
    )
    op.create_index("idx_invoices_contract_id", "invoices", ["contract_id"])
    op.create_index("idx_invoices_status", "invoices", ["status"])


def downgrade() -> None:
    op.drop_index("idx_invoices_status", table_name="invoices")
    op.drop_index("idx_invoices_contract_id", table_name="invoices")
    op.drop_table("invoices")

    op.execute("DROP INDEX IF EXISTS idx_orders_contract_id")
    op.drop_column("orders", "contract_id")

    op.drop_index(
        "idx_contract_price_items_product_id",
        table_name="contract_price_items",
    )
    op.drop_index(
        "idx_contract_price_items_contract_id",
        table_name="contract_price_items",
    )
    op.drop_table("contract_price_items")

    op.execute("DROP INDEX IF EXISTS uq_one_active_contract_per_client")
    op.drop_index("idx_contract_client_status", table_name="contracts")
    op.drop_index("idx_contract_status", table_name="contracts")
    op.drop_index("idx_contract_client_id", table_name="contracts")
    op.drop_table("contracts")

    op.execute("DROP TYPE IF EXISTS invoice_status_enum")
    op.execute("DROP TYPE IF EXISTS contract_status_enum")
