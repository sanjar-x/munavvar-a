# Technology Stack for DDD Restructuring + Role-Based API Layer

**Project:** HOD (Home & Office Delivery)
**Researched:** 2026-03-27
**Mode:** Ecosystem -- DDD modular monolith restructuring in Python/FastAPI

## Executive Summary

The existing stack (FastAPI + SQLAlchemy 2.1 async + PostgreSQL + Pydantic v2) is already the right foundation. This research focuses on *what to add, how to configure what exists, and what patterns to adopt* for the DDD restructuring milestone. The core principle: **no new frameworks, just disciplined patterns on the existing stack.** The project should not introduce a DDD framework, event bus library, or state machine library -- Python's stdlib `dataclasses` plus Pydantic v2 plus SQLAlchemy's existing patterns are sufficient for a 6-context modular monolith at this scale.

## Recommended Stack

### Core Framework (Keep As-Is)

| Technology | Pin | Purpose | Confidence |
|---|---|---|---|
| FastAPI | >=0.135.0 | Async REST API framework | HIGH |
| SQLAlchemy | >=2.1.0b2 | ORM with async support, mapped_column, composite types | HIGH |
| Pydantic v2 | >=2.12.5 | Request/response validation, settings, frozen service DTOs | HIGH |
| asyncpg | >=0.31.0 | PostgreSQL async driver | HIGH |
| Alembic | >=1.18.4 | Database migrations | HIGH |
| Python | >=3.14 | Runtime -- uses new generic syntax `class Foo[T]` | HIGH |

**Why keep:** FastAPI 0.135+ and SQLAlchemy 2.1 are the current state of the art for async Python APIs. Pydantic v2 is deeply integrated into FastAPI. No reason to switch anything. SQLAlchemy 2.1.0b2 is beta but the project already pins `>=2.1.0b1` and uses its features; the beta is stable enough for this use case (no production data migration pressure).

**FastAPI version note:** Bump from `>=0.132.0` to `>=0.135.0`. Version 0.135.2 (released 2026-03-23) includes Pydantic v2 model_config fixes and is the latest stable release.

### Service Layer DTOs (New Pattern, No New Library)

| Technology | Version | Purpose | Why |
|---|---|---|---|
| `dataclasses` (stdlib) | Python 3.14 built-in | Frozen DTOs returned from services | Zero dependency, `frozen=True` + `slots=True` gives immutable, fast objects |
| Pydantic v2 `BaseModel` | >=2.12.5 | API request/response schemas only | Validation belongs at API boundary, not service layer |

**Why `dataclasses` for service DTOs instead of Pydantic frozen models:**

1. **Separation of concerns.** Pydantic's purpose is *validation* -- it belongs at the API boundary. Service DTOs are *data transfer containers* that carry already-validated domain state. Using Pydantic for both conflates two concerns.
2. **Performance.** Frozen `@dataclass(frozen=True, slots=True)` is 4-6x faster to instantiate than Pydantic `BaseModel(frozen=True)`. Service DTOs are constructed on every request; this matters.
3. **No validation overhead.** Service DTOs are constructed from trusted data (from the database or business logic). Running Pydantic validation on data that just came from your own ORM is wasteful.
4. **Clarity.** When a developer sees `@dataclass`, they know "this is a data bag." When they see `BaseModel`, they know "this has validation." The distinction communicates intent.
5. **Modern Python 3.14.** With `kw_only=True`, `slots=True`, `frozen=True`, and `dataclasses.replace()` for copy-with-changes, stdlib dataclasses are fully sufficient.

**Pattern:**

```python
from dataclasses import dataclass
import uuid
from datetime import datetime

@dataclass(frozen=True, slots=True, kw_only=True)
class OrderDTO:
    id: uuid.UUID
    client_id: uuid.UUID
    status: str
    total_amount: int
    created_at: datetime

    @classmethod
    def from_model(cls, order: Order) -> "OrderDTO":
        return cls(
            id=order.id,
            client_id=order.client_id,
            status=order.status.value,
            total_amount=order.total_amount,
            created_at=order.created_at,
        )
```

**What NOT to use:**
- **msgspec Structs** -- 10-20x faster than Pydantic, but adds a dependency for marginal gain over dataclasses in a service DTO context (no serialization needed). Adds cognitive load.
- **Pydantic `model_config = {"frozen": True}`** -- Known edge-case bugs in Pydantic 2.10-2.12 where frozen fields can be mutated after `model_construct()`. Also carries unnecessary validation machinery.
- **attrs** -- Functionally identical to dataclasses for this use case, but adds a dependency. stdlib is preferred when equivalent.

