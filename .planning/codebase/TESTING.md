# Testing Patterns

**Analysis Date:** 2026-03-27

## Test Framework

**Runner:**
- pytest 9.0.2+
- Config: `pyproject.toml` `[tool.pytest.ini_options]`

**Async Support:**
- pytest-asyncio 1.3.0+
- `asyncio_mode = "auto"` (all async tests run automatically without `@pytest.mark.asyncio`)
- `asyncio_default_fixture_loop_scope = "session"` (single event loop shared across session)

**Additional Test Libraries (installed as dev dependencies):**
- `httpx` 0.28.1+ -- async HTTP client for FastAPI `TestClient` / `ASGITransport`
- `polyfactory` 3.3.0+ -- test data factory generation from Pydantic models
- `pytest-cov` 7.0.0+ -- coverage reporting
- `pytest-archon` 0.0.7+ -- architecture/dependency constraint testing
- `locust` 2.43.3+ -- load testing (not integrated into pytest)

**Run Commands:**
```bash
make test                    # Run all tests (uv run pytest -v)
uv run pytest -v             # Direct invocation
uv run pytest --cov=src      # With coverage (not configured as default)
uv run pytest -k "test_name" # Run specific test
```

## Current Test State

**CRITICAL: The project has virtually no tests.**

The `tests/` directory contains:
- `tests/conftest.py` -- exists but is **empty** (0 lines of code)
- `tests/data.json` -- test fixture data file
- `tests/data copy.json` -- duplicate of above
- `tests/` -- no `test_*.py` files exist

There are **zero test functions** in the codebase. All testing patterns below are **prescriptive guidance** for writing new tests, based on the installed tooling, framework conventions, and codebase architecture.

## Test File Organization

**Location:**
- Separate `tests/` directory at project root (not co-located with source)
- Mirror the `src/` module structure inside `tests/`

**Naming:**
- Test files: `test_{module}.py` (e.g., `test_users.py`, `test_orders.py`)
- Test functions: `test_{action}_{scenario}` (e.g., `test_create_order_empty_cart_raises`)

**Recommended Structure:**
```
tests/
    conftest.py                    # Shared fixtures (DB session, test client, factories)
    test_health.py                 # Smoke tests
    unit/
        test_exceptions.py         # Exception hierarchy tests
        test_permissions.py        # RBAC scope mapping tests
        test_jwt.py                # Token creation/validation
    integration/
        test_users.py              # User CRUD via service layer
        test_catalog.py            # Product catalog operations
        test_orders.py             # Order lifecycle
        test_inventory.py          # Stock transfers and ledger
        test_finances.py           # Financial transactions
    api/
        test_auth_endpoints.py     # Login/register endpoints
        test_backoffice_users.py   # Backoffice user management
        test_backoffice_orders.py  # Backoffice order endpoints
        test_client_endpoints.py   # Client-facing API
        test_courier_endpoints.py  # Courier-facing API
    architecture/
        test_dependencies.py       # pytest-archon layer dependency tests
```

## Test Structure

**Suite Organization (recommended pattern):**
```python
# tests/integration/test_orders.py
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


class TestOrderCreation:
    """Tests for the order checkout flow."""

    async def test_create_order_success(self, authenticated_client, seed_products):
        """Happy path: create order with valid items."""
        response = await authenticated_client.post(
            "/api/v1/backoffice/orders/",
            params={"clientId": str(seed_products["client_id"])},
            json={
                "items": [{"product_id": str(seed_products["water_id"]), "quantity": 2}],
                "payment_method": "cash",
                "client_inventory_id": str(seed_products["inventory_id"]),
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "new"
        assert data["total_amount"] > 0

    async def test_create_order_empty_cart_fails(self, authenticated_client):
        """Validation: empty cart should raise 422."""
        response = await authenticated_client.post(
            "/api/v1/backoffice/orders/",
            params={"clientId": str(uuid.uuid4())},
            json={"items": [], "payment_method": "cash", "client_inventory_id": str(uuid.uuid4())},
        )
        assert response.status_code == 422

    async def test_create_order_missing_products_fails(self, authenticated_client):
        """Business rule: nonexistent product IDs should raise error."""
        response = await authenticated_client.post(
            "/api/v1/backoffice/orders/",
            params={"clientId": str(uuid.uuid4())},
            json={
                "items": [{"product_id": str(uuid.uuid4()), "quantity": 1}],
                "payment_method": "cash",
                "client_inventory_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code in (404, 409, 422)
        assert "error" in response.json()
```

