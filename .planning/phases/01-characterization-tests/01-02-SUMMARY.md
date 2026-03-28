---
phase: 01-characterization-tests
plan: 02
subsystem: testing
tags: [pytest, httpx, characterization-test, warehouse-pickup, walk-in-sale, loss-writeoff]

requires:
  - phase: 01-characterization-tests/plan-01
    provides: "Savepoint-isolated test infrastructure, shared integration fixtures"
provides:
  - "TEST-02: Warehouse pickup characterization test passing end-to-end"
  - "TEST-03: Walk-in sale characterization test with LOSS_WRITE_OFF verification"
affects: []

tech-stack:
  added: []
  patterns:
    - "capitalize_missing_tara=True for warehouse sale tests (tara exchange requires pre-existing client tara)"
    - "Delta assertions for system accounts (pre-state balance capture before API calls)"

key-files:
  created:
    - tests/integration/test_warehouse_pickup.py
    - tests/integration/test_walkin_sale.py
  modified: []

key-decisions:
  - "Used capitalize_missing_tara=True in warehouse sale requests because tara exchange validation rejects orders when client has no tara"
  - "Walk-in test uses system_entities walkin fixtures (walkin_inventory, walkin_account) instead of creating new entities"
  - "Asserted virtual_loss inventory balance to verify LOSS_WRITE_OFF actually moved items out of walk-in inventory"

patterns-established:
  - "Warehouse sale test pattern: POST /warehouse-sale with clientId + complete-pickup, then assert stock + financial balances"
  - "Walk-in test pattern: POST /warehouse-sale without clientId, verify LOSS_WRITE_OFF clears walkin inventory to 0"
  - "System account delta assertions: capture balance before API calls, assert (after - before) == expected_delta"

requirements-completed: [TEST-02, TEST-03]

duration: 7min
completed: 2026-03-28
---

# Phase 01 Plan 02: Warehouse Pickup + Walk-in Sale Tests Summary

**Characterization tests for warehouse pickup (TEST-02) and walk-in sale with LOSS_WRITE_OFF cleanup (TEST-03), both asserting HTTP responses and ledger balances**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-28T05:10:32Z
- **Completed:** 2026-03-28T05:17:26Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- TEST-02 passes: warehouse sale (201) + complete-pickup (200) with stock and financial balance assertions
- TEST-03 passes: anonymous walk-in sale + pickup with LOSS_WRITE_OFF verification clearing walk-in inventory to 0
- All 4 integration tests pass together (delivery + warehouse pickup + walk-in sale + courier shift close)
- Savepoint rollback verified: repeated runs produce identical results

## Task Commits

Each task was committed atomically:

1. **Task 1: Write warehouse pickup test (TEST-02)** - `8287160` (test)
2. **Task 2: Write walk-in sale test (TEST-03)** - `b6af9ba` (test)

## Files Created/Modified
- `tests/integration/test_warehouse_pickup.py` - TEST-02: warehouse pickup flow with cash payment, tara exchange, and balance assertions
- `tests/integration/test_walkin_sale.py` - TEST-03: anonymous walk-in sale with LOSS_WRITE_OFF cleanup and virtual_loss verification

## Decisions Made
- Used `capitalize_missing_tara: True` in warehouse sale requests because the tara exchange validation in `create_warehouse_sale()` rejects orders when the client inventory has no tara balance. This matches the delivery test pattern from Plan 01.
- Walk-in test reuses `system_entities` fixture for walkin_user, walkin_inventory, and walkin_account (already created by `init_data()`) instead of creating new entities.
- Asserted `virtual_loss` inventory balance to verify the LOSS_WRITE_OFF transfer actually moved items out of the walk-in inventory, not just decremented it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Tara exchange validation requires capitalize_missing_tara**
- **Found during:** Task 1 (warehouse pickup test, first run)
- **Issue:** POST /warehouse-sale returned 409 INSUFFICIENT_TARA because the client has no tara balance and `capitalize_missing_tara` defaults to False
- **Fix:** Added `"capitalize_missing_tara": True` to the JSON body for both warehouse pickup and walk-in sale tests
- **Files modified:** tests/integration/test_warehouse_pickup.py, tests/integration/test_walkin_sale.py
- **Verification:** Both tests pass with 201 response
- **Committed in:** 8287160, b6af9ba

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor adjustment to request body. The plan's sample code omitted the `capitalize_missing_tara` field. No scope creep.

## Issues Encountered
None beyond the tara validation issue documented above.

## Known Stubs
None - all data flows are wired end-to-end.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 4 characterization tests (TEST-01 through TEST-04) now pass
- Phase 01 is complete pending Plan 03 (courier shift close) if running in parallel
- Test infrastructure and shared fixtures are proven stable across all business flows

---
*Phase: 01-characterization-tests*
*Completed: 2026-03-28*
