# Phase 1: Characterization Tests - Research

**Researched:** 2026-03-28
**Domain:** Async Python testing (pytest-asyncio + httpx + SQLAlchemy async + FastAPI TestClient + PostgreSQL triggers)
**Confidence:** HIGH

## Summary

Phase 1 locks four existing business flows with API-level characterization tests before any refactoring begins. The test infrastructure must be built from scratch -- `tests/conftest.py` is empty, `tests/factories/`, `tests/integration/`, and `tests/unit/` are empty directories. The four flows are: (1) order delivery fulfillment, (2) warehouse pickup, (3) walk-in sale, and (4) courier shift close. All four exercise the dual-ledger system (stock + financial) and depend on PG triggers firing within the test transaction.

The central technical challenge is the **transaction isolation strategy**. Decision D-05 requires each test to wrap in a transaction that rolls back after completion. However, the application code itself opens its own sessions via `async_session_maker` (through UoW pattern), and PG triggers fire on `INSERT` to `stock_transactions` and `transactions` tables. The test must ensure that the application's session is the test's session (nested inside a savepoint), so that trigger-generated balance updates are visible to assertions and everything rolls back cleanly. This is a well-established pattern for FastAPI + SQLAlchemy async testing, implemented by overriding `async_session_maker` dependency with a fixture that returns a nested (savepoint) session.

**Primary recommendation:** Build a `conftest.py` with a session-scoped engine, function-scoped savepoint sessions, an httpx `AsyncClient` wired to the FastAPI app with overridden session factory, and dedicated fixture functions that create test entities via direct ORM inserts. Each test calls the real API endpoint and asserts both HTTP response and ledger balances via direct SQL queries on the same session.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Tests operate at API level -- full HTTP requests via httpx AsyncClient against the FastAPI app
- **D-02:** All 4 flows (delivery fulfillment, warehouse pickup, walk-in sale, courier shift close) are tested through their actual API endpoints
- **D-03:** Authentication in tests uses direct token creation via `create_access_token()` in fixtures -- no login endpoint calls, no dependency overrides
- **D-04:** Tests run against the existing connected dev PostgreSQL database -- no separate test database
- **D-05:** Each test is wrapped in a transaction that rolls back after completion for data isolation
- **D-06:** PG triggers (update_account_balances, update_inventory_balances) fire within the test transaction, exercising real ledger enforcement
- **D-07:** Dedicated pytest fixtures create exactly the entities each flow needs (products, users, inventories, orders, accounts)
- **D-08:** Fixtures create data via ORM models directly (session.add), not through service methods -- decouples fixture setup from service-layer correctness
- **D-09:** Seeder class is used as a reference for what entities to create but is not called directly in tests
- **D-10:** Each flow asserts HTTP response (status code + body structure) AND verifies final state of inventory_balances and accounts.balance after the flow completes
- **D-11:** Balance assertions use exact expected amounts -- fixture-controlled prices make amounts deterministic
- **D-12:** Tests do NOT assert individual stock_transaction or transaction rows -- only the materialized balances that PG triggers compute

