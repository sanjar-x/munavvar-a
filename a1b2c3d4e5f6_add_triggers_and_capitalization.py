"""add balance triggers and orders.capitalization_applied

Revision ID: a1b2c3d4e5f6
Revises: 0e04bb949a80
Create Date: 2026-03-15 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "0e04bb949a80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# SQL: Триггер автоматического пересчета балансов финансовых счетов
# Таблица: transactions -> accounts.balance
# ---------------------------------------------------------------------------
UPDATE_ACCOUNT_BALANCES_FUNCTION = """
CREATE OR REPLACE FUNCTION update_account_balances() RETURNS TRIGGER AS $$
DECLARE
    diff_from BIGINT := 0;
    diff_to   BIGINT := 0;
BEGIN
    -- Запрет удаления (Strict Ledger)
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Удаление транзакций запрещено. Используйте отмену (REJECTED) или корректирующую транзакцию.';
    END IF;

    -- Запрет изменения суммы и контрагентов
    IF TG_OP = 'UPDATE' THEN
        IF OLD.amount IS DISTINCT FROM NEW.amount THEN
            RAISE EXCEPTION 'Изменение суммы существующей транзакции запрещено.';
        END IF;
        IF OLD.from_id != NEW.from_id OR OLD.to_id != NEW.to_id THEN
            RAISE EXCEPTION 'Изменение отправителя или получателя транзакции запрещено.';
        END IF;
    END IF;

    -- Расчет дельты баланса
    IF TG_OP = 'INSERT' THEN
        IF NEW.status = 'completed' THEN
            diff_from := -NEW.amount;
            diff_to   :=  NEW.amount;
        END IF;
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.status != 'completed' AND NEW.status = 'completed' THEN
            diff_from := -NEW.amount;
            diff_to   :=  NEW.amount;
        ELSIF OLD.status = 'completed' AND NEW.status != 'completed' THEN
            diff_from :=  OLD.amount;
            diff_to   := -OLD.amount;
        END IF;
    END IF;

    -- Нет изменений — выход
    IF diff_from = 0 AND diff_to = 0 THEN
        RETURN NEW;
    END IF;

    -- Блокировка счетов в детерминированном порядке (защита от deadlock)
    PERFORM id FROM accounts
    WHERE id IN (NEW.from_id, NEW.to_id)
    ORDER BY id
    FOR UPDATE;

    -- Обновление балансов
    UPDATE accounts SET balance = balance + diff_from WHERE id = NEW.from_id;
    UPDATE accounts SET balance = balance + diff_to   WHERE id = NEW.to_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

DROP_ACCOUNT_BALANCES_TRIGGER = """
DROP TRIGGER IF EXISTS trigger_update_account_balances ON transactions;
"""

CREATE_ACCOUNT_BALANCES_TRIGGER = """
CREATE TRIGGER trigger_update_account_balances
    AFTER INSERT OR UPDATE OR DELETE
    ON transactions
    FOR EACH ROW
    EXECUTE FUNCTION update_account_balances();
"""

# ---------------------------------------------------------------------------
# SQL: Триггер автоматического пересчета балансов инвентаря
# Таблица: stock_transactions -> inventory_balances.quantity
# ---------------------------------------------------------------------------
UPDATE_INVENTORY_BALANCES_FUNCTION = """
CREATE OR REPLACE FUNCTION update_inventory_balances() RETURNS TRIGGER AS $$
BEGIN
    -- Запрет мутации (Strict Ledger)
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'Изменение истории транзакций запрещено. Создайте корректирующее перемещение.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Удаление транзакций запрещено. Создайте корректирующее перемещение.';
    END IF;

    -- INSERT: upsert в таблицу inventory_balances
    IF TG_OP = 'INSERT' THEN
        INSERT INTO inventory_balances (id, inventory_id, product_id, quantity, created_at, updated_at)
        SELECT gen_random_uuid(), v.inv_id, NEW.product_id, v.qty, NOW(), NOW()
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

DROP_INVENTORY_BALANCES_TRIGGER = """
DROP TRIGGER IF EXISTS trigger_update_inventory_balances ON stock_transactions;
"""

CREATE_INVENTORY_BALANCES_TRIGGER = """
CREATE TRIGGER trigger_update_inventory_balances
    AFTER INSERT OR UPDATE OR DELETE
    ON stock_transactions
    FOR EACH ROW
    EXECUTE FUNCTION update_inventory_balances();
"""

# ---------------------------------------------------------------------------
# Downgrade SQL
# ---------------------------------------------------------------------------
DROP_ACCOUNT_FUNCTION = """
DROP FUNCTION IF EXISTS update_account_balances();
"""

DROP_INVENTORY_FUNCTION = """
DROP FUNCTION IF EXISTS update_inventory_balances();
"""


def upgrade() -> None:
    # 1. Триггер балансов финансовых счетов
    op.execute(UPDATE_ACCOUNT_BALANCES_FUNCTION)
    op.execute(DROP_ACCOUNT_BALANCES_TRIGGER)
    op.execute(CREATE_ACCOUNT_BALANCES_TRIGGER)

    # 2. Триггер балансов инвентаря
    op.execute(UPDATE_INVENTORY_BALANCES_FUNCTION)
    op.execute(DROP_INVENTORY_BALANCES_TRIGGER)
    op.execute(CREATE_INVENTORY_BALANCES_TRIGGER)

    # 3. Новая колонка: orders.capitalization_applied
    op.add_column(
        "orders",
        sa.Column(
            "capitalization_applied",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Было ли авто-оприходование тары при создании заказа",
        ),
    )


def downgrade() -> None:
    # 3. Удаляем колонку
    op.drop_column("orders", "capitalization_applied")

    # 2. Удаляем триггер и функцию инвентаря
    op.execute(DROP_INVENTORY_BALANCES_TRIGGER)
    op.execute(DROP_INVENTORY_FUNCTION)

    # 1. Удаляем триггер и функцию финансов
    op.execute(DROP_ACCOUNT_BALANCES_TRIGGER)
    op.execute(DROP_ACCOUNT_FUNCTION)
