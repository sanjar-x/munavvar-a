# Phase 1: Characterization Tests - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Lock existing business flows with tests before any refactoring. Four flows are covered: order delivery fulfillment, warehouse pickup, walk-in sale, and courier shift close. These tests document current behavior as-is — they are refactoring guardrails, not correctness proofs.

</domain>

<decisions>
## Implementation Decisions

### Test Level
- **D-01:** Tests operate at API level — full HTTP requests via httpx AsyncClient against the FastAPI app
- **D-02:** All 4 flows (delivery fulfillment, warehouse pickup, walk-in sale, courier shift close) are tested through their actual API endpoints
- **D-03:** Authentication in tests uses direct token creation via `create_access_token()` in fixtures — no login endpoint calls, no dependency overrides

### Database Strategy
- **D-04:** Tests run against the existing connected dev PostgreSQL database — no separate test database
- **D-05:** Each test is wrapped in a transaction that rolls back after completion for data isolation
- **D-06:** PG triggers (update_account_balances, update_inventory_balances) fire within the test transaction, exercising real ledger enforcement

### Test Data Setup
- **D-07:** Dedicated pytest fixtures create exactly the entities each flow needs (products, users, inventories, orders, accounts)
- **D-08:** Fixtures create data via ORM models directly (session.add), not through service methods — decouples fixture setup from service-layer correctness
- **D-09:** Seeder class is used as a reference for what entities to create but is not called directly in tests

### Assertion Depth
- **D-10:** Each flow asserts HTTP response (status code + body structure) AND verifies final state of inventory_balances and accounts.balance after the flow completes
- **D-11:** Balance assertions use exact expected amounts — fixture-controlled prices make amounts deterministic
- **D-12:** Tests do NOT assert individual stock_transaction or transaction rows — only the materialized balances that PG triggers compute

### Claude's Discretion
- Exact fixture composition and sharing strategy (per-test vs shared setup fixtures)
- Test file organization within `tests/` directory
- Whether to use polyfactory for any fixture data generation
- Error message assertion strategy (assert on error_code, not Russian message text)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Business flows under test
- `src/modules/orders/services.py` — Contains all 4 flows: `_handle_order_fulfillment()`, `_handle_warehouse_pickup()`, walk-in sale logic, and courier shift close
- `src/application/order/` — Application-layer order orchestration (cross-domain)
- `src/application/inventories/` — Inventory orchestration for stock transfers

### Ledger enforcement
- `src/infrastructure/database/scripts/` — PG trigger SQL source for balance materialization
- `alembic/versions/c650cec7ccb0_triggers.py` — Trigger migration that installs balance enforcement

### API endpoints exercised
- `src/api/v1/backoffice/orders.py` — Backoffice order endpoints (delivery, pickup, walk-in)
- `src/api/v1/backoffice/couriers.py` — Courier shift close endpoint (if exists)

### Test infrastructure
- `tests/conftest.py` — Currently empty; needs full fixture setup
- `src/core/seeder.py` — Reference for entity creation patterns and relationships
- `src/core/init.py` — System initialization (system user, accounts, virtual inventories)

### Data models
- `src/infrastructure/database/models.py` — Model registry (all SQLAlchemy models)
- `src/infrastructure/database/base.py` — BaseModel with UUIDv7, soft-delete, timestamps

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `create_access_token()` in `src/core/security/jwt.py` — Can be used directly in test fixtures for auth
- `Seeder` class in `src/core/seeder.py` — Reference for entity creation order and relationships
- `async_session_maker` in `src/infrastructure/database/session.py` — Session factory for test DB connection
- `BaseModel.metadata` — SQLAlchemy metadata for table introspection

### Established Patterns
- All async: pytest-asyncio with `asyncio_mode = "auto"` — no decorators needed
- UoW pattern: Services use `async with self.uow` for transaction boundaries
- Error format: `{"error": {"code": "ERROR_CODE", "message": "...", "details": {...}}}`
- Soft delete: `is_active=True` filter on all queries — tests should create active entities

### Integration Points
- FastAPI app instance: `src/main.py` imports from `src/api/server.py`
- httpx ASGITransport wraps the app for in-process HTTP testing
- `init_data()` in `src/core/init.py` creates system accounts and virtual inventories needed by business flows

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-characterization-tests*
*Context gathered: 2026-03-28*