### Claude's Discretion
- Exact fixture composition and sharing strategy (per-test vs shared setup fixtures)
- Test file organization within `tests/` directory
- Whether to use polyfactory for any fixture data generation
- Error message assertion strategy (assert on error_code, not Russian message text)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEST-01 | Characterization tests for order delivery fulfillment flow (stock + financial atomicity) | Covered by `_handle_order_fulfillment()` in `BaseOrderService.update_status()` -- API endpoint `PATCH /api/v1/backoffice/orders/{orderId}/status` with `newStatus: "delivered"`. Creates CLIENT_DELIVERY transfer (courier->client), CLIENT_RETURN transfer (tara), and financial settlement (Revenue->Client + Client->Courier for cash). Fixture needs: admin user, courier with inventory+account loaded with stock, client with inventory+account, products (water+tara), order in ASSIGNED status with courier assigned. |
| TEST-02 | Characterization tests for warehouse pickup flow | Covered by `complete_pickup()` -> `_handle_warehouse_pickup()`. Two-step flow: (1) `POST /api/v1/backoffice/orders/warehouse-sale` creates order, then (2) `PATCH /api/v1/backoffice/orders/{orderId}/complete-pickup` executes stock+financial settlement. Creates WAREHOUSE_SALE transfer (warehouse->client), WAREHOUSE_TARA_RETURN (client->warehouse), and pickup settlement (Revenue->Client + Client->Cash). Fixture needs: admin user, warehouse inventory loaded with stock, registered client with inventory+account, products. |
| TEST-03 | Characterization tests for walk-in sale flow | Same endpoints as TEST-02 but with `clientId` omitted (defaults to WALKIN_USER_ID). Additional behavior: after pickup completion, creates LOSS_WRITE_OFF transfer (client->virtual_loss) to clear walk-in inventory. Fixture needs: admin user, warehouse inventory loaded with stock, walk-in user (WALKIN_USER_ID) with inventory+account already initialized by `init_data()`, products. |
| TEST-04 | Characterization tests for courier shift close flow | Covered by `ShiftService.close_shift()`. API endpoint `POST /api/v1/backoffice/shifts/close`. Performs: (1) inventory reconciliation (system qty must match returned qty), (2) COURIER_RETURN transfer (courier->main warehouse), (3) cash collection (courier account -> system cash account). Fixture needs: admin/storekeeper user, courier with inventory+account loaded with known stock and account balance from prior deliveries, main warehouse inventory, products. |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 9.0.2 | Test runner | Already installed, configured in pyproject.toml |
| pytest-asyncio | 1.3.0 | Async test support | Already installed, `asyncio_mode = "auto"` configured |
| httpx | 0.28.1 | Async HTTP test client | Already installed, standard for FastAPI API-level testing with ASGITransport |
| SQLAlchemy | 2.1.0b1 (async) | ORM + session management | Core project dependency, needed for fixture data creation and balance assertions |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| polyfactory | 3.3.0 | Test data factory generation | Already installed but NOT recommended for this phase -- fixtures need precise control over entity relationships and amounts for deterministic balance assertions |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Direct ORM fixtures | polyfactory | polyfactory generates random data; characterization tests need exact, deterministic values for balance math |
| httpx AsyncClient | FastAPI TestClient (sync) | TestClient is sync; this project is fully async, httpx ASGITransport is the standard async approach |

## Architecture Patterns

### Recommended Test Structure
```
tests/
    conftest.py                          # Session-scoped engine, function-scoped savepoint, AsyncClient, auth helpers
    integration/
        conftest.py                      # Shared fixtures for all integration tests (products, system entities)
        test_delivery_fulfillment.py     # TEST-01: Order delivery flow
        test_warehouse_pickup.py         # TEST-02: Warehouse pickup flow
        test_walkin_sale.py              # TEST-03: Walk-in sale flow
        test_courier_shift_close.py      # TEST-04: Courier shift close flow
```

### Pattern 1: Savepoint-Based Transaction Isolation

**What:** Each test runs inside a database SAVEPOINT. The outer transaction is never committed -- it rolls back at test teardown, leaving the dev database unchanged.

**When to use:** Always -- this is the only pattern that satisfies D-04 (use dev DB), D-05 (rollback isolation), and D-06 (triggers fire within transaction).

**How it works:**

1. A session-scoped fixture creates a raw asyncpg `Connection` and begins a transaction (BEGIN).
2. A function-scoped fixture creates a SAVEPOINT on that connection.
3. The application's `async_session_maker` is monkeypatched to return sessions bound to this savepoint connection.
4. The FastAPI app is created fresh (or the session factory is overridden via app dependency overrides).
5. After each test, the SAVEPOINT is rolled back. After all tests, the outer transaction is rolled back.

**Critical detail:** PG triggers fire on the INSERT within the savepoint. Trigger-computed balances (on `inventory_balances` and `accounts`) are visible to queries on the same connection. When the savepoint rolls back, all trigger side-effects are also rolled back.

**Example (conftest.py core pattern):**