**Setup/teardown:**
- Use pytest fixtures with `async` generators for DB setup/teardown
- Scope fixtures appropriately: `session` for DB connection, `function` for data isolation

## Conftest Setup (Recommended Implementation)

**`tests/conftest.py` should provide:**

```python
# tests/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.main import app
from src.infrastructure.database.base import BaseModel


# --- Database Fixtures ---

@pytest.fixture(scope="session")
def test_engine():
    """Create a test database engine."""
    # Use a separate test database or SQLite for unit tests
    engine = create_async_engine(
        "postgresql+asyncpg://test:test@localhost:5432/test_db",
        echo=False,
    )
    return engine


@pytest.fixture(scope="session")
async def setup_db(test_engine):
    """Create all tables before test session, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def db_session(test_engine, setup_db):
    """Provide a transactional DB session per test (auto-rollback)."""
    async with AsyncSession(test_engine) as session:
        async with session.begin():
            yield session
            await session.rollback()


# --- HTTP Client Fixtures ---

@pytest.fixture
async def client():
    """Unauthenticated async HTTP client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def authenticated_client(client):
    """Client with valid admin JWT token."""
    # Create or login as admin, attach token to headers
    # This depends on your auth flow
    token = "..."  # Generate via create_access_token
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
```

## Mocking

**Framework:** Standard `unittest.mock` (no third-party mock library installed)

**Patterns - Mocking external dependencies:**
```python
# Mock the UoW for unit testing services in isolation
from unittest.mock import AsyncMock, MagicMock, patch

async def test_user_service_register():
    mock_uow = AsyncMock()
    mock_uow.users.get_with_identity.return_value = None  # No existing user
    mock_uow.users.add.return_value = MagicMock(id=uuid.uuid4(), username="Test")
    mock_uow.__aenter__.return_value = mock_uow

    service = UserService(uow=mock_uow)
    result = await service.register_local_user(schema)

    mock_uow.users.add.assert_called_once()
    mock_uow.commit.assert_called_once()
```

**Patterns - Mocking FastAPI dependencies:**
```python
from fastapi.testclient import TestClient
from src.modules.auth.dependencies import get_current_user

async def mock_current_user():
    return MagicMock(id=uuid.uuid4(), role=Role.ADMIN, is_active=True)

app.dependency_overrides[get_current_user] = mock_current_user
```

**What to Mock:**
- External services (Redis, third-party APIs) when not available in test env
- JWT token validation for API endpoint tests (override `get_current_user`)
- `async_session_maker` to inject test DB session

**What NOT to Mock:**
- SQLAlchemy models and queries in integration tests -- use real test DB
- Pydantic validation -- let it run against real schemas
- Business logic in services -- test the actual implementation

## Fixtures and Factories

**Test Data Factories (polyfactory):**
polyfactory is installed and can generate test data from Pydantic schemas:

```python
# tests/factories.py
from polyfactory.factories.pydantic_factory import ModelFactory
from src.modules.users.schemas import UserAdminCreate
from src.modules.orders.schemas import OrderCreate


class UserFactory(ModelFactory):
    __model__ = UserAdminCreate

    @classmethod
    def phone(cls) -> str:
        return f"+99890{cls.__faker__.random_number(digits=7)}"


class OrderCreateFactory(ModelFactory):
    __model__ = OrderCreate
```

**Test data files:**
- `tests/data.json` -- JSON fixture data (currently present but unused)

**Location:**
- Fixture definitions: `tests/conftest.py` and `tests/factories.py`
- Static test data: `tests/data.json`

## Coverage

**Requirements:** None enforced currently. No coverage threshold configured.

**View Coverage:**
```bash
uv run pytest --cov=src --cov-report=html   # HTML report
uv run pytest --cov=src --cov-report=term    # Terminal output
```

