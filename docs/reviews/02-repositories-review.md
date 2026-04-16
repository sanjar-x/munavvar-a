# Code Review: Repository Layer

**Reviewer:** Repository SQL Patterns Agent
**Files:** `src/modules/contracts/repositories.py`, `src/modules/orders/repositories.py`
**Focus:** SQL injection, deadlocks, race conditions, edge cases, performance

---

## Summary

| Severity   | Count |
| ---------- | ----- |
| High       | 1     |
| Medium     | 2     |
| Low        | 1     |
| ✅ Verified | 6     |

---

## High

### 1. Missing rowcount validation in `decrement_quantities_used`
**File:** `src/modules/contracts/repositories.py:203–227`

The method executes UPDATE statements but never checks if rows were actually modified. If a price item was soft-deleted or doesn't exist, the UPDATE affects 0 rows — silently failing to release quota. Creates a **permanent quota leak**.

```python
# Current: no check
await self.session.execute(stmt)

# Fix: validate rowcount
result = await self.session.execute(stmt)
if result.rowcount == 0:
    log.warning("decrement_no_rows_affected",
                contract_id=contract_id,
                product_id=product_id)
```

---

## Medium

### 2. Missing rowcount validation in `increment_quantities_used`
**File:** `src/modules/contracts/repositories.py:186–201`

Same issue as decrement — no verification that rows were updated. Less likely to trigger, but corrupted data could cause silent failures.

### 3. N+1 query pattern in quantity updates
**File:** `src/modules/contracts/repositories.py:186–227`

Both methods execute separate UPDATEs in a loop. For 20 items = 20 round-trips.

**Fix:** Batch into single UPDATE with CASE WHEN:
```python
stmt = (
    sa.update(ContractPriceItem)
    .where(ContractPriceItem.id.in_([id for id, _ in items]))
    .values(quantity_used=ContractPriceItem.quantity_used +
        sa.case({id: delta for id, delta in items},
                value=ContractPriceItem.id))
)
```

---

## Low

### 4. No negative delta validation in `decrement_quantities_used`
**File:** `src/modules/contracts/repositories.py:212–226`

If caller passes negative delta, `greatest(quantity_used - (-delta), 0)` actually **increments**. Currently safe (callers use `OrderItem.quantity` with CHECK `> 0`), but defensive validation would help.

---

## ✅ Verified (No Issues)

| Area                | Finding                                                  |
| ------------------- | -------------------------------------------------------- |
| SQL Injection       | All queries use parameterized SQLAlchemy expressions ✓   |
| Deadlock Prevention | `ORDER BY product_id` for deterministic lock order ✓     |
| Race Conditions     | SELECT FOR UPDATE serializes concurrent transactions ✓   |
| Empty Lists         | `get_for_products_locked` returns `[]` early ✓           |
| Quantity Underflow  | `greatest(..., 0)` prevents negative values ✓            |
| SQLAlchemy Async    | Proper `await session.execute()`, `.with_for_update()` ✓ |
