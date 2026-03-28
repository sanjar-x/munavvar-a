---
phase: 01-characterization-tests
plan: 01
subsystem: testing
tags: [pytest, httpx, sqlalchemy-async, asyncpg, savepoint, characterization-test]

requires: []
provides:
  - "Savepoint-isolated test infrastructure (engine, session factory, httpx client, auth helpers)"
  - "Integration conftest with shared entity fixtures (users, products, inventories, accounts)"
  - "TEST-01: Delivery fulfillment characterization test passing end-to-end"
affects: [01-02-PLAN, 01-03-PLAN]

tech-stack:
  added: []
  patterns:
    - "Per-function engine to avoid pytest-asyncio event loop mismatch"
    - "Monkeypatch async_session_maker across all dependency modules"
    - "values_callable on SA Enum types for asyncpg native enum compat"

key-files:
  created:
    - tests/conftest.py
    - tests/integration/conftest.py
    - tests/integration/test_delivery_fulfillment.py
  modified:
    - pyproject.toml
    - src/modules/finances/enums.py
    - src/modules/finances/models.py

key-decisions:
  - "Function-scoped engine (not session-scoped) to match pytest-asyncio event loop per test"
  - "Monkeypatch all 9 modules that import async_session_maker (not just session module)"
  - "System entities queried by Role.SYSTEM not SYSTEM_USER_ID constant (ID mismatch in dev DB)"
  - "DB finance enum labels migrated to lowercase for asyncpg StrEnum compatibility"

patterns-established:
  - "Savepoint rollback: per-function engine + connection.begin() + session_factory bound to connection"
  - "Auth helper: make_auth_headers(user_id, role) using create_access_token directly"
  - "Fixture data via ORM session.add + flush (not service methods)"
  - "Balance assertions via fresh SELECT queries (not cached ORM objects)"

requirements-completed: [TEST-01]

duration: 40min
completed: 2026-03-28
---

# Phase 01 Plan 01: Test Infrastructure + Delivery Fulfillment Summary

**Savepoint-isolated test infrastructure with httpx client and first passing delivery fulfillment characterization test (TEST-01)**

## Performance

- **Duration:** 40 min
- **Started:** 2026-03-28T04:27:20Z
- **Completed:** 2026-03-28T05:07:20Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- Full test infrastructure: savepoint rollback, session factory monkeypatch, httpx AsyncClient, auth helpers
- Shared integration fixtures: system entities, products, users, inventories, accounts, stock loading helper
- TEST-01 passes: create order (201) -> assign courier (200) -> deliver (200) with balance assertions
- Savepoint rollback verified: running test twice produces identical results (no data leakage)

## Task Commits

Each task was committed atomically:

1. **Task 1: Build root test conftest** - `dfa4061` (test)
2. **Task 2: Build integration conftest** - `7ebb8e8` (test)
3. **Task 2.5: Fix finance enum asyncpg compat** - `a271f42` (fix)
4. **Task 3: Delivery fulfillment test** - `3f4552b` (test)

## Files Created/Modified
- `tests/conftest.py` - Root conftest with engine, session factory, db_session, httpx client, auth helper
- `tests/integration/conftest.py` - Shared fixtures: system_entities, products, users, inventories, accounts, load_stock, credit_account
- `tests/integration/test_delivery_fulfillment.py` - TEST-01: full delivery fulfillment flow with balance assertions
- `pyproject.toml` - Added pythonpath=["."], changed asyncio_default_fixture_loop_scope to "function"
- `src/modules/finances/enums.py` - AccountType and TransactionStatus values unchanged (were already lowercase)
- `src/modules/finances/models.py` - Added values_callable to Enum types for asyncpg native enum compat