**Confidence:** HIGH -- stdlib dataclasses are battle-tested, zero-dependency, and the recommended approach for DDD value objects/DTOs in Python 3.12+.

### Domain Events (New Pattern, No New Library)

| Technology | Version | Purpose | Why |
|---|---|---|---|
| Simple in-process event bus | Custom, <50 lines | Decouple bounded contexts | At this scale, a hand-rolled `EventBus` with `dict[type, list[Callable]]` is simpler than any library |

**Why NOT use a library:**

- **mediatr_py, python-mediator, pyventus** -- These are all <500 GitHub stars, varying maintenance levels, and add patterns (CQRS, pipeline behaviors) that are overkill for in-process domain events in a modular monolith.
- **The project has 6 bounded contexts in a single process.** A simple `async def publish(event: DomainEvent)` that dispatches to registered handlers is all that's needed. No message broker, no serialization, no replay.

**Pattern:**

```python
from dataclasses import dataclass
from collections import defaultdict
from collections.abc import Callable, Awaitable
from typing import Any

@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Base class for all domain events."""
    pass

@dataclass(frozen=True, slots=True)
class OrderDelivered(DomainEvent):
    order_id: uuid.UUID
    courier_id: uuid.UUID
    total_amount: int

class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable[..., Awaitable[Any]]]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent], handler: Callable[..., Awaitable[Any]]) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers[type(event)]:
            await handler(event)
```

**When to introduce a real event bus:** If the project ever needs cross-service communication (microservices), event replay, or async background processing. Then consider Redis Streams or PostgreSQL LISTEN/NOTIFY. Not now.

**Confidence:** HIGH -- this is standard DDD modular monolith practice. Libraries add complexity without proportional value at this scale.

### State Machine for Transfer/Order Lifecycles (Keep Hand-Rolled)

| Technology | Version | Purpose | Why |
|---|---|---|---|
| Enum + explicit transition methods | stdlib | Order status transitions, transfer status transitions | Simpler than a library for <10 states |

**Why NOT `python-statemachine` 3.0.0:**

- The project already has `TransferStatus` and `OrderStatus` enums with explicit transition logic in service methods. This works.
- `python-statemachine` adds class-per-machine overhead, diagram generation features the project does not need, and Django integration baggage.
- With only 4-5 states per entity (Order: PENDING -> ASSIGNED -> IN_DELIVERY -> DELIVERED/CANCELLED; Transfer: DRAFT -> COMPLETED -> CANCELLED), a simple `VALID_TRANSITIONS: dict[Status, set[Status]]` dict + a `transition(current, target)` function is clearer and more debuggable.

**Pattern:**

```python
VALID_ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.ASSIGNED, OrderStatus.CANCELLED},
    OrderStatus.ASSIGNED: {OrderStatus.IN_DELIVERY, OrderStatus.CANCELLED},
    OrderStatus.IN_DELIVERY: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
}

def validate_transition(current: OrderStatus, target: OrderStatus) -> None:
    allowed = VALID_ORDER_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStatusTransitionError(current, target)
```

**When to introduce `python-statemachine`:** If entities grow to 10+ states with complex guard conditions and actions. Not relevant for this domain.

**Confidence:** HIGH -- hand-rolled state validation is standard for simple lifecycles.

### Architecture Testing (Keep, Upgrade Rules)

| Technology | Version | Purpose | Why |
|---|---|---|---|
| pytest-archon | >=0.0.7 | Enforce bounded context boundaries | Already in devDeps, proven pattern for preventing cross-context imports |

**Why this matters for DDD restructuring:** The entire point of bounded contexts is that modules do not import each other's internals. pytest-archon tests make this enforceable in CI. Without them, context boundaries erode within weeks.

**Pattern for bounded context enforcement:**

```python
# tests/test_architecture.py
from pytest_archon import archrule

def test_inventory_does_not_import_orders():
    (archrule("inventory_isolation")
     .match("src.modules.inventory.*")
     .should_not_import("src.modules.orders.*")
     .check("src"))

def test_billing_does_not_import_logistics():
    (archrule("billing_isolation")
     .match("src.modules.billing.*")
     .should_not_import("src.modules.logistics.*")
     .check("src"))

def test_modules_do_not_import_api():
    (archrule("no_api_in_modules")
     .match("src.modules.*")
     .should_not_import("src.api.*")
     .check("src"))
```

**Confidence:** HIGH -- already in use, just needs expanded rules for 6 bounded contexts.

### Logging, Security, Config (Keep As-Is)