```python
# tests/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings
from src.core.security.jwt import create_access_token
from src.core.security.permissions import ROLE_SCOPES
from src.modules.users.enums import Role


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def engine():
    """Session-scoped engine -- shared across all tests."""
    eng = create_async_engine(
        url=settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )
    yield eng
    await eng.dispose()


@pytest.fixture(scope="function")
async def db_session(engine):
    """
    Function-scoped session with savepoint rollback.
    Each test gets a clean savepoint that rolls back on teardown.
    """
    async with engine.connect() as conn:
        # Begin outer transaction (never committed)
        trans = await conn.begin()
        # Create savepoint-aware session
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            autoflush=False,
        )
        # Begin a nested savepoint
        nested = await conn.begin_nested()

        yield session

        # Rollback everything
        await session.close()
        await trans.rollback()


@pytest.fixture(scope="function")
async def client(db_session):
    """
    httpx AsyncClient wired to the FastAPI app with
    session factory overridden to use the test session.
    """
    from src.api.server import create_app
    from src.infrastructure.database import session as session_module

    app = create_app()

    # Monkeypatch the session factory to return our test session
    original_factory = session_module.async_session_maker

    def test_session_factory():
        return db_session

    session_module.async_session_maker = test_session_factory

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as ac:
        yield ac

    session_module.async_session_maker = original_factory
```

**Important caveats with this pattern:**

The `BaseSQLAlchemyUoW.__aenter__` calls `self._session_factory()` which normally returns a new `AsyncSession`. When monkeypatched, it must return the test's savepoint-bound session. However, the UoW's `__aexit__` calls `session.close()` which would close the test session prematurely. The solution: instead of returning the raw session, return a wrapper or use `async_sessionmaker` bound to the test connection so each `()` call creates a new session on the same connection/savepoint.

**Refined approach:**

```python
@pytest.fixture(scope="function")
async def db_connection(engine):
    """Raw connection with outer transaction."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        yield conn
        await trans.rollback()


@pytest.fixture(scope="function")
async def session_factory(db_connection):
    """
    Session factory that creates sessions on the test connection.
    Each session.begin_nested() creates a savepoint.
    The UoW can open/close sessions freely -- they all run
    on the same connection and see each other's writes.
    """
    factory = async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    return factory


@pytest.fixture(scope="function")
async def db_session(session_factory):
    """Direct session for fixture data setup and balance assertions."""
    async with session_factory() as session:
        yield session
```

This refined approach lets the UoW create/close sessions normally (each UoW `__aenter__` calls `session_factory()` and gets a new `AsyncSession` bound to the same connection), while the test fixture also holds a session for data setup and assertions.

### Pattern 2: Auth Token Fixtures (D-03)

**What:** Create JWT tokens directly via `create_access_token()` with the correct `sub` (user UUID) and `scopes` for the role.

**When to use:** Every test that calls an authenticated endpoint.

```python
def make_auth_headers(user_id: uuid.UUID, role: Role) -> dict[str, str]:
    """Create Bearer token headers for a test user."""
    scopes = ROLE_SCOPES.get(role, [])
    token = create_access_token(
        payload_data={
            "sub": str(user_id),
            "scopes": scopes,
        }
    )
    return {"Authorization": f"Bearer {token}"}
```

**Key insight:** The `get_current_user` dependency (auth/dependencies.py) calls `user_service.get(id=user_id)` to load the user from DB. This means the test user MUST exist in the database (via fixture) for the auth dependency to succeed. The token just bypasses the login flow.

### Pattern 3: ORM Direct Fixture Data (D-08)

**What:** Create all test entities via `session.add()` + `session.flush()`, not through service methods.

**When to use:** All fixture setup for all four flows.

**Entity creation order (respects FK constraints):**

1. **System entities** (already exist in dev DB from `init_data()`): System User, Revenue/Cash/Card/Bank accounts, VIRTUAL_VENDOR, VIRTUAL_LOSS, Walk-in User + inventory + account
2. **Products**: Container (tara), Water (with `returnable_item_id` -> container), Equipment
3. **Users**: Admin (Role.ADMIN), Courier (Role.COURIER), Client (Role.CLIENT_B2C)
4. **Identities**: One per user (AuthProvider.LOCAL, phone number, password_hash)
5. **Accounts**: Client account (AccountType.CLIENT), Courier account (AccountType.COURIER)
6. **Inventories**: Warehouse (InventoryType.WAREHOUSE), Courier van (InventoryType.COURIER), Client inventory (InventoryType.CLIENT)
7. **Stock loading** (for flows that need pre-existing stock): StockTransfer + StockTransferItem + StockTransaction from VIRTUAL_VENDOR to warehouse/courier -- triggers will auto-create inventory_balances rows
8. **Orders** (for delivery fulfillment test): Order + OrderItems in correct status

