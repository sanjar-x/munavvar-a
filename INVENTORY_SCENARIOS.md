# Inventory Scenarios & Edge Cases: HOD Water Delivery

**Date:** 2026-03-27
**Status:** Reference Document
**Scope:** StockTransfers, StockTransactions, Balances, all participant movements

---

## Table of Contents

- [Inventory Scenarios \& Edge Cases: HOD Water Delivery](#inventory-scenarios--edge-cases-hod-water-delivery)
  - [Table of Contents](#table-of-contents)
  - [1. Participants \& Inventory Types](#1-participants--inventory-types)
    - [1.1 Physical Participants](#11-physical-participants)
    - [1.2 Virtual Participants](#12-virtual-participants)
  - [2. Transfer Types \& Valid Routes](#2-transfer-types--valid-routes)
    - [Route Validation Matrix](#route-validation-matrix)
  - [3. Warehouse Operations](#3-warehouse-operations)
    - [3.1 Factory Receipt / Purchase](#31-factory-receipt--purchase)
    - [3.2 Production (Refill / Bottling)](#32-production-refill--bottling)
    - [4.2 During Day: Order Deliveries (see Section 5)](#42-during-day-order-deliveries-see-section-5)
    - [4.3 Evening: Close Shift (COURIER\_RETURN + Cash Collection)](#43-evening-close-shift-courier_return--cash-collection)
    - [4.4 Loss Write-Off (LOSS\_WRITE\_OFF)](#44-loss-write-off-loss_write_off)
  - [5. Order Fulfillment \& Client Delivery](#5-order-fulfillment--client-delivery)
  - [12. Data Integrity \& Ledger Edge Cases](#12-data-integrity--ledger-edge-cases)
    - [12.1 Immutable Ledger (StockTransaction)](#121-immutable-ledger-stocktransaction)
    - [12.2 Balance Trigger](#122-balance-trigger)
    - [12.3 Transfer Document Integrity](#123-transfer-document-integrity)
  - [13. Not Yet Implemented / Potential Gaps](#13-not-yet-implemented--potential-gaps)
    - [13.1 Missing Business Scenarios](#131-missing-business-scenarios)
    - [13.2 Missing Validation Gaps](#132-missing-validation-gaps)
    - [13.3 Scalability Concerns](#133-scalability-concerns)
  - [Appendix A: Complete Business Flow Scenarios](#appendix-a-complete-business-flow-scenarios)
    - [A.1 Happy Path: Full Day Cycle](#a1-happy-path-full-day-cycle)
    - [A.2 New Client Onboarding](#a2-new-client-onboarding)
    - [A.3 Edge Case: Client Orders More Than Available Tara](#a3-edge-case-client-orders-more-than-available-tara)
    - [A.4 Edge Case: Courier Runs Out of Stock Mid-Route](#a4-edge-case-courier-runs-out-of-stock-mid-route)
    - [A.5 Edge Case: Shift Close with Discrepancy](#a5-edge-case-shift-close-with-discrepancy)
    - [A.6 Edge Case: Production Cycle](#a6-edge-case-production-cycle)
    - [A.7 Edge Case: Concurrent Double-Spending](#a7-edge-case-concurrent-double-spending)
  - [Appendix B: Error Code Reference](#appendix-b-error-code-reference)

---

## 1. Participants & Inventory Types

### 1.1 Physical Participants

| Participant             | InventoryType | Role                                   | Holds                                          |
| ----------------------- | ------------- | -------------------------------------- | ---------------------------------------------- |
| Warehouse (Storekeeper) | `WAREHOUSE`   | Storage, production, loading/unloading | Full bottles, empty bottles, equipment         |
| Courier (Driver)        | `COURIER`     | Transport, delivery, cash collection   | Full bottles on truck, empty bottles collected |
| Client (B2C/B2B)        | `CLIENT`      | Consumer, returnable container holder  | Empty bottles (tara), delivered equipment      |

### 1.2 Virtual Participants

| Participant    | InventoryType    | Purpose                                                                               |
| -------------- | ---------------- | ------------------------------------------------------------------------------------- |
| Virtual Vendor | `VIRTUAL_VENDOR` | Infinite source for goods entering the system (purchases, findings, initial balances) |
| Virtual Loss   | `VIRTUAL_LOSS`   | Infinite sink for goods leaving the system (breakage, theft, loss)                    |




## 2. Transfer Types & Valid Routes

### Route Validation Matrix

| TransferType         | Valid Source         | Valid Destination             |
| -------------------- | -------------------- | ----------------------------- |
| `FACTORY_RECEIPT`    | VIRTUAL_VENDOR       | WAREHOUSE                     |
| `PURCHASE`           | VIRTUAL_VENDOR       | WAREHOUSE                     |
| `PRODUCTION`         | WAREHOUSE            | WAREHOUSE (same or different) |
| `COURIER_LOAD`       | WAREHOUSE            | COURIER                       |
| `COURIER_RETURN`     | COURIER              | WAREHOUSE                     |
| `CLIENT_DELIVERY`    | COURIER              | CLIENT                        |
| `CLIENT_RETURN`      | CLIENT               | COURIER                       |
| `WAREHOUSE_TRANSFER` | WAREHOUSE            | WAREHOUSE (must be different) |
| `LOSS_WRITE_OFF`     | WAREHOUSE or COURIER | VIRTUAL_LOSS                  |
| `INVENTORY_FINDING`  | VIRTUAL_VENDOR       | WAREHOUSE or COURIER          |
| `INITIAL_BALANCE`    | VIRTUAL_VENDOR       | CLIENT, WAREHOUSE, or COURIER |



---

## 3. Warehouse Operations

### 3.1 Factory Receipt / Purchase

| #      | Scenario                                         | Expected Behavior                                                                                                                                                    
| 3.1.3  | Complete FACTORY_RECEIPT without adding items    | **BUG:** `complete_transfer` does NOT check for empty items. Transfer silently completes with 0 transactions. `EmptyTransferError` is defined but never raised. **Approved (bug documented                                                                                                                                         |

### 3.2 Production (Refill / Bottling)

| #     | Scenario                                                   | Expected Behavior                                                                                                                                                            |
| ----- | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 3.2.1 | Convert 100 empty bottles -> 100 full bottles (PRODUCTION) | WH(empty) -100, WH(full) +100 (two transfers or single multi-item). **Approved**                                                                                             |
| 3.2.2 | Production when not enough empty bottles                   | `ValueError` from `complete_transfer` (not structured `InsufficientStockError`). Checks one item at a time, raises on first failure. **Approved (inconsistency documented)** |
| 3.2.3 | Production WAREHOUSE A -> WAREHOUSE B                      | Valid (raw materials -> finished goods). **Approved**                                                                                                                        |
| 3.2.4 | Production with zero items                                 | **BUG:** Silently completes with 0 transactions                                                                                                                              |

                                                                                 |

---

### 4.2 During Day: Order Deliveries (see Section 5)

### 4.3 Evening: Close Shift (COURIER_RETURN + Cash Collection)

| #      | Scenario                                                                 | Expected Behavior                                                                        |
| ------ | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| 4.3.1  | Normal close: return all remaining stock + cash                          | COURIER -> WAREHOUSE transfer, cash to system account                                    |
| 4.3.2  | Returned inventory doesn't match system balances                         | `ValueError: "Balance mismatch for product X"`                                           |
| 4.3.3  | Courier has 10 full bottles on system, returns 8                         | Error: must write off 2 as loss first, then close                                        |
| 4.3.4  | Courier has 0 balance but returns 5 items                                | Error: system says 0, courier says 5                                                     |
| 4.3.5  | Courier has products not mentioned in returned_inventory                 | Error: product exists in system but not in return list                                   |
| 4.3.6  | Courier returns products not on system record                            | Error: product in return list but not in system                                          |
| 4.3.7  | Close shift with cash_collected = 0                                      | Inventory return processed, cash transfer skipped                                        |
| 4.3.8  | Close shift with negative cash_collected                                 | Likely allowed (schema doesn't validate, cast to int)                                    |
| 4.3.9  | Close shift with cash_collected > courier account balance                | Financial transaction created regardless (no balance check in close_shift)               |
| 4.3.10 | Close shift when courier has no financial account                        | Error from `get_user_account_by_type`                                                    |
| 4.3.11 | Close shift twice for same courier                                       | Second attempt: inventory.is_active=False, not found                                     |
| 4.3.12 | Close shift without active courier inventory                             | `ValueError: "Active inventory for courier not found"`                                   |
| 4.3.13 | Close with empty returned_inventory list                                 | No COURIER_RETURN transfer created, only cash collection and deactivation                |
| 4.3.14 | System WAREHOUSE (main) not found                                        | Error from `get_system_inventory(WAREHOUSE)`                                             |
| 4.3.15 | Courier has only zero-balance products                                   | returned_inventory must list those products with qty=0, or omit them (both should match) |
| 4.3.16 | Close shift during active delivery (courier still has orders IN_TRANSIT) | No guard: shift closes regardless of pending orders                                      |
| 4.3.17 | `courier_id` is inventory_id vs user_id ambiguity                        | Code tries inventory_id first, then user_id fallback                                     |

### 4.4 Loss Write-Off (LOSS_WRITE_OFF)

| #     | Scenario                                | Expected Behavior                                             |
| ----- | --------------------------------------- | ------------------------------------------------------------- |
| 4.4.1 | Write off 2 broken bottles from courier | COURIER -2, VIRTUAL_LOSS +2                                   |
| 4.4.2 | Write off 5 bottles from warehouse      | WAREHOUSE -5, VIRTUAL_LOSS +5                                 |
| 4.4.3 | Write off from CLIENT inventory         | `InventoryTypeMismatchError` (only WAREHOUSE/COURIER allowed) |
| 4.4.4 | Write off more than available           | `InsufficientStockError`                                      |
| 4.4.5 | Write off from VIRTUAL_VENDOR           | `InventoryTypeMismatchError`                                  |
| 4.4.6 | Write off with empty items              | Transfer created with no items                                |
| 4.4.7 | Write off from deactivated inventory    | Depends on `get_inventory_with_balances` behavior             |
| 4.4.8 | Write off product not on inventory      | Shortage computed, `InsufficientStockError`                   |

---

## 5. Order Fulfillment & Client Delivery

| 5.2.7  | CANCELLED -> DELIVERED                      | **BUG:** Allowed AND triggers fulfillment. No state machine validation.                            |




---

## 12. Data Integrity & Ledger Edge Cases

### 12.1 Immutable Ledger (StockTransaction)

| #      | Scenario                                                 | Expected Behavior                                                    |
| ------ | -------------------------------------------------------- | -------------------------------------------------------------------- |
| 12.1.1 | Attempt to delete StockTransaction                       | `NotImplementedError: "Strict Ledger"`                               |
| 12.1.2 | Attempt to archive StockTransaction                      | `NotImplementedError: "Strict Ledger"`                               |
| 12.1.3 | Attempt to update StockTransaction                       | No explicit guard (only delete/archive overridden)                   |
| 12.1.4 | StockTransaction with quantity <= 0                      | DB CHECK constraint: `quantity > 0`                                  |
| 12.1.5 | Composite FK: (transfer_id, from_id, to_id)              | Ensures transaction can only belong to correct transfer route        |
| 12.1.6 | StockTransaction without corresponding StockTransferItem | Possible if manually created, no reverse FK from transaction to item |

### 12.2 Balance Trigger

| #      | Scenario                                            | Expected Behavior                                                      |
| ------ | --------------------------------------------------- | ---------------------------------------------------------------------- |
| 12.2.1 | INSERT into stock_transactions                      | Trigger: from_inventory balance -qty, to_inventory balance +qty        |
| 12.2.2 | First transaction for new (inventory, product) pair | Trigger: INSERT INTO inventory_balances ... ON CONFLICT DO UPDATE      |
| 12.2.3 | Balance becomes negative                            | Trigger allows it (no CHECK constraint on inventory_balances.quantity) |
| 12.2.4 | High-volume concurrent inserts                      | Trigger serializes per (inventory_id, product_id) via UPSERT           |

### 12.3 Transfer Document Integrity

| #      | Scenario                                          | Expected Behavior                                                              |
| ------ | ------------------------------------------------- | ------------------------------------------------------------------------------ |
| 12.3.1 | Transfer completed with items but no transactions | Possible if complete_transfer fails mid-loop                                   |
| 12.3.2 | Transfer has transactions but items were cleared  | Items and transactions are independent (no cascade from items to transactions) |
| 12.3.3 | StockTransferItem with quantity = 0               | DB CHECK: `quantity > 0` prevents this                                         |
| 12.3.4 | Transfer from_id != transaction from_id           | Composite FK prevents this                                                     |
| 12.3.5 | Orphaned DRAFT transfers                          | No cleanup mechanism, accumulate over time                                     |

---

## 13. Not Yet Implemented / Potential Gaps

### 13.1 Missing Business Scenarios

| #       | Gap                                                    | Description                                                                                                           |
| ------- | ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| 13.1.1  | **No transfer reversal/cancellation after completion** | Once COMPLETED, no way to reverse stock movements (manual correction via LOSS_WRITE_OFF + INVENTORY_FINDING required) |
| 13.1.2  | **No order cancellation reversal**                     | If order is delivered then cancelled, stock transfers and financial transactions remain (no auto-reversal)            |
| 13.1.3  | **No partial returns from client**                     | CLIENT_RETURN quantity equals delivered quantity (1:1), no mechanism for client to return fewer bottles               |
| 13.1.4  | **No inter-courier transfers**                         | Cannot transfer stock directly between two courier vehicles (must go through warehouse)                               |
| 13.1.5  | **No CLIENT -> VIRTUAL_LOSS**                          | Client cannot write off lost bottles (only WAREHOUSE/COURIER can)                                                     |
| 13.1.6  | **No equipment return from client**                    | Equipment delivered to client has no return mechanism (only containers have returnable_item_id)                       |
| 13.1.7  | **No multi-warehouse shift close**                     | close_shift always returns to `get_system_inventory(WAREHOUSE)` -- only one main warehouse                            |
| 13.1.8  | **No route sheet validation in load_truck**            | `route_sheet_id` in request but not validated against any route/trip model                                            |
| 13.1.9  | **No daily reconciliation report**                     | No endpoint to compare expected vs actual balances across all inventories                                             |
| 13.1.10 | **No batch delivery**                                  | Each order delivered individually, no bulk delivery for same courier                                                  |

### 13.2 Missing Validation Gaps

| #       | Gap                                                                        | Description                                                                     |
| ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| 13.2.1  | **Loss reason not persisted**                                              | `LossWriteOffRequest.reason` accepted but not stored in transfer or transaction |
| 13.2.2  | **No order state machine**                                                 | Status transitions not validated (e.g., CANCELLED -> DELIVERED is possible)     |
| 13.2.3  | **No duplicate product in transfer items**                                 | Same product_id can appear multiple times in one transfer's items               |
| 13.2.4  | **No max quantity limits**                                                 | Transfer items can have arbitrarily large quantities                            |
| 13.2.5  | **Cash_collected not validated against courier balance**                   | Shift close accepts any cash amount without checking courier account            |
| 13.2.6  | **DRAFT transfers never expire**                                           | Abandoned drafts accumulate indefinitely                                        |
| 13.2.7  | **No CANCELLED status transition for drafts**                              | CANCELLED status exists but no endpoint to cancel a draft                       |
| 13.2.8  | **`complete_transfer` uses ValueError instead of domain exceptions**       | Inconsistent with other services that use typed exceptions                      |
| 13.2.9  | **Admin tara capitalization accepts any product type**                     | No validation that capitalized products are actually CONTAINER type             |
| 13.2.10 | **Close shift reconciliation uses ValueError instead of domain exception** | Should use specific reconciliation error with details                           |

### 13.3 Scalability Concerns

| #      | Concern                                                  | Description                                                                          |
| ------ | -------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 13.3.1 | **VIRTUAL_VENDOR/VIRTUAL_LOSS balance grows infinitely** | Balance in `inventory_balances` for virtual inventories grows with every transaction |
| 13.3.2 | **No archival for old transactions**                     | Ledger grows indefinitely (by design, but may need partitioning)                     |
| 13.3.3 | **FOR UPDATE on popular warehouses**                     | High contention if many couriers load from same warehouse simultaneously             |
| 13.3.4 | **No batch operations for transfers**                    | Each item creates individual DB writes in a loop                                     |

---

## Appendix A: Complete Business Flow Scenarios

### A.1 Happy Path: Full Day Cycle

```
1. Morning:
   FACTORY_RECEIPT: VIRTUAL_VENDOR -> WAREHOUSE [200 water, 200 tara]
   COURIER_LOAD:    WAREHOUSE -> COURIER_A [30 water, 10 tara]
   COURIER_LOAD:    WAREHOUSE -> COURIER_B [25 water, 5 tara]

2. During Day (Courier A):
   Order #1 (CASH, 5 water):
     CLIENT_DELIVERY: COURIER_A -> CLIENT_1 [5 water]
     CLIENT_RETURN:   CLIENT_1 -> COURIER_A [5 tara]
     Revenue -> Client_1_Account [100000]
     Client_1_Account -> Courier_A_Account [100000]

   Order #2 (CARD, 3 water):
     CLIENT_DELIVERY: COURIER_A -> CLIENT_2 [3 water]
     CLIENT_RETURN:   CLIENT_2 -> COURIER_A [3 tara]
     Revenue -> Client_2_Account [60000]
     Client_2_Account -> Card_Account [60000, PENDING]

3. Loss during day:
   LOSS_WRITE_OFF: COURIER_A -> VIRTUAL_LOSS [1 water] (broken)

4. Evening (Courier A):
   -- Courier A balance: 21 water, 18 tara (30-5-3-1=21, 10+5+3=18)
   close_shift(returned=[21 water, 18 tara], cash=100000)
   COURIER_RETURN: COURIER_A -> WAREHOUSE [21 water, 18 tara]
   Courier_A_Account -> System_Cash [100000]
   COURIER_A.is_active = False
```

### A.2 New Client Onboarding

```
1. POST /backoffice/clients/onboard
   -> Create User (role=CLIENT_B2C)
   -> Create Identity (phone="+998901234567")
   -> Create Account (type=CLIENT)
   -> Create Inventory (type=CLIENT, name="Home Address")
   -> INITIAL_BALANCE: VIRTUAL_VENDOR -> CLIENT_INV [5 tara] (initial bottles)
   -> Create Order #1 (5 water, CASH)
```

### A.3 Edge Case: Client Orders More Than Available Tara

```
Client has: 3 tara at address A, 7 tara at address B
Client orders 5 water to address A:

Case 1 (capitalize_missing_tara=false):
  available = 3, required = 5, deficit = 2
  -> InsufficientTaraError (address B tara not considered)

Case 2 (capitalize_missing_tara=true):
  available = 3, required = 5, deficit = 2
  -> INITIAL_BALANCE: VIRTUAL_VENDOR -> CLIENT_A [2 tara]
  -> Order created with capitalization_applied=true
```

### A.4 Edge Case: Courier Runs Out of Stock Mid-Route

```
Courier loaded with 10 water bottles.
Delivers 10 to orders #1-#4.
Order #5 (3 water) status -> DELIVERED:
  -> InsufficientStockError (courier has 0 water)
  -> Order stays in previous status (ARRIVED)
  -> Admin must either: reassign to another courier, or cancel order
```

### A.5 Edge Case: Shift Close with Discrepancy

```
Courier system balance: [water: 5, tara: 15]
Courier physically returns: [water: 5, tara: 13]

Step 1: close_shift fails -- "Balance mismatch: tara system=15, returned=13"
Step 2: Admin creates LOSS_WRITE_OFF: COURIER -> VIRTUAL_LOSS [2 tara]
Step 3: Courier system balance: [water: 5, tara: 13]
Step 4: close_shift succeeds -- balances match
```

### A.6 Edge Case: Production Cycle

```
Warehouse has: [empty_bottle: 100, raw_water: 500L]

Step 1: PRODUCTION (WH_raw -> WH_finished):
  Items: [filled_water_19L: 50]
  -- Requires: 50 empty bottles consumed (separate tracking needed)
  -- Current system: single-direction transfer, no consumption tracking

Note: PRODUCTION is WH -> WH, but the system doesn't enforce
      that raw materials are consumed. This is a manual process.
```

### A.7 Edge Case: Concurrent Double-Spending

```
Warehouse has: [water: 10]

Thread 1: COURIER_LOAD (warehouse -> courier_A, 8 water)
Thread 2: COURIER_LOAD (warehouse -> courier_B, 8 water)

With FOR UPDATE lock:
  Thread 1 acquires lock, checks balance (10 >= 8), proceeds
  Thread 2 waits for lock
  Thread 1 commits, balance = 2
  Thread 2 acquires lock, checks balance (2 < 8), InsufficientStockError
```

---

## Appendix B: Error Code Reference

| Error Code                           | HTTP | When                                          |
| ------------------------------------ | ---- | --------------------------------------------- |
| `VIRTUAL_INVENTORY_MISSING`          | 500  | System startup, virtual warehouse not created |
| `INVENTORY_NOT_FOUND`                | 404  | Inventory ID not found or wrong type          |
| `TRANSFER_NOT_FOUND`                 | 404  | Transfer ID not found                         |
| `ROUTE_LOOP_DETECTED`                | 400  | from_id == to_id                              |
| `EMPTY_TRANSFER`                     | 422  | Transfer has no items on completion           |
| `INVALID_QUANTITY`                   | 422  | quantity <= 0                                 |
| `INSUFFICIENT_STOCK`                 | 409  | Source inventory has insufficient balance     |
| `INVALID_TRANSFER_STATUS`            | 409  | Operation not allowed for current status      |
| `TRANSFER_TYPE_MISMATCH`             | 409  | Wrong transfer type for the operation         |
| `INVENTORY_TYPE_MISMATCH`            | 409  | Wrong inventory type for route                |
| `PRODUCT_MISMATCH_IN_TRANSIT`        | 409  | Accepting unexpected product                  |
| `COURIER_ALREADY_ASSIGNED`           | 409  | Courier already has active transport          |
| `COURIER_ROUTE_MISMATCH`             | 409  | Vehicle not on route sheet                    |
| `STRICT_LEDGER_VIOLATION`            | 403  | Attempt to mutate ledger                      |
| `TARA_CAPITALIZATION_LIMIT_EXCEEDED` | 409  | Client exceeds deficit limit                  |
| `REVERSAL_NOT_ALLOWED`               | 403  | Transfer type cannot be reversed              |
| `INSUFFICIENT_TARA`                  | 409  | Client lacks returnable containers            |
| `EMPTY_CART`                         | 422  | Order has no items                            |
| `DELIVERY_QUANTITY_EXCEEDED`         | 409  | Actual delivery > ordered quantity            |
| `CANNOT_REMOVE_LAST_ITEM`            | 409  | Cannot empty an order                         |
| `INSUFFICIENT_FUNDS`                 | 409  | Financial account lacks balance               |

---

*Generated from codebase analysis on 2026-03-27. Covers all modules: inventory, orders, finances, catalog, users.*