| Technology | Pin | Purpose | Change Needed |
|---|---|---|---|
| structlog | >=25.5.0 | Structured logging | None |
| structlog-config | >=0.11.0 | Structlog helpers | None |
| pyjwt | >=2.11.0 | JWT tokens | None -- add audience claim for 3 API audiences |
| pwdlib[argon2,bcrypt] | >=0.3.0 | Password hashing | None |
| pydantic-settings | >=2.13.1 | Env-based config | Bump from implicit (via fastapi) to explicit pin |

**JWT audience claim for 3 API audiences:**

The existing JWT implementation embeds scopes at token creation time. For the 3-audience API split (courier, client, staff), add an `aud` (audience) claim to the JWT:

```python
# Token payload includes:
{
    "sub": "user_id",
    "aud": "courier",  # or "client" or "staff"
    "scopes": ["orders:read", "orders:deliver", ...]
}
```

Then create per-audience auth dependencies:

```python
def require_courier_token(token: TokenPayload = Depends(get_token_payload)) -> TokenPayload:
    if token.audience != "courier":
        raise ForbiddenError("Invalid audience")
    return token
```

This reuses the existing JWT infrastructure. No new auth library needed.

**Confidence:** HIGH -- standard JWT `aud` claim pattern, already supported by PyJWT.

### Testing (Keep, Add)

| Technology | Pin | Purpose | Change Needed |
|---|---|---|---|
| pytest | >=9.0.2 | Test runner | None |
| pytest-asyncio | >=1.3.0 | Async test support | None |
| pytest-cov | >=7.0.0 | Coverage | None |
| pytest-archon | >=0.0.7 | Architecture rules | Expand rules for 6 bounded contexts |
| httpx | >=0.28.1 | API test client | None |
| polyfactory | >=3.3.0 | Test data factories | None |

**No new test dependencies needed.** The existing test stack is comprehensive.

**Confidence:** HIGH.

### Dev Tooling (Keep As-Is)

| Technology | Pin | Purpose | Change Needed |
|---|---|---|---|
| ruff | >=0.15.1 | Linter + formatter | None |
| ty | >=0.0.17 | Type checker | None |
| pre-commit | >=4.5.1 | Git hooks | None |
| uv | latest | Package manager | None |

**Confidence:** HIGH.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|---|---|---|---|
| Service DTOs | `dataclasses(frozen=True, slots=True)` | Pydantic frozen models | Validation overhead, known frozen bugs, conflates validation with data transfer |
| Service DTOs | `dataclasses` | `msgspec.Struct` | External dependency for marginal perf gain; no serialization needed at service layer |
| Service DTOs | `dataclasses` | `attrs` | External dependency; stdlib is equivalent for this use case |
| Domain Events | Hand-rolled EventBus (<50 LOC) | mediatr_py | CQRS overkill for in-process modular monolith |
| Domain Events | Hand-rolled EventBus | pyventus | External dependency for something trivial |
| State Machine | Enum + transition dict | python-statemachine 3.0 | Over-engineered for <10 states; adds class-per-machine overhead |
| Architecture Tests | pytest-archon | PyTestArch | pytest-archon already in use, stable, simpler API |
| Auth | JWT `aud` claim (existing PyJWT) | Auth0 FGA / Permit.io | External service dependency for a single-org system with 8 roles |
| Double-entry Ledger | Custom (existing PG triggers) | python-accounting / django-ledger | These are full accounting systems; the project needs domain-specific ledger logic, not GAAP reporting |

## What NOT to Add

| Library/Pattern | Why Tempting | Why Wrong |
|---|---|---|
| **Any DDD framework** (e.g., ddd-python, cosmic-python patterns lib) | "DDD in a box" sounds productive | DDD is a design discipline, not a library. These frameworks impose opinions that conflict with SQLAlchemy's identity map |
| **Dishka** (DI container) | "Proper" dependency injection | FastAPI's `Depends()` is sufficient. Adding a container adds indirection without solving a real problem at this scale |
| **SQLModel** | "Combines SQLAlchemy + Pydantic" | Leaky abstraction. The project already has clean SQLAlchemy models. SQLModel adds constraints without benefits for DDD |
| **Celery / ARQ / Dramatiq** | "Background tasks for events" | All domain events are synchronous in-process. No background jobs needed for this milestone |
| **Redis** (for events) | "Event bus needs a broker" | In-process events in a monolith do not need a broker. Redis is configured but unused -- keep it that way for now |
| **Alembic auto-generate for triggers** | "Automate trigger migrations" | PG trigger migrations must be hand-written. Auto-generate does not understand `CREATE FUNCTION` or `CREATE TRIGGER` |

## Dependency Changes Summary

### pyproject.toml Changes