**Priority areas for coverage (by business impact):**
1. `src/modules/orders/services.py` -- Order lifecycle (create, deliver, warehouse sale)
2. `src/modules/inventory/services.py` -- Stock transfers and ledger integrity
3. `src/modules/finances/` -- Financial settlement and account balances
4. `src/core/security/` -- JWT, password hashing, permissions
5. `src/modules/auth/` -- Login, token generation, scope verification

## Test Types

**Unit Tests:**
- Scope: Individual functions, exception classes, utility functions, permission mappings
- No DB required
- Files: `tests/unit/`
- Examples: JWT token encoding/decoding, password hashing, exception construction, `ROLE_SCOPES` mapping correctness

**Integration Tests:**
- Scope: Service layer methods with real (test) database
- Requires PostgreSQL test database
- Files: `tests/integration/`
- Examples: `UserService.register_client` creates user + identity + account + inventory atomically, `BaseOrderService.create_order` calculates prices and handles tara exchange

**API / E2E Tests:**
- Scope: Full HTTP request/response cycle via httpx `AsyncClient`
- Requires running FastAPI app with test DB
- Files: `tests/api/`
- Examples: POST `/api/v1/auth/login` returns JWT, POST `/api/v1/backoffice/orders/` creates order

**Architecture Tests (pytest-archon):**
- Scope: Enforce import boundaries between layers
- No DB required
- Files: `tests/architecture/`
- Example: modules should not import from `src.api`, repositories should not import from services

**Load Tests (locust):**
- Scope: Performance and concurrency testing
- Separate from pytest, run with `locust` CLI
- Not currently implemented

## Common Patterns

**Async Testing:**
```python
# All async tests run automatically due to asyncio_mode = "auto"
# No need for @pytest.mark.asyncio decorator

async def test_get_user_returns_none_for_missing_id(db_session):
    repo = UserRepository(session=db_session)
    result = await repo.get(uuid.uuid4())
    assert result is None
```

**Error Testing:**
```python
import pytest
from src.core.exceptions import ConflictError
from src.modules.users.exceptions import UserAlreadyExistsError

async def test_duplicate_phone_raises_conflict(user_service, existing_user):
    with pytest.raises(UserAlreadyExistsError) as exc_info:
        await user_service.register_local_user(
            UserAdminCreate(
                username="Duplicate",
                phone=existing_user.phone,
                password="pass1234",
                role=Role.CLIENT_B2C,
            )
        )
    assert exc_info.value.error_code == "USER_ALREADY_EXISTS"
    assert exc_info.value.status_code == 409
```

**Testing error response format at API level:**
```python
async def test_not_found_returns_standard_error_json(client):
    response = await client.get(f"/api/v1/backoffice/users/{uuid.uuid4()}")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]
    assert "details" in body["error"]
```

**Testing UoW transaction atomicity:**
```python
async def test_order_creation_rolls_back_on_failure(db_session):
    """If order item creation fails, the order header should also rollback."""
    # Count orders before
    initial_count = await order_repo.count()

    with pytest.raises(SomeExpectedError):
        await order_service.create_order(client_id=..., dto=bad_dto)

    # Count should be unchanged (rollback happened)
    final_count = await order_repo.count()
    assert final_count == initial_count
```

## Key Testing Considerations

**Database triggers:** The project uses PostgreSQL triggers for balance updates (`update_account_balances`). Integration tests MUST use a real PostgreSQL database to test trigger behavior -- SQLite will not work.

**Soft delete:** All `BaseRepository.get_multi` and `get` methods filter `is_active=True` by default. Tests should verify both active and archived entity behavior.

**UUIDv7:** Primary keys use `uuid.uuid7()` which is time-ordered. Tests should not assume random UUID distribution.

**Russian error messages:** Error messages are in Russian. Tests should assert on `error_code` (machine-readable) rather than `message` (human-readable, may change).

**Session-scoped event loop:** pytest-asyncio is configured with `asyncio_default_fixture_loop_scope = "session"`, meaning all tests share one event loop. This is important for fixtures that create DB connections.

---

*Testing analysis: 2026-03-27*