## Decisions Made
- Used per-function engine creation instead of session-scoped to avoid pytest-asyncio event loop mismatch between fixture and test scopes
- Monkeypatched async_session_maker on 9 separate module imports (not just the session module) because Python `from X import Y` creates local name bindings
- Queried system user by `Role.SYSTEM` instead of `SYSTEM_USER_ID` constant because dev DB has `settings.SYSTEM_USER_ID` (UUID int=0) not `constants.SYSTEM_USER_ID` (UUID ...001)
- Used `raise_app_exceptions=False` on ASGITransport to prevent unhandled exceptions from breaking test teardown

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pytest pythonpath missing**
- **Found during:** Task 1 (Root conftest)
- **Issue:** `from src.*` imports failed in pytest because project root not on sys.path
- **Fix:** Added `pythonpath = ["."]` to pyproject.toml [tool.pytest.ini_options]
- **Files modified:** pyproject.toml
- **Verification:** `uv run pytest --co` succeeds
- **Committed in:** 3f4552b

**2. [Rule 3 - Blocking] Event loop mismatch between fixtures and tests**
- **Found during:** Task 3 (Test execution)
- **Issue:** `asyncio_default_fixture_loop_scope = "session"` caused fixtures to run in session loop while tests ran in function loop, producing `attached to a different loop` errors
- **Fix:** Changed to `asyncio_default_fixture_loop_scope = "function"` and made engine per-function
- **Files modified:** pyproject.toml, tests/conftest.py
- **Verification:** Minimal test with DB query passes
- **Committed in:** 3f4552b

**3. [Rule 3 - Blocking] Session factory monkeypatch insufficient**
- **Found during:** Task 3 (Test execution)
- **Issue:** Patching only `session_module.async_session_maker` didn't affect UoW constructors because dependency modules import it directly (`from src...session import async_session_maker`)
- **Fix:** Monkeypatched async_session_maker on all 9 importing modules
- **Files modified:** tests/conftest.py
- **Verification:** API calls use test session factory (verified via echo logs)
- **Committed in:** 3f4552b

**4. [Rule 1 - Bug] asyncpg lowercases StrEnum values for native PG enums**
- **Found during:** Task 3 (Delivery endpoint returns 500)
- **Issue:** asyncpg's native enum codec lowercases string values when binding parameters, but DB had UPPERCASE labels and SQLAlchemy Enum used .name (UPPERCASE) instead of .value
- **Fix:** Added `values_callable=lambda e: [m.value for m in e]` to SA Enum types and migrated DB enum labels to lowercase via `ALTER TYPE RENAME VALUE`
- **Files modified:** src/modules/finances/enums.py, src/modules/finances/models.py
- **Verification:** INSERT and SELECT with TransactionStatus and AccountType both succeed
- **Committed in:** a271f42

**5. [Rule 1 - Bug] SYSTEM_USER_ID constant mismatch with dev DB**
- **Found during:** Task 2 fixture setup (system_entities)
- **Issue:** `constants.SYSTEM_USER_ID` is UUID ...001 but `init_data()` uses `settings.SYSTEM_USER_ID` which defaults to UUID int=0 (all zeros)
- **Fix:** Query system user by `Role.SYSTEM` instead of constant ID
- **Files modified:** tests/integration/conftest.py
- **Verification:** system_entities fixture finds system user and all related entities
- **Committed in:** 7ebb8e8, 3f4552b

---

**Total deviations:** 5 auto-fixed (2 bugs, 3 blocking)
**Impact on plan:** All auto-fixes necessary for test infrastructure to function. The enum fix (deviation 4) is a genuine production bug that would affect any financial transaction creation. No scope creep.

## Issues Encountered
- SQLAlchemy 2.1.0b1 + asyncpg 0.31.0 + StrEnum interaction: asyncpg's native enum codec lowercases parameter values, while SQLAlchemy's Enum type uses .name for lookup/binding. Required both DB migration and SA type config change. Documented as pattern for future reference.

## Known Stubs
None - all data flows are wired end-to-end.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Test infrastructure is ready for TEST-02 (warehouse pickup), TEST-03 (walk-in sale), TEST-04 (courier shift close)
- All shared fixtures (products, users, inventories, accounts, load_stock) are reusable
- The enum fix may need to be applied to other enum types if they have similar UPPERCASE DB labels

---
*Phase: 01-characterization-tests*
*Completed: 2026-03-28*
