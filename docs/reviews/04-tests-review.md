# Code Review: Test Coverage

**Reviewer:** Test Coverage Agent
**Files:** `tests/unit/test_contracts.py`, `tests/unit/test_orders_contract.py`, `tests/integration/test_contracts_api.py`
**Focus:** Coverage gaps, missing edge cases, mock correctness, regression risk

---

## Summary

| Priority     | Missing Scenarios |
| ------------ | ----------------- |
| Critical     | 3                 |
| Important    | 4                 |
| Nice-to-have | 3                 |

---

## Critical Gaps

### 1. Multi-product order quota (partial failure atomicity)
No tests verify ordering **multiple products** where one exceeds quota. Must confirm NO partial increments occur.

```python
async def test_multi_product_partial_failure():
    """Product A has quota. Product B exceeds.
    Entire order fails. Product A quota unchanged."""
```

### 2. Concurrent order race conditions
No integration test verifies two simultaneous orders don't both succeed when quota allows only one. This is the reason for `SELECT FOR UPDATE`.

```python
async def test_concurrent_orders_respect_quota():
    """quota=10, used=5. Two orders of 6 each.
    Only ONE succeeds."""
```

### 3. Quantity underflow protection
No test verifies `greatest(0)` prevents negative `quantity_used` in `decrement_quantities_used`.

---

## Important Gaps

### 4. Cancel delivered order does NOT release quota
Tests verify release on `NEW → CANCELLED` but not that `DELIVERED → CANCELLED` does NOT release.

### 5. Suspend contract with in-flight orders
No test verifies behavior when suspending a contract with pending orders that have reserved quantities.

### 6. Full quota lifecycle (create → cancel → create → exceed)
Integration tests verify creation and cancellation separately, not a full cycle hitting the quota limit across multiple operations.

### 7. `PriceItemHasUsageError` at HTTP level
Unit tests verify the exception, but integration tests don't verify HTTP 409 response.

---

## Nice-to-have

### 8. Stateful fake repos
Current `FakePriceItemRepo` uses plain `AsyncMock()` — can't verify actual quantity changes.

### 9. Boundary value tests
Missing: exact limit (`quantity=1, used=0, order=1`), zero/negative order quantities.

### 10. Empty order items at API level
Current test manipulates DTO post-construction; should also test at HTTP API level.

---

## Regression Risk Matrix

| Risk                 | Gap | Description                                   |
| -------------------- | --- | --------------------------------------------- |
| **Quota corruption** | #1  | Partial reservations on multi-product orders  |
| **Over-reservation** | #2  | Concurrent orders exceed quota                |
| **Negative quota**   | #3  | quantity_used goes below zero                 |
| **Phantom release**  | #4  | Delivered order cancel releases quota         |
| **Quota leak**       | #5  | Suspended contracts leave quantities reserved |
| **Lifecycle bug**    | #6  | Cancel → create → cancel breaks tracking      |

**Priority:** Fix gaps #1, #2, #3, and #6 first — they guard the most critical invariants.