### Pattern 4: Balance Assertion via Direct SQL

**What:** After the API call, query `inventory_balances` and `accounts` tables directly on the test session to verify trigger-computed values.

```python
from sqlalchemy import select
from src.infrastructure.database.models import Account, Balance

# Verify inventory balance
result = await db_session.execute(
    select(Balance.quantity).where(
        Balance.inventory_id == courier_inv.id,
        Balance.product_id == water_product.id,
    )
)
actual_qty = result.scalar_one()
assert actual_qty == expected_qty

# Verify financial balance
result = await db_session.execute(
    select(Account.balance).where(Account.id == client_account.id)
)
actual_balance = result.scalar_one()
assert actual_balance == expected_balance
```

**Critical:** After the API call completes (which committed via UoW), the test session must `await db_session.execute(select(...))` to read the committed state. Since both the API session and the test assertion session are on the same connection (same transaction), the committed-within-savepoint data is visible.

### Anti-Patterns to Avoid
- **Overriding FastAPI dependencies for auth:** D-03 explicitly forbids this. Use real `create_access_token()` with real scopes.
- **Using service methods in fixtures:** D-08 requires ORM-direct fixture setup. Service methods may have side effects or validation that interferes with test data setup.
- **Asserting individual ledger rows:** D-12 says only assert materialized balances, not the individual stock_transaction or transaction entries.
- **Using `scope="session"` for data fixtures:** Function scope is required for data isolation (D-05). Each test creates its own entities inside its own savepoint.
- **Calling `init_data()` in tests:** The system entities (system user, accounts, virtual inventories, walk-in user) already exist in the dev database. Tests just need to query for them.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Transaction isolation | Custom begin/rollback wrapper | SQLAlchemy `connection.begin()` + `begin_nested()` | Handles savepoints, nested transactions, and trigger visibility correctly |
| JWT token creation | Manual JWT encoding in tests | `create_access_token()` from `src.core.security.jwt` | Already handles all claims (sub, scopes, exp, iat, jti) correctly |
| HTTP client setup | Manual ASGI app invocation | `httpx.AsyncClient` with `ASGITransport` | Standard FastAPI testing approach, handles async correctly |
| Scope computation for roles | Hardcoding scope strings | `ROLE_SCOPES[role]` from `src.core.security.permissions` | Source of truth for what scopes each role has |

## Common Pitfalls

### Pitfall 1: Session Factory Monkeypatching Scope

**What goes wrong:** If `async_session_maker` is monkeypatched at module import time, it affects all tests globally. If patched too late, the app creates sessions on the real DB, bypassing the test transaction.

**Why it happens:** `async_session_maker` is a module-level global in `src/infrastructure/database/session.py`. The UoW classes import it indirectly through their dependency chain.

**How to avoid:** Monkeypatch it on the `session_module` object BEFORE creating the `AsyncClient`, and restore it after. The `BaseSQLAlchemyUoW.__init__` receives `session_factory` as a constructor parameter -- but the dependency injection (in `dependencies.py`) calls `BaseOrderUnitOfWork(session_factory=async_session_maker)` at request time, so the monkeypatch on the module attribute is picked up.

**Warning signs:** Tests pass but data persists in the dev database after test run.

### Pitfall 2: UoW Session Close vs Test Session Lifecycle

**What goes wrong:** The UoW's `__aexit__` calls `session.close()`. If the monkeypatched factory returns the exact same session object, closing it kills the test session.

**Why it happens:** `BaseSQLAlchemyUoW.__aenter__` calls `self._session = self._session_factory()`. If the factory returns a singleton session, closing it in `__aexit__` breaks subsequent assertions.

**How to avoid:** Use `async_sessionmaker(bind=connection)` as the factory. Each `factory()` call returns a NEW `AsyncSession` bound to the same connection. The UoW can freely close its sessions without affecting the test fixture's session.

**Warning signs:** `sqlalchemy.exc.InvalidRequestError: This Session's transaction has been rolled back due to a previous exception` or `Session is closed`.

