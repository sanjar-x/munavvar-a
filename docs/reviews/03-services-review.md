# Code Review: Service Business Logic

**Reviewer:** Service Logic Agent
**Files:** `src/modules/orders/services.py`, `src/modules/contracts/services.py`
**Focus:** Quota reservation/release correctness, double-release, cancel flows, edge cases

---

## Summary

| Severity  | Count |
| --------- | ----- |
| Critical  | 1     |
| High      | 1     |
| Medium    | 2     |
| Low       | 1     |
| ✅ Correct | 3     |

---

## Critical

### 1. Quota leak in `add_product_to_order`
**File:** `src/modules/orders/services.py:696–719`

`add_product_to_order` calls `increment_quantities_used` (line 696–698) but does NOT set `quantities_reserved = True` on the order. When this order is later cancelled, the cancellation logic checks `order.quantities_reserved` (line 944) — since the flag was never set to `True`, quota will NOT be released.

**Evidence:**
- Line 696–698: `increment_quantities_used` is called
- Line 719: Only `total_amount` is updated, NOT `quantities_reserved`
- Line 944: Release only happens if `order.quantities_reserved == True`

**Fix:** After line 698, add:
```python
update_data["quantities_reserved"] = True
```

---

## High

### 2. Quota over-consumption in partial delivery
**File:** `src/modules/orders/services.py:1159–1195`

When partial delivery occurs (`actual_items_dto` provided), `item.quantity` is reduced (lines 1185–1188) and `total_amount` updated, but quota is NOT released for the difference. The lifetime consumed model means `quantity_used` stays at the original higher value, even though less was actually delivered.

**Fix:** After reducing quantities in partial delivery:
```python
if (order.payment_method == PaymentMethod.CONTRACT
        and order.contract_id):
    delta = original_quantity - requested_quantity
    if delta > 0:
        await self.uow.price_items.decrement_quantities_used(
            order.contract_id,
            [(item.product_id, delta)]
        )
```

---

## Medium

### 3. Boolean guard timing issue in `_cancel_inflight_orders`
**File:** `src/modules/orders/services.py` (via `repositories.py:344`)

`bulk_cancel_by_contract` sets `quantities_reserved=False` in a bulk UPDATE BEFORE quantities are actually decremented. If the transaction fails between these operations, the flag is `False` but quotas were never released.

**Fix:** Set `quantities_reserved=False` AFTER `decrement_quantities_used` succeeds.

### 4. Atomicity of `_check_and_reserve_quantities`
**File:** `src/modules/orders/services.py:1009–1036`

Increments are submitted as a loop of individual UPDATEs. If one fails midway, earlier updates remain. Mitigated by UoW transaction rollback, but code doesn't make this guarantee explicit.

---

## Low

### 5. `expire_stale_orders` — SKIP LOCKED edge case
**File:** `src/modules/orders/services.py:1772–1788`

Uses `SKIP LOCKED`. Concurrent instances may repeatedly skip the same orders. Acceptable with regular scheduling.

---

## ✅ Correct (No Issues)

| Area                        | Finding                                                                          |
| --------------------------- | -------------------------------------------------------------------------------- |
| Delivery/Pickup paths       | Both correctly avoid quota release (lifetime consumed) ✓                         |
| Cancel flow guards          | Checks `quantities_reserved`, `old_status != CANCELLED`, not settled ✓           |
| `remove_product_from_order` | Correctly checks CONTRACT + contract_id + quantities_reserved, then decrements ✓ |
