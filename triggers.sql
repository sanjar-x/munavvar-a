CREATE TRIGGER trigger_update_inventory_balances
AFTER
INSERT
    OR
UPDATE
    OR DELETE ON stock_transactions FOR EACH ROW EXECUTE FUNCTION update_inventory_balances();