```toml
[project]
dependencies = [
    "alembic>=1.18.4",           # no change
    "asyncpg>=0.31.0",           # no change
    "fastapi[standard]>=0.135.0", # BUMP from >=0.132.0
    "pwdlib[argon2,bcrypt]>=0.3.0", # no change
    "pyjwt>=2.11.0",             # no change
    "pydantic-settings>=2.13.1",  # ADD explicit pin (was implicit via fastapi)
    "sqlalchemy[asyncio]>=2.1.0b1", # no change (b2 available but >=b1 covers it)
    "structlog>=25.5.0",          # no change
    "structlog-config>=0.11.0",   # no change
]
```

**Net result: 1 version bump (FastAPI), 1 explicit pin (pydantic-settings). Zero new production dependencies.**

### Dev Dependencies

No changes needed. The existing dev stack covers all needs.

## Key Patterns Enabled by This Stack

### 1. Frozen DTO Boundary Pattern

Services return `@dataclass(frozen=True)` DTOs. API routers convert DTOs to Pydantic response models. ORM models never leave the service layer.

```
Router (Pydantic) <-> Service (dataclass DTO) <-> Repository (ORM model)
```

### 2. Composite Unit of Work per Bounded Context

Each bounded context gets its own UoW composing only the repositories it owns. Cross-context operations go through the Application layer's composite UoW. This is already the pattern in the codebase -- it just needs to be made consistent across all 6 contexts.

### 3. SQLAlchemy Composite Types for Value Objects

Use `composite()` with `mapped_column()` for domain value objects that map to multiple columns (e.g., `Money(amount, currency)` if needed). This is native SQLAlchemy 2.1 -- no library needed.

### 4. JWT Audience-Scoped API Separation

Three API audiences (`/api/v1/courier/`, `/api/v1/client/`, `/api/v1/backoffice/`) share the same JWT infrastructure but validate against different `aud` claims and scope sets. Already partially implemented -- needs the `aud` claim added.

## Sources

### Official Documentation (HIGH confidence)
- [SQLAlchemy 2.1 Async Docs](https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html)
- [SQLAlchemy 2.1 Changelog](https://docs.sqlalchemy.org/en/21/changelog/changelog_21.html) -- 2.1.0b2 latest
- [SQLAlchemy 2.1 Composite Types](https://docs.sqlalchemy.org/en/21/orm/composites.html)
- [Pydantic v2 Frozen Models](https://docs.pydantic.dev/latest/concepts/models/)
- [Pydantic v2 Config](https://docs.pydantic.dev/latest/api/config/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [FastAPI APIRouter](https://fastapi.tiangolo.com/reference/apirouter/)
- [Python dataclasses docs](https://docs.python.org/3/library/dataclasses.html)

### PyPI Version Verification (HIGH confidence)
- FastAPI 0.135.2 -- released 2026-03-23
- SQLAlchemy 2.1.0b2 -- unreleased (b1 released 2026-01-21)
- Pydantic 2.12.5 -- released 2025-11-26 (2.13.0b2 in beta)
- pydantic-settings 2.13.1 -- released 2026-02-19
- Alembic 1.18.4 -- released 2026-02-10
- asyncpg 0.31.0 -- released 2025-11-24
- structlog 25.5.0 -- released 2025-10-27
- pytest-archon 0.0.7 -- released 2025-09-19
- python-statemachine 3.0.0 -- released 2026-02-24 (evaluated, rejected)
- pwdlib 0.3.0 -- released 2025-10-25

### Community / Architecture Patterns (MEDIUM confidence)
- [DDD Principles Python: Aggregates with SQLAlchemy Events](https://johal.in/ddd-principles-python-aggregates-with-sqlalchemy-events-2026/)
- [Domain model with SQLAlchemy](https://blog.szymonmiks.pl/p/domain-model-with-sqlalchemy/)
- [Mastering Value Objects in Python](https://damianpiatkowski.com/blog/value-objects-in-python)
- [Protecting Architecture with Automated Tests in Python](https://handsonarchitects.com/blog/2026/protecting-architecture-with-automated-tests-in-python/)
- [pytest-archon GitHub](https://github.com/jwbargsten/pytest-archon)
- [FastAPI DDD Example](https://github.com/NEONKID/fastapi-ddd-example)
- [Python DDD Example](https://github.com/qu3vipon/python-ddd)

### Benchmark / Comparison (MEDIUM confidence)
- [msgspec vs Pydantic v2 Benchmark](https://hrekov.com/blog/msgspec-vs-pydantic-v2-benchmark)
- [Python Data Serialization 2025](https://hrekov.com/blog/python-data-serialization-2025)

---

*Stack research: 2026-03-27*
