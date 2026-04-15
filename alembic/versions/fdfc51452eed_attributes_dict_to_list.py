"""attributes_dict_to_list

Revision ID: fdfc51452eed
Revises: a1b2c3d4e5f6
Create Date: 2026-04-15 20:33:05.117306

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fdfc51452eed"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Migrate attributes from dict to list of {label, value} pairs.

    1. Normalize non-object rows (null, scalar, already array) → '[]'
    2. Convert existing `{"k": "v", ...}` → `[{"label":"k","value":"v"}, ...]`
    3. Change server_default from '{}' to '[]'
    4. Add CHECK constraint: jsonb_typeof(attributes) = 'array'
    """
    # Step 1: normalize any non-object, non-array rows to '[]'
    op.execute(
        sa.text("""
        UPDATE products
        SET attributes = '[]'::jsonb
        WHERE jsonb_typeof(attributes) NOT IN ('object', 'array')
           OR attributes IS NULL
    """)
    )

    # Step 2: convert object → list of {label, value} pairs
    op.execute(
        sa.text("""
        UPDATE products
        SET attributes = (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'label', key,
                        'value', value
                    )
                ),
                '[]'::jsonb
            )
            FROM jsonb_each_text(attributes)
        )
        WHERE jsonb_typeof(attributes) = 'object'
    """)
    )

    # Step 3: change default from {} to []
    op.alter_column(
        "products",
        "attributes",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'[]'::jsonb"),
        existing_server_default=sa.text("'{}'::jsonb"),
        comment=("Парные характеристики [{label, value}, ...]"),
        existing_comment=(
            "Динамические характеристики (объем, бренд, цвет, мощность)"
        ),
        existing_nullable=False,
    )

    # Step 4: enforce array shape at DB level
    op.create_check_constraint(
        "ck_product_attributes_is_array",
        "products",
        "jsonb_typeof(attributes) = 'array'",
    )


def downgrade() -> None:
    """Revert attributes from list back to dict (lossy if duplicate labels)."""
    op.drop_constraint(
        "ck_product_attributes_is_array",
        "products",
        type_="check",
    )

    # Data migration: convert list → dict (duplicate labels collapse)
    op.execute(
        sa.text("""
        UPDATE products
        SET attributes = (
            SELECT COALESCE(
                jsonb_object_agg(
                    elem->>'label', elem->>'value'
                ),
                '{}'::jsonb
            )
            FROM jsonb_array_elements(attributes) AS elem
        )
        WHERE jsonb_typeof(attributes) = 'array'
    """)
    )

    op.alter_column(
        "products",
        "attributes",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"),
        existing_server_default=sa.text("'[]'::jsonb"),
        comment=("Динамические характеристики (объем, бренд, цвет, мощность)"),
        existing_comment=("Парные характеристики [{label, value}, ...]"),
        existing_nullable=False,
    )