### Pitfall 3: expire_on_commit and Stale Data After API Call

**What goes wrong:** After the API endpoint commits (via `uow.commit()`), the test session's loaded ORM objects may be stale. Assertions on `account.balance` return the pre-commit value.

**Why it happens:** `expire_on_commit=False` prevents auto-expiry, but the test session loaded the data BEFORE the API's session committed. The API session and test session are different `AsyncSession` instances on the same connection.

**How to avoid:** For balance assertions, always use a fresh `SELECT` query after the API call returns -- never rely on previously loaded ORM objects. Use `await db_session.execute(select(Account.balance).where(...))` to get the trigger-updated value.

**Warning signs:** Assertions fail with "expected 20000, got 0" -- the pre-trigger value.

### Pitfall 4: System Entity IDs are Fixed Constants

**What goes wrong:** Tests create duplicate system entities (system user, walk-in user) that conflict with the ones already in the dev database.

**Why it happens:** `init_data()` creates entities with fixed UUIDs (`SYSTEM_USER_ID`, `WALKIN_USER_ID`). The dev database already has these.

**How to avoid:** Never create system entities in test fixtures. Query for them: `select(User).where(User.id == SYSTEM_USER_ID)`. They already exist from `init_data()` which runs at app startup.

**Warning signs:** IntegrityError on users table during fixture setup.

### Pitfall 5: Trigger-Generated Balances and the ORDER BY Trick

**What goes wrong:** Deadlock when the inventory balance trigger inserts two rows in different order across concurrent tests.

**Why it happens:** The `update_inventory_balances()` trigger does `ORDER BY v.inv_id` in its UPSERT to prevent deadlocks during normal operation. In tests, since each test runs in its own savepoint on a single connection, true concurrency deadlocks are not a concern.

**How to avoid:** Not an issue in the test context since tests run sequentially on a single connection. But be aware that `FOR UPDATE` locks in the application code (e.g., `with_for_update=True` on inventory queries) acquire row-level locks that are released at savepoint rollback.

### Pitfall 6: StockTransaction Composite Foreign Key

**What goes wrong:** Inserting a `StockTransaction` fails with FK violation because `transfer_id + from_id + to_id` must match a row in `stock_transfers`.

**Why it happens:** `StockTransaction` has a composite FK constraint (`fk_stock_transaction_strict_route`) referencing `stock_transfers(id, from_id, to_id)`. The `from_id` and `to_id` on the transaction must exactly match the transfer's `from_id` and `to_id`.

**How to avoid:** When creating stock transactions in fixtures (for pre-loading courier inventory), always use the same `from_id` and `to_id` as the parent transfer.

**Warning signs:** `IntegrityError: insert or update on table "stock_transactions" violates foreign key constraint "fk_stock_transaction_strict_route"`.

## Code Examples

### API Endpoints for Each Flow

**TEST-01: Delivery Fulfillment**
```python
# Step 1: Create order (via API or fixture -- API is cleaner for characterization)
# Step 2: Assign courier
response = await client.patch(
    f"/api/v1/backoffice/orders/{order_id}/assign",
    json={"courierId": str(courier_id)},
    headers=admin_headers,
)
# Step 3: Update status to DELIVERED (triggers fulfillment)
response = await client.patch(
    f"/api/v1/backoffice/orders/{order_id}/status",
    json={"newStatus": "delivered"},
    headers=admin_headers,
)
assert response.status_code == 200
data = response.json()
assert data["status"] == "delivered"
```

**TEST-02: Warehouse Pickup**
```python
# Step 1: Create warehouse sale order
response = await client.post(
    "/api/v1/backoffice/orders/warehouse-sale",
    params={"clientId": str(client_id)},
    json={
        "warehouse_id": str(warehouse_id),
        "items": [{"product_id": str(water_id), "quantity": 2}],
    },
    headers=admin_headers,
)
assert response.status_code == 201
order_id = response.json()["id"]

# Step 2: Complete pickup (triggers stock + financial settlement)
response = await client.patch(
    f"/api/v1/backoffice/orders/{order_id}/complete-pickup",
    headers=admin_headers,
)
assert response.status_code == 200
```

