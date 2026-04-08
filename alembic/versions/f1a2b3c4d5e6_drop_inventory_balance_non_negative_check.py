"""drop inventory balance non-negative check

Revision ID: f1a2b3c4d5e6
Revises: d8e9f0a1b2c3
Create Date: 2026-04-08 10:38:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPDATE_INVENTORY_BALANCES_FUNCTION = """
CREATE OR REPLACE FUNCTION update_inventory_balances()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION
            'Изменение истории транзакций запрещено.'
            ' Создайте корректирующее перемещение.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'Удаление транзакций запрещено.'
            ' Создайте корректирующее перемещение.';
    END IF;

    IF TG_OP = 'INSERT' THEN
        INSERT INTO inventory_balances (
            id,
            inventory_id,
            product_id,
            quantity,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            v.inv_id,
            NEW.product_id,
            v.qty,
            NOW(),
            NOW()
        FROM (
            VALUES
                (NEW.from_id, -NEW.quantity),
                (NEW.to_id, NEW.quantity)
        ) AS v(inv_id, qty)
        ORDER BY v.inv_id
        ON CONFLICT (inventory_id, product_id) DO UPDATE
        SET
            quantity = inventory_balances.quantity + EXCLUDED.quantity,
            updated_at = NOW();

        IF EXISTS (
            SELECT 1
            FROM inventory_balances AS balance
            JOIN inventories AS inventory
                ON inventory.id = balance.inventory_id
            WHERE balance.product_id = NEW.product_id
              AND balance.inventory_id IN (NEW.from_id, NEW.to_id)
              AND inventory.type NOT IN (
                  'VIRTUAL_VENDOR',
                  'VIRTUAL_LOSS'
              )
              AND balance.quantity < 0
        ) THEN
            RAISE EXCEPTION
                'Negative balances are not allowed'
                ' for non-virtual inventories.';
        END IF;

        RETURN NEW;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

LEGACY_UPDATE_INVENTORY_BALANCES_FUNCTION = """
CREATE OR REPLACE FUNCTION update_inventory_balances()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION
            'Изменение истории транзакций запрещено.'
            ' Создайте корректирующее перемещение.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'Удаление транзакций запрещено.'
            ' Создайте корректирующее перемещение.';
    END IF;

    IF TG_OP = 'INSERT' THEN
        INSERT INTO inventory_balances (
            id,
            inventory_id,
            product_id,
            quantity,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            v.inv_id,
            NEW.product_id,
            v.qty,
            NOW(),
            NOW()
        FROM (
            VALUES
                (NEW.from_id, -NEW.quantity),
                (NEW.to_id, NEW.quantity)
        ) AS v(inv_id, qty)
        ORDER BY v.inv_id
        ON CONFLICT (inventory_id, product_id) DO UPDATE
        SET
            quantity = inventory_balances.quantity + EXCLUDED.quantity,
            updated_at = NOW();

        RETURN NEW;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(UPDATE_INVENTORY_BALANCES_FUNCTION)
    op.execute(
        """
        ALTER TABLE inventory_balances
        DROP CONSTRAINT IF EXISTS ck_inventory_balances_quantity_non_negative;
        """
    )


def downgrade() -> None:
    op.execute(LEGACY_UPDATE_INVENTORY_BALANCES_FUNCTION)
    op.execute(
        """
        ALTER TABLE inventory_balances
        ADD CONSTRAINT ck_inventory_balances_quantity_non_negative
        CHECK (quantity >= 0);
        """
    )
