CREATE OR REPLACE FUNCTION update_account_balances() RETURNS TRIGGER AS $$
DECLARE diff_from BIGINT := 0;
diff_to BIGINT := 0;
BEGIN IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Удаление транзакций запрещено. Используйте отмену (REJECTED) или корректирующую транзакцию.';
END IF;
IF TG_OP = 'UPDATE' THEN IF OLD.amount IS DISTINCT
FROM NEW.amount THEN RAISE EXCEPTION 'Изменение суммы существующей транзакции запрещено.';
END IF;
IF OLD.from_id != NEW.from_id
OR OLD.to_id != NEW.to_id THEN RAISE EXCEPTION 'Изменение отправителя или получателя транзакции запрещено.';
END IF;
END IF;
IF TG_OP = 'INSERT' THEN IF NEW.status = 'completed' THEN diff_from := - NEW.amount;
diff_to := NEW.amount;
END IF;
ELSIF TG_OP = 'UPDATE' THEN IF OLD.status != 'completed'
AND NEW.status = 'completed' THEN diff_from := - NEW.amount;
diff_to := NEW.amount;
ELSIF OLD.status = 'completed'
AND NEW.status != 'completed' THEN diff_from := OLD.amount;
diff_to := - OLD.amount;
END IF;
END IF;
IF diff_from = 0
AND diff_to = 0 THEN RETURN NEW;
END IF;
PERFORM id
FROM accounts
WHERE id IN (NEW.from_id, NEW.to_id)
ORDER BY id FOR
UPDATE;
UPDATE accounts
SET balance = balance + diff_from
WHERE id = NEW.from_id;
UPDATE accounts
SET balance = balance + diff_to
WHERE id = NEW.to_id;
RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trigger_update_account_balances ON transactions;
CREATE TRIGGER trigger_update_account_balances
AFTER
INSERT
    OR
UPDATE
    OR DELETE ON transactions FOR EACH ROW EXECUTE FUNCTION update_account_balances();