**TEST-03: Walk-in Sale**
```python
# Same as TEST-02 but WITHOUT clientId param (defaults to WALKIN_USER_ID)
response = await client.post(
    "/api/v1/backoffice/orders/warehouse-sale",
    json={
        "warehouse_id": str(warehouse_id),
        "items": [{"product_id": str(water_id), "quantity": 1}],
    },
    headers=admin_headers,
)
assert response.status_code == 201
# Walk-in complete_pickup also creates LOSS_WRITE_OFF transfer
```

**TEST-04: Courier Shift Close**
```python
response = await client.post(
    "/api/v1/backoffice/shifts/close",
    json={
        "courier_id": str(courier_id),
        "returned_inventory": [
            {"product_id": str(water_id), "quantity": 5},
            {"product_id": str(tara_id), "quantity": 3},
        ],
        "cash_collected": 100000,
    },
    headers=admin_headers,  # needs INVENTORY_WRITE scope
)
assert response.status_code == 200
```

### Fixture Data Creation Pattern

```python
# Source: Derived from src/core/seeder.py patterns + D-08

async def create_test_products(session: AsyncSession) -> dict:
    """Create water + tara products with known prices."""
    tara = Product(
        name="Test Tara 19L",
        type=ProductType.CONTAINER,
        price=50_000,
        is_active=True,
    )
    session.add(tara)
    await session.flush()

    water = Product(
        name="Test Water 19L",
        type=ProductType.WATER,
        price=20_000,
        returnable_item_id=tara.id,
        is_active=True,
    )
    session.add(water)
    await session.flush()

    return {"water": water, "tara": tara}
```

### Stock Loading Pattern (Triggers Auto-Create Balances)

```python
async def load_stock(
    session: AsyncSession,
    from_inv_id: uuid.UUID,
    to_inv_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
    created_by_id: uuid.UUID,
) -> None:
    """
    Create a completed stock transfer with transaction.
    The PG trigger will auto-create/update inventory_balances rows.
    """
    transfer = StockTransfer(
        from_id=from_inv_id,
        to_id=to_inv_id,
        type=TransferType.INITIAL_BALANCE,
        status=TransferStatus.COMPLETED,
        created_by_id=created_by_id,
    )
    session.add(transfer)
    await session.flush()

    item = StockTransferItem(
        transfer_id=transfer.id,
        product_id=product_id,
        quantity=quantity,
    )
    session.add(item)

    txn = StockTransaction(
        product_id=product_id,
        transfer_id=transfer.id,
        from_id=from_inv_id,
        to_id=to_inv_id,
        quantity=quantity,
    )
    session.add(txn)
    await session.flush()
    # After flush, the PG trigger has fired and updated inventory_balances
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/integration/ -x -v` |
| Full suite command | `uv run pytest tests/ -v --tb=short` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-01 | Order delivery fulfillment (stock debit + financial credit atomicity) | integration | `uv run pytest tests/integration/test_delivery_fulfillment.py -x` | Wave 0 |
| TEST-02 | Warehouse pickup flow | integration | `uv run pytest tests/integration/test_warehouse_pickup.py -x` | Wave 0 |
| TEST-03 | Walk-in sale flow | integration | `uv run pytest tests/integration/test_walkin_sale.py -x` | Wave 0 |
| TEST-04 | Courier shift close flow | integration | `uv run pytest tests/integration/test_courier_shift_close.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/integration/ -x -v`
- **Per wave merge:** `uv run pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/conftest.py` -- engine, connection, session factory, db_session, AsyncClient fixtures, auth header helper
- [ ] `tests/integration/conftest.py` -- shared product/user/inventory/account fixtures, stock loading helper
- [ ] `tests/integration/test_delivery_fulfillment.py` -- covers TEST-01
- [ ] `tests/integration/test_warehouse_pickup.py` -- covers TEST-02
- [ ] `tests/integration/test_walkin_sale.py` -- covers TEST-03
- [ ] `tests/integration/test_courier_shift_close.py` -- covers TEST-04

## Flow-by-Flow Analysis

### Flow 1: Order Delivery Fulfillment (TEST-01)

