# Code Review: Alembic Migration

**Reviewer:** Migration Safety Agent
**File:** `alembic/versions/a1b2c3d4e5f6_contract_quantity_quotas.py`
**Focus:** SQL safety, data loss, reversibility, production locks

---

## Summary

| Severity | Count |
| -------- | ----- |
| Critical | 3     |
| Medium   | 2     |
| Low      | 1     |
| Info     | 3     |

---

## Critical

### 1. Data loss — credit columns dropped without data migration
**Lines 44–45**

The migration drops `contracts.credit_limit` and `contracts.credit_used` without any data migration logic. If production contracts have non-zero values, this data is permanently lost.

**Fix:** Before dropping, either migrate credit data into the new quantity schema, or add a pre-flight check that fails if any contracts have non-zero credit values.

### 2. Data loss — `reserved_credit_amount` dropped without migration
**Line 89**

`orders.reserved_credit_amount` (BIGINT) is dropped and replaced with `quantities_reserved` (BOOLEAN) without data migration. Orders with active reservations lose tracking data.

**Fix:** Before dropping, run:
```sql
UPDATE orders SET quantities_reserved = true
WHERE reserved_credit_amount IS NOT NULL;
```
(Add `quantities_reserved` column before dropping `reserved_credit_amount`.)

### 3. Downgrade is irreversible after business operations
**Lines 105–175**

The downgrade correctly reverses schema changes, but cannot restore dropped data. After upgrade→downgrade, all contracts get `credit_limit=0` and `credit_used=0`.

**Fix:** Document that downgrade is only safe immediately after upgrade, or implement data preservation logic.

---

## Medium

### 4. Downgrade server_default differs from original schema
**Lines 147–160**

Downgrade adds `credit_limit`/`credit_used` with `server_default="0"`, but the original schema had no server_default — columns required explicit values at INSERT.

### 5. Table locking concerns for production
**Lines 27–102**

Multiple DDL operations on `contracts`, `contract_price_items`, and `orders` tables. Each ALTER TABLE acquires ACCESS EXCLUSIVE lock blocking all reads/writes.

**Fix:** Test migration timing on production-sized data; run during low-traffic window.

---

## Low

### 6. NOT NULL with server_default (safe)
**Lines 48–71**

Adding NOT NULL columns with `server_default="0"` is standard practice and safe.

---

## Info (No Issues Found)

- ✅ Revision chain correct: `109a87243062` → `014cf8e85d99` → `a1b2c3d4e5f6`
- ✅ No PL/pgSQL — asyncpg dollar-quoting not applicable
- ✅ CHECK constraints syntactically correct (`quantity >= 0`, `quantity_used >= 0`, `quantity_used <= quantity OR quantity = 0`)
