"""fix virtual inventory balance check

Drop the unconditional CHECK constraint on inventory_balances.quantity
and update the trigger to enforce non-negative balances only for
non-virtual inventories (VIRTUAL_VENDOR / VIRTUAL_LOSS are exempt).

Revision ID: db4934c22d35
Revises: 42dbaeeee209
Create Date: 2026-04-08 12:35:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "db4934c22d35"
down_revision: str | Sequence[str] | None = "42dbaeeee209"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---------------------------------------------------------------------------
# Updated trigger: adds negative-balance guard for non-virtual inventories
# ---------------------------------------------------------------------------
UPDATED_INVENTORY_BALANCES_FUNCTION = """
CREATE OR REPLACE FUNCTION update_inventory_balances()
RETURNS TRIGGER AS $$
BEGIN
    -- Запрет мутации (Strict Ledger)
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION
            'Изменение истории транзакций запрещено. '
            'Создайте корректирующее перемещение.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'Удаление транзакций запрещено. '
            'Создайте корректирующее перемещение.';
    END IF;

    -- INSERT: upsert в таблицу inventory_balances
    IF TG_OP = 'INSERT' THEN
        INSERT INTO inventory_balances (
            id, inventory_id, product_id, quantity,
            created_at, updated_at
        )
        SELECT gen_random_uuid(), v.inv_id, NEW.product_id,
               v.qty, NOW(), NOW()
        FROM (
            VALUES (NEW.from_id, -NEW.quantity),
                   (NEW.to_id,    NEW.quantity)
        ) AS v(inv_id, qty)
        ORDER BY v.inv_id
        ON CONFLICT (inventory_id, product_id) DO UPDATE
        SET quantity   = inventory_balances.quantity + EXCLUDED.quantity,
            updated_at = NOW();

        -- Guard: non-virtual inventories must not go negative
        IF EXISTS (
            SELECT 1
            FROM inventory_balances AS balance
            JOIN inventories AS inventory
                ON inventory.id = balance.inventory_id
            WHERE balance.product_id = NEW.product_id
              AND balance.inventory_id IN (NEW.from_id, NEW.to_id)
              AND inventory.type NOT IN (
                    'VIRTUAL_VENDOR', 'VIRTUAL_LOSS'
              )
              AND balance.quantity < 0
        ) THEN
            RAISE EXCEPTION
                'Negative balances are not allowed '
                'for non-virtual inventories.'
                USING ERRCODE = '23514';
        END IF;

        RETURN NEW;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

# Restore the old trigger (without the guard) for downgrade
OLD_INVENTORY_BALANCES_FUNCTION = """
CREATE OR REPLACE FUNCTION update_inventory_balances()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION
            'Изменение истории транзакций запрещено. '
            'Создайте корректирующее перемещение.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'Удаление транзакций запрещено. '
            'Создайте корректирующее перемещение.';
    END IF;

    IF TG_OP = 'INSERT' THEN
        INSERT INTO inventory_balances (
            id, inventory_id, product_id, quantity,
            created_at, updated_at
        )
        SELECT gen_random_uuid(), v.inv_id, NEW.product_id,
               v.qty, NOW(), NOW()
        FROM (
            VALUES (NEW.from_id, -NEW.quantity),
                   (NEW.to_id,    NEW.quantity)
        ) AS v(inv_id, qty)
        ORDER BY v.inv_id
        ON CONFLICT (inventory_id, product_id) DO UPDATE
        SET quantity   = inventory_balances.quantity + EXCLUDED.quantity,
            updated_at = NOW();

        RETURN NEW;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    # 1. Drop the unconditional CHECK constraint
    op.drop_constraint(
        "ck_inventory_balances_quantity_non_negative",
        "inventory_balances",
        type_="check",
    )

    # 2. Replace trigger function (adds virtual-inventory exemption)
    op.execute(UPDATED_INVENTORY_BALANCES_FUNCTION)


def downgrade() -> None:
    # 1. Restore the old trigger function (no guard)
    op.execute(OLD_INVENTORY_BALANCES_FUNCTION)

    # 2. Re-add the CHECK constraint
    op.create_check_constraint(
        "ck_inventory_balances_quantity_non_negative",
        "inventory_balances",
        "quantity >= 0",
    )