**API chain:**
1. `POST /api/v1/backoffice/orders/?clientId={id}` (create order) -- 201
2. `PATCH /api/v1/backoffice/orders/{id}/assign` (assign courier) -- 200
3. `PATCH /api/v1/backoffice/orders/{id}/status` with `newStatus: "delivered"` -- 200

**Service path:** `BaseOrderService.update_status()` -> detects transition to DELIVERED -> calls `_handle_order_fulfillment()` -> calls `_process_financial_settlement()`

**Stock movements:**
- CLIENT_DELIVERY: courier_inv -> client_inv (water, quantity per order)
- CLIENT_RETURN: client_inv -> courier_inv (tara, quantity per returnable items)

**Financial movements (CASH payment):**
- Revenue -> Client account (debt, amount = total_amount) -- COMPLETED
- Client -> Courier account (cash payment) -- COMPLETED

**Financial movements (CARD payment):**
- Revenue -> Client account (debt) -- COMPLETED
- Client -> Card account (card payment) -- PENDING

**Assertions needed:**
- HTTP 200, status == "delivered"
- Courier inventory balance: water decreased by order qty, tara increased by order qty
- Client inventory balance: water increased (net from delivery-only, or delivery+tara exchange), tara decreased
- Courier account balance: increased by total_amount (for cash)
- Client account balance: net zero (debt created then transferred to courier)
- Revenue account balance: decreased by total_amount

### Flow 2: Warehouse Pickup (TEST-02)

**API chain:**
1. `POST /api/v1/backoffice/orders/warehouse-sale?clientId={id}` -- 201
2. `PATCH /api/v1/backoffice/orders/{id}/complete-pickup` -- 200

**Service path:** `BaseOrderService.create_warehouse_sale()` then `complete_pickup()` -> `_handle_warehouse_pickup()` -> `_process_pickup_settlement()`

**Stock movements:**
- WAREHOUSE_SALE: warehouse -> client_inv (products)
- WAREHOUSE_TARA_RETURN: client_inv -> warehouse (tara for returnable items)

**Financial movements:**
- Revenue -> Client account (debt) -- COMPLETED
- Client -> Cash account (immediate payment) -- COMPLETED

**Assertions needed:**
- HTTP 201 for order creation, 200 for complete-pickup
- Order status == "pickup_completed"
- Warehouse balance: decreased by sold qty, increased by returned tara qty
- Client balance: increased by products, decreased by tara
- Revenue account balance: decreased
- Cash account balance: increased by total_amount
- Client account balance: net zero

### Flow 3: Walk-in Sale (TEST-03)

**Same as Flow 2 but:**
- No `clientId` query parameter -> uses `WALKIN_USER_ID`
- Additional LOSS_WRITE_OFF transfer: walk-in client_inv -> VIRTUAL_LOSS (cleanup)
- After cleanup, walk-in inventory should be empty (delivered items moved to loss)

**Extra assertions:**
- Walk-in inventory balance after cleanup: 0 for products delivered
- VIRTUAL_LOSS inventory: increased by delivered qty

### Flow 4: Courier Shift Close (TEST-04)

**API:** `POST /api/v1/backoffice/shifts/close`

**Service path:** `ShiftService.close_shift()`

**Pre-conditions (fixture must establish):**
- Courier has inventory with known product balances
- Courier has financial account with known cash balance (from prior deliveries)
- A main warehouse exists (first WAREHOUSE type inventory found by `get_system_inventory`)

**Steps:**
1. Reconciliation: `returned_inventory` must match system balances exactly
2. COURIER_RETURN transfer: courier_inv -> main_warehouse
3. Financial: courier_account -> system_cash_account (cash_collected amount)

