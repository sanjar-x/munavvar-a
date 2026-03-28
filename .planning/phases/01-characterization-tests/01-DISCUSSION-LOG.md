# Phase 1: Characterization Tests - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-28
**Phase:** 01-characterization-tests
**Areas discussed:** Test level, Database strategy, Test data setup, Assertion depth

---

## Test Level

| Option | Description | Selected |
|--------|-------------|----------|
| API level | Full HTTP requests via httpx AsyncClient. Exercises auth, middleware, serialization, services, repos, AND PG triggers. | ✓ |
| Service level | Call service methods directly. Skips HTTP layer but still hits real DB + triggers. Simpler setup, less coverage. | |
| Both layers | API-level for happy path, service-level for edge cases. More tests but maximum safety net. | |

**User's choice:** API level
**Notes:** Most realistic approach — catches the most behavior during refactoring.

### Follow-up: Auth Setup

| Option | Description | Selected |
|--------|-------------|----------|
| Direct token creation | Use create_access_token() in fixtures to mint JWTs. Faster, avoids coupling to auth flow. | ✓ |
| Real login endpoint | POST /api/v1/auth/login to get tokens. Tests auth flow too but couples all tests to login. | |
| Dependency override | Override get_current_user via app.dependency_overrides. Bypasses JWT entirely. | |

**User's choice:** Direct token creation
**Notes:** None

---

## Database Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated test DB | Separate 'hod_test' database in Docker Compose PostgreSQL. Schema via Alembic migrations. | |
| Reuse dev DB with rollback | Run tests against dev database, wrap each test in a transaction that rolls back. | ✓ |
| Ephemeral Docker container | Fresh PostgreSQL container per test session via testcontainers. | |

**User's choice:** Use existing connected database with transaction rollback
**Notes:** User explicitly chose this — no separate test DB needed. Project already has a working PostgreSQL connection configured.

---

## Test Data Setup

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated fixtures | Write pytest fixtures that create exactly the entities each flow needs using the test session. | ✓ |
| Adapt Seeder for tests | Refactor Seeder to accept a session parameter so it can run within test transaction. | |
| init_data + Seeder via API | Call the seed endpoint at test start. | |

**User's choice:** Dedicated fixtures
**Notes:** None

### Follow-up: Fixture Style

| Option | Description | Selected |
|--------|-------------|----------|
| ORM models directly | session.add(User(...)). Fastest, no service-layer coupling. | ✓ |
| Via service methods | Call UserService.add(), CatalogService.add(). Tests setup path too. | |
| You decide | Claude's discretion based on what makes sense per fixture. | |

**User's choice:** ORM models directly
**Notes:** None

---

## Assertion Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Final state + ledger balances | Assert HTTP response + verify inventory_balances and accounts.balance. | ✓ |
| Full depth — every record | Assert response + count stock_transactions, verify each transfer record. | |
| Response only | Assert HTTP status codes and response JSON structure only. | |

**User's choice:** Final state + ledger balances
**Notes:** Right balance for refactoring safety without brittleness.

### Follow-up: Balance Check

| Option | Description | Selected |
|--------|-------------|----------|
| Exact amounts | Assert inventory_balances.quantity == expected and accounts.balance == expected. | ✓ |
| Direction only | Assert balance decreased/increased by checking before vs after. | |
| You decide | Claude's discretion — exact where deterministic, directional where complex. | |

**User's choice:** Exact amounts
**Notes:** Prices controlled in fixtures, so amounts are deterministic.

---

## Claude's Discretion

- Fixture composition and sharing strategy
- Test file organization within tests/ directory
- polyfactory usage
- Error message assertion strategy

## Deferred Ideas

None — discussion stayed within phase scope
