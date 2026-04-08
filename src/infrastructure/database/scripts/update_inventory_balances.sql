CREATE OR REPLACE FUNCTION update_inventory_balances() RETURNS TRIGGER AS $$ BEGIN IF TG_OP = 'UPDATE' THEN RAISE EXCEPTION 'Изменение истории транзакций запрещено. Создайте корректирующее перемещение.';
END IF;
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Удаление транзакций запрещено. Создайте корректирующее перемещение.';
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
SELECT gen_random_uuid(),
    v.inv_id,
    NEW.product_id,
    v.qty,
    NOW(),
    NOW()
FROM (
        VALUES (NEW.from_id, - NEW.quantity),
            (NEW.to_id, NEW.quantity)
    ) AS v(inv_id, qty)
ORDER BY v.inv_id ON CONFLICT (inventory_id, product_id) DO
UPDATE
SET quantity = inventory_balances.quantity + EXCLUDED.quantity,
    updated_at = NOW();
IF EXISTS (
    SELECT 1
    FROM inventory_balances AS balance
        JOIN inventories AS inventory ON inventory.id = balance.inventory_id
    WHERE balance.product_id = NEW.product_id
        AND balance.inventory_id IN (NEW.from_id, NEW.to_id)
        AND inventory.type NOT IN ('VIRTUAL_VENDOR', 'VIRTUAL_LOSS')
        AND balance.quantity < 0
) THEN RAISE EXCEPTION 'Negative balances are not allowed for non-virtual inventories.';
END IF;
RETURN NEW;
END IF;
RETURN NULL;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trigger_update_inventory_balances ON stock_transactions;
CREATE TRIGGER trigger_update_inventory_balances
AFTER
INSERT
    OR
UPDATE
    OR DELETE ON stock_transactions FOR EACH ROW EXECUTE FUNCTION update_inventory_balances();