**Assertions needed:**
- HTTP 200
- Courier inventory balances: all zeroed out (everything returned to warehouse)
- Warehouse inventory balances: increased by returned amounts
- Courier financial account balance: decreased by cash_collected
- System cash account balance: increased by cash_collected
- Courier inventory `is_active`: set to False (shift closed)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@pytest.mark.asyncio` on each test | `asyncio_mode = "auto"` in pyproject.toml | pytest-asyncio 0.21+ | No decorators needed on async tests |
| `asyncio_default_fixture_loop_scope` absent | Set to `"session"` in pyproject.toml | pytest-asyncio 0.24+ | Required for session-scoped async fixtures; already configured |
| Sync FastAPI TestClient | httpx AsyncClient + ASGITransport | FastAPI 0.100+ | Full async support, required for async app |

## Open Questions

1. **Session factory monkeypatch vs dependency override**
   - What we know: D-03 says no dependency overrides for auth. The session factory is not an auth dependency -- it is infrastructure.
   - What's unclear: Whether to use `app.dependency_overrides` for the session factory, or monkeypatch the module-level `async_session_maker` attribute.
   - Recommendation: Monkeypatch the module-level attribute. This is simpler and avoids any ambiguity about D-03. The UoW constructors receive `session_factory=async_session_maker` from their dependency providers, so overriding the module attribute before the request is processed ensures the test session factory is used.

2. **Commit behavior within savepoint**
   - What we know: The UoW calls `await session.commit()`. When the session is bound to a connection that has a transaction, `session.commit()` issues a RELEASE SAVEPOINT (not a real COMMIT).
   - What's unclear: Whether SQLAlchemy 2.1.0b1 handles this correctly with `async_sessionmaker(bind=connection)`.
   - Recommendation: Test this early in Wave 0. If `session.commit()` truly releases the savepoint and the data is visible, the approach works. If not, use `connection.begin_nested()` explicitly.

3. **`get_system_inventory` lookup in shift close**
   - What we know: `ShiftService.close_shift()` calls `self.uow.inventories.get_system_inventory(InventoryType.WAREHOUSE)` which queries for the first warehouse owned by SYSTEM_USER_ID.
   - What's unclear: Whether the dev DB already has a system warehouse, or only the seeder creates one.
   - Recommendation: The `init_data()` function does NOT create a warehouse. The seeder creates `[MOCK] Hlavny Sklad` but owned by system_user. Test fixtures should create their own warehouse with `user_id=SYSTEM_USER_ID` to ensure the lookup succeeds.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.14.3 | -- |
| pytest | Test runner | Yes | 9.0.2 | -- |
| pytest-asyncio | Async test support | Yes | 1.3.0 | -- |
| httpx | API test client | Yes | 0.28.1 | -- |
| PostgreSQL (dev) | Database (D-04) | Requires .env with PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE set | -- | None -- tests require live PG with triggers installed |
| uv | Package manager | Yes | -- | -- |

**Missing dependencies with no fallback:**
- PostgreSQL must be running and accessible via .env credentials with schema and triggers already applied (Alembic migrations run)

**Missing dependencies with fallback:**
- None

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python 3.14+, SQLAlchemy 2.x (async), PostgreSQL, FastAPI -- tests must use these
- **Line length**: 79 characters (Ruff enforced)
- **Import style**: Absolute imports from `src.` root only
- **Async**: All DB operations must be `async def`
- **asyncio_mode**: "auto" -- no `@pytest.mark.asyncio` decorators
- **asyncio_default_fixture_loop_scope**: "session" -- configured in pyproject.toml
- **Error format**: `{"error": {"code": "ERROR_CODE", "message": "...", "details": {...}}}`
- **UUIDv7**: Primary keys use `uuid.uuid7()`
- **Pre-commit hooks**: Ruff formatter + linter will run on any committed test files
- **Naming**: snake_case for files and functions, PascalCase for classes

## Sources

### Primary (HIGH confidence)
- Direct source code inspection of all referenced files (services, models, API routers, triggers, config, UoW)
- `pyproject.toml` for exact dependency versions and test configuration
- `src/core/seeder.py` for entity creation patterns and relationship dependencies
- `src/infrastructure/database/scripts/*.sql` for exact trigger behavior

### Secondary (MEDIUM confidence)
- SQLAlchemy 2.x async testing patterns from training data and documentation (savepoint pattern is well-established since SQLAlchemy 1.4)
- httpx + FastAPI ASGITransport testing pattern from FastAPI official documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all dependencies already installed and verified
- Architecture: HIGH -- savepoint pattern is well-established; all source code inspected
- Pitfalls: HIGH -- identified from direct code analysis of UoW lifecycle, trigger SQL, and session management
- Flow analysis: HIGH -- every line of the four service methods read and mapped to API endpoints

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable -- characterization tests against existing code, no external API changes)
