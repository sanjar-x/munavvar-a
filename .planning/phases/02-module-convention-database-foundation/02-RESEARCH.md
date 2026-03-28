# Phase 2: Module Convention & Database Foundation - Research

**Researched:** 2026-03-28 (re-validated)
**Domain:** Python DDD module conventions, frozen dataclasses, SQLAlchemy generics, Alembic migration rebuild
**Confidence:** HIGH

## Summary

Phase 2 establishes two foundational patterns: (1) the `public.py` facade + frozen DTO convention using Catalog as pilot module, and (2) a clean Alembic migration rebuild from scratch. The Catalog module is the ideal pilot -- it has no inbound module dependencies (only outbound: other modules consume it), making it safe for demonstrating the full Repository -> Service -> frozen DTO chain without cascading breakage.

The primary technical risks are well-understood: the `values_callable` fix must be applied to ALL model enum declarations (not just catalog) so the fresh migration generates correct lowercase PG enum labels, and the `BaseService` generic signature must gain a `DTOType` parameter without breaking existing subclasses. Both have been verified against the project's Python 3.14 runtime.

The consumer update scope is significant -- 18 import statements across `src/` need redirecting to `src.modules.catalog.public`. After facade creation, consumers of CatalogService and ProductType must import from `catalog.public`. However, per D-03, only existing Catalog consumers are updated; application-layer UoWs that import `ProductRepository` directly are left as-is (those are addressed in later phases when composite UoWs are decomposed per ARCH-04).

**Primary recommendation:** Execute in three waves -- (1) create DTO + facade + update BaseService generics, (2) update all consumers to import from public.py, (3) rebuild Alembic migrations from scratch with corrected enums.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Catalog is the pilot module -- simplest, no inbound dependencies, safest for demonstrating the full pattern
- **D-02:** Only Catalog is converted in Phase 2 -- other modules follow in Phases 3-6 using Catalog as reference
- **D-03:** All existing consumers of Catalog internals are updated to import from `catalog.public` -- proves the facade end-to-end
- **D-04:** Characterization tests from Phase 1 are also updated to import from `catalog.public`
- **D-05:** Pydantic schemas (ProductResponse, etc.) coexist with frozen DTOs -- schemas stay for API request/response validation, DTOs are what services return internally. API layer converts DTO -> Pydantic response
- **D-06:** Frozen DTOs use `@dataclass(frozen=True, slots=True)` per REQUIREMENTS.md ARCH-03
- **D-07:** DTOs live in a new `dtos.py` file per module (alongside models.py, schemas.py)
- **D-08:** DTO naming convention: `{Entity}DTO` (e.g., ProductDTO)
- **D-09:** Service methods return `tuple[int, Sequence[ProductDTO]]` for paginated results -- keeping existing pattern
- **D-10:** ORM-to-DTO conversion happens inside the service via standalone function `product_to_dto()` in `dtos.py` -- converter is module-internal, NOT exported via public.py
- **D-11:** UUIDs represented as `uuid.UUID` in DTOs (not str)
- **D-12:** DTOs include timestamps (id, domain fields, is_active, created_at, updated_at)
- **D-13:** Standalone DTOs -- no base DTO class, each DTO declares all fields explicitly (frozen+slots inheritance is tricky)
- **D-14:** Plain dataclasses, no generic syntax -- DTOs are concrete domain types
- **D-15:** Optional fields use PEP 604 union syntax: `container_id: uuid.UUID | None`
- **D-16:** DTO field ordering: match the SQLAlchemy model's column definition order
- **D-17:** ProductDTO includes all model fields: id, name, type, price, container_id, is_active, created_at, updated_at
- **D-18:** BaseService updated with DTOType generic parameter -- type checker catches services returning ORM objects
- **D-19:** `type Paginated[T] = tuple[int, Sequence[T]]` added to `src/common/types.py` for cleaner signatures
- **D-20:** Enums referenced by DTOs (e.g., ProductType) re-exported via public.py -- consumers get everything from one import
- **D-21:** Two fresh migrations: Migration 1 (schema: tables, indexes, constraints) + Migration 2 (PG triggers)
- **D-22:** Schema migration uses `alembic revision --autogenerate` from current models
- **D-23:** Dev DB is dropped and recreated from scratch -- proves the migration set works end-to-end
- **D-24:** Fresh migration generates enums with lowercase labels (Phase 1 fix baked in from the start)
- **D-25:** Trigger SQL stays in separate .sql files (`src/infrastructure/database/scripts/`) -- migration reads and executes them
- **D-26:** public.py exports: DTOs + Service class + Enums referenced by DTOs (e.g., ProductDTO, CatalogService, ProductType)
- **D-27:** public.py uses `__all__` list for explicit contract enforcement
- **D-28:** UoW is internal -- not exported via public.py (only dependencies.py creates it)
- **D-29:** Exceptions stay internal -- not exported via public.py

### Claude's Discretion
- Whether to add a `get_catalog_service()` dependency factory if one doesn't exist
- Exact trigger SQL adjustments for the fresh migration (preserve behavior, may improve formatting)
- Whether to add type stubs or Protocol definitions for the facade contract
- Exact handling of Alembic version history cleanup

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ARCH-02 | Each module exposes `public.py` facade -- other modules import only from this | Catalog pilot demonstrates the pattern: public.py with `__all__`, re-exports DTOs + Service + Enums. Consumer audit identified 18 import statements to update across 13 files. |
| ARCH-03 | Unified Repository -> Service -> frozen DTO (`dataclasses(frozen=True, slots=True)`) pattern across all modules | ProductDTO with frozen+slots verified on Python 3.14. BaseService gains DTOType generic with PEP 696 default (`= object`). Converter function `product_to_dto()` in dtos.py. |
| DB-01 | Alembic migrations rebuilt from scratch (clean schema) | Delete old versions, add `values_callable` to 8 enum declarations missing it, `alembic revision --autogenerate` from current models. Drop+recreate dev DB to prove clean. |
| DB-02 | PG triggers preserved for ledger balance enforcement (stock + financial) | Trigger SQL in `src/infrastructure/database/scripts/` (2 files verified). Migration 2 reads .sql files and executes. Pattern already established in current `c650cec7ccb0_triggers.py`. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python 3.14+, SQLAlchemy 2.x (async), PostgreSQL, FastAPI, Alembic -- non-negotiable
- **Architecture**: DDD modular monolith -- modules communicate via services, not direct model access
- **Ledger integrity**: PG triggers enforce balance consistency -- application code cannot bypass
- **lazy="raise"**: On bulk-risk SQLAlchemy relationships -- no accidental N+1 queries
- **ondelete="RESTRICT"**: On critical foreign keys -- no silent cascade deletes
- **Service returns**: Frozen DTOs only -- never expose ORM objects to consumers
- **Line length**: 79 characters
- **Absolute imports**: Always from `src.` root, never relative
- **Naming**: `snake_case` files, `PascalCase` classes, `{Entity}DTO` for DTOs, `{Entity}Service` for services

## Standard Stack

### Core (already installed, no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.14+ | Runtime | Project requirement (PEP 695 generics, PEP 696 TypeVar defaults, `uuid.uuid7()`, `StrEnum`) |
| SQLAlchemy | 2.1.0b1 | ORM + async | Project requirement, async mode with asyncpg |
| Alembic | 1.18.4 | Migrations | Project requirement, `--autogenerate` from models |
| dataclasses | stdlib | Frozen DTOs | `@dataclass(frozen=True, slots=True)` -- no external dep needed |

### No New Dependencies Required

This phase requires zero new packages. Everything is stdlib or already installed:
- `dataclasses` -- stdlib (frozen DTOs)
- `uuid` -- stdlib (UUID fields in DTOs)
- `datetime` -- stdlib (timestamp fields in DTOs)
- `collections.abc.Sequence` -- stdlib (paginated return types)
- `pathlib.Path` -- stdlib (reading .sql trigger files in migration)

## Architecture Patterns

### New File Structure (Catalog pilot)
```
src/modules/catalog/
    __init__.py          # Empty (unchanged)
    public.py            # NEW: facade -- exports DTOs, Service, Enums
    dtos.py              # NEW: ProductDTO + product_to_dto() converter
    models.py            # MODIFIED: add values_callable to enum
    schemas.py           # UNCHANGED: stays for API layer
    services.py          # MODIFIED: returns DTOs instead of ORM objects
    repositories.py      # UNCHANGED: still returns ORM objects
    uow.py               # UNCHANGED: internal
    dependencies.py      # UNCHANGED: internal
    enums.py             # UNCHANGED
    exceptions.py        # UNCHANGED

src/common/
    types.py             # NEW: Paginated type alias
    service.py           # MODIFIED: DTOType generic parameter added
```

### Pattern 1: Frozen DTO with Converter

**What:** Each module defines frozen dataclass DTOs and a converter function.
**When to use:** Every service method that returns domain data.

**Field order reference from Product model (verified):**
1. `id` (from BaseModel)
2. `returnable_item_id` (first declared column)
3. `type` (ProductType enum)
4. `name` (str)
5. `price` (int -- BIGINT in PG)
6. `attributes` (dict -- JSONB in PG)
7. `is_active` (from BaseModel)
8. `created_at` (from BaseModel)
9. `updated_at` (from BaseModel)

```python
# src/modules/catalog/dtos.py
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.modules.catalog.enums import ProductType


@dataclass(frozen=True, slots=True)
class ProductDTO:
    """Frozen data transfer object for Product.

    Field order matches Product model column definitions.
    """

    id: uuid.UUID
    returnable_item_id: uuid.UUID | None
    type: ProductType
    name: str
    price: int
    attributes: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


def product_to_dto(product: Any) -> ProductDTO:
    """Convert ORM Product instance to frozen DTO."""
    return ProductDTO(
        id=product.id,
        returnable_item_id=product.returnable_item_id,
        type=product.type,
        name=product.name,
        price=product.price,
        attributes=dict(product.attributes),
        is_active=product.is_active,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )
```

**Verified:** `@dataclass(frozen=True, slots=True)` works on Python 3.14. Assignment to fields raises `FrozenInstanceError`.

**Note on `attributes` field type:** The model uses `JSONB` which returns a Python dict. The DTO uses `dict[str, Any]` for the converter's `dict()` copy to avoid shared mutable state. The `Any` matches the existing pattern used in `schemas.py` and `repositories.py` across the project.

### Pattern 2: public.py Facade

**What:** Single-file public API that other modules import from.
**When to use:** Every module's external contract.

```python
# src/modules/catalog/public.py
"""Catalog module public API.

Other modules MUST import only from this file.
Do not import from catalog.models, catalog.repositories,
catalog.uow, or catalog.exceptions directly.
"""
from src.modules.catalog.dtos import ProductDTO
from src.modules.catalog.enums import ProductType
from src.modules.catalog.services import CatalogService

__all__ = [
    "CatalogService",
    "ProductDTO",
    "ProductType",
]
```

**Ruff compatibility:** The `__all__` list exempts these imports from Ruff's `F401` (unused import) rule. No Ruff configuration change needed -- verified with the project's Ruff rule set `["E", "W", "F", "I", "B", "C4", "UP", "SIM"]`.

### Pattern 3: BaseService with DTOType Generic

**What:** Add a 4th generic parameter `DTOType` to `BaseService`.
**When to use:** All service subclasses (but only Catalog is updated in this phase).

Current signature (verified from `src/common/service.py`):
```python
class BaseService[
    ModelType: BaseModel,
    CreateSchemaType: PydanticSchema,
    UoWType: BaseSQLAlchemyUoW,
](ABC):
```

New signature:
```python
class BaseService[
    ModelType: BaseModel,
    CreateSchemaType: PydanticSchema,
    UoWType: BaseSQLAlchemyUoW,
    DTOType = object,
](ABC):
```

**PEP 696 TypeVar defaults:** Landed in Python 3.13. Using `DTOType = object` as default means existing 3-param subclasses like `BaseOrderService[Order, ..., OrderUnitOfWork]` continue to work without modification. Only CatalogService adds the 4th param in this phase.

**Impact on existing services (verified):**
- `CatalogService(BaseService[Product, ProductCreate, CatalogUnitOfWork])` -- updated to `CatalogService(BaseService[Product, ProductCreate, CatalogUnitOfWork, ProductDTO])`
- Other services keep 3 params, default `DTOType = object` prevents breakage

### Pattern 4: Paginated Type Alias

**What:** PEP 695 type alias for paginated results.
**File:** `src/common/types.py` (new file -- `src/common/` currently contains: `__init__.py`, `pagination.py` (empty), `repository.py`, `service.py`, `uow.py`)

```python
# src/common/types.py
from collections.abc import Sequence

type Paginated[T] = tuple[int, Sequence[T]]
```

### Pattern 5: Service DTO Conversion

**What:** Service methods convert ORM objects to DTOs before returning.

Current CatalogService methods (verified from `src/modules/catalog/services.py`) that return ORM objects and need conversion:
- `get_catalog()` -- returns `Sequence[Product]`, convert to `Sequence[ProductDTO]`
- `get_by_ids()` -- returns `Sequence[Product]`, convert to `Sequence[ProductDTO]`
- `search_by_attribute()` -- returns `Sequence[Product]`, convert to `Sequence[ProductDTO]`
- `add_product()` -- returns `Product`, convert to `ProductDTO`
- Inherited from BaseService: `get()`, `get_multi()`, `add()`, `update()`, `archive()`, `delete()`

**Note on BaseService inherited methods:** The BaseService methods (e.g., `get()`, `get_multi()`) still return `ModelType` (ORM objects). Converting these is an ongoing concern -- in Phase 2, only CatalogService's own methods are converted. BaseService's methods can be overridden in CatalogService or left as-is with `object` return via the DTOType default. The planner must decide the exact scope.

**Recommended approach:** Override the commonly-used inherited methods in CatalogService to add DTO conversion, demonstrating the full pattern. Methods like `archive()` and `delete()` that return `bool` can stay as-is.

### Pattern 6: API Layer DTO-to-Schema Conversion

**What:** API routers receive DTOs from service, convert to Pydantic response.
**Why:** Pydantic schemas handle serialization (JSON, OpenAPI). DTOs handle internal contract.

The current API routers use `response_model=list[ProductResponse]` which relies on `from_attributes=True` to serialize ORM objects. After this change, services return DTOs (plain dataclasses), and `ProductResponse.model_validate(dto, from_attributes=True)` still works because Pydantic v2 can read from any object with matching attribute names (dataclass slots included).

**Verified from `src/modules/catalog/schemas.py` line 65:** `model_config = ConfigDict(from_attributes=True)` is present on `ProductResponse`.

**No API router changes needed for serialization** -- FastAPI's `response_model` with `from_attributes=True` handles both ORM objects and frozen dataclasses transparently.

### Anti-Patterns to Avoid
- **Importing ORM models outside their module:** After public.py, no module should `from src.modules.catalog.models import Product` -- use `ProductDTO` instead
- **Mutable DTOs:** Never use regular `@dataclass` without `frozen=True` -- the whole point is immutability
- **DTO inheritance:** Don't create `BaseDTO` -- frozen+slots inheritance is fragile and unnecessary (D-13)
- **Exporting converter functions:** `product_to_dto()` is internal to the module -- consumers get DTOs, not converters (D-10)
- **Importing from `__init__.py`:** The facade is `public.py`, not `__init__.py`. Keep `__init__.py` empty

## Consumer Update Inventory

### Complete audit of files importing from `src.modules.catalog.*`

**Category 1: Import CatalogService (update to catalog.public)**
| File | Current Import | New Import |
|------|---------------|------------|
| `src/modules/orders/services.py` | `from src.modules.catalog.services import CatalogService` | `from src.modules.catalog.public import CatalogService` |
| `src/modules/inventory/services.py` | `from src.modules.catalog.services import CatalogService` | `from src.modules.catalog.public import CatalogService` |
| `src/application/client/service.py` | `from src.modules.catalog.services import CatalogService` | `from src.modules.catalog.public import CatalogService` |
| `src/application/client/dependencies.py` | `from src.modules.catalog.services import CatalogService` | `from src.modules.catalog.public import CatalogService` |
| `src/modules/orders/dependencies.py` | `from src.modules.catalog.services import CatalogService` | `from src.modules.catalog.public import CatalogService` |
| `src/modules/inventory/dependencies.py` | `from src.modules.catalog.services import CatalogService` | `from src.modules.catalog.public import CatalogService` |
| `src/api/v1/backoffice/catalog.py` | `from src.modules.catalog.services import CatalogService` | `from src.modules.catalog.public import CatalogService` |
| `src/api/v1/client/catalog.py` | `from src.modules.catalog.services import CatalogService` | `from src.modules.catalog.public import CatalogService` |
| `src/api/v1/courier/catalog.py` | `from src.modules.catalog.services import CatalogService` | `from src.modules.catalog.public import CatalogService` |

**Category 2: Import ProductType enum (update to catalog.public)**
| File | Current Import | New Import |
|------|---------------|------------|
| `src/modules/users/schemas.py` | `from src.modules.catalog.enums import ProductType` | `from src.modules.catalog.public import ProductType` |
| `src/modules/users/queries.py` | `from src.modules.catalog.enums import ProductType` | `from src.modules.catalog.public import ProductType` |
| `src/modules/inventory/schemas.py` | `from src.modules.catalog.enums import ProductType` | `from src.modules.catalog.public import ProductType` |
| `src/application/client/schemas.py` | `from src.modules.catalog.enums import ProductType` | `from src.modules.catalog.public import ProductType` |
| `src/api/v1/backoffice/catalog.py` | `from src.modules.catalog.enums import ProductType` | `from src.modules.catalog.public import ProductType` |
| `src/api/v1/client/catalog.py` | `from src.modules.catalog.enums import ProductType` | `from src.modules.catalog.public import ProductType` |
| `src/api/v1/courier/catalog.py` | `from src.modules.catalog.enums import ProductType` | `from src.modules.catalog.public import ProductType` |
| `src/core/seeder.py` | `from src.modules.catalog.enums import ProductType` | `from src.modules.catalog.public import ProductType` |
| `tests/integration/conftest.py` | `from src.modules.catalog.enums import ProductType` | `from src.modules.catalog.public import ProductType` |

**Category 3: Import Pydantic schemas (API layer only -- schemas NOT in public.py -- KEEP)**
| File | Current Import | Action |
|------|---------------|--------|
| `src/api/v1/backoffice/catalog.py` | `from src.modules.catalog.schemas import ProductCreate, ProductResponse, ProductUpdate` | KEEP -- schemas are API-layer concerns, imported directly |
| `src/api/v1/client/catalog.py` | `from src.modules.catalog.schemas import ProductResponse` | KEEP |
| `src/api/v1/courier/catalog.py` | `from src.modules.catalog.schemas import ProductResponse` | KEEP |
| `src/modules/inventory/schemas.py` | `from src.modules.catalog.schemas import ProductResponse` | KEEP -- cross-module schema import, acceptable for now |
| `src/modules/orders/schemas.py` | `from src.modules.catalog.schemas import ProductResponse` | KEEP |

**Category 4: Import dependencies (internal wiring -- NOT moved to public.py -- KEEP)**
| File | Current Import | Action |
|------|---------------|--------|
| `src/api/v1/backoffice/catalog.py` | `from src.modules.catalog.dependencies import get_catalog_service` | KEEP |
| `src/api/v1/client/catalog.py` | `from src.modules.catalog.dependencies import get_catalog_service` | KEEP |
| `src/api/v1/courier/catalog.py` | `from src.modules.catalog.dependencies import get_catalog_service` | KEEP |
| `src/application/client/dependencies.py` | `from src.modules.catalog.dependencies import get_catalog_service` | KEEP |
| `src/modules/orders/dependencies.py` | `from src.modules.catalog.dependencies import get_catalog_service` | KEEP |
| `src/modules/inventory/dependencies.py` | `from src.modules.catalog.dependencies import get_catalog_service` | KEEP |

**Category 5: Import ProductRepository directly (application-layer UoWs -- DEFER)**
| File | Current Import | Action |
|------|---------------|--------|
| `src/application/order/uow.py` | `from src.modules.catalog.repositories import ProductRepository` | DEFER to Phase 6 (ARCH-04) |
| `src/application/courier/uow.py` | `from src.modules.catalog.repositories import ProductRepository` | DEFER to Phase 6 |
| `src/application/client/uow.py` | `from src.modules.catalog.repositories import ProductRepository` | DEFER to Phase 6 |
| `src/application/inventories/uow.py` | `from src.modules.catalog.repositories import ProductRepository` | DEFER to Phase 6 |

**Category 6: Import Product ORM model (model registry -- KEEP)**
| File | Current Import | Action |
|------|---------------|--------|
| `src/infrastructure/database/models.py` | `from src.modules.catalog.models import Product` | KEEP -- model registry for Alembic autogenerate |
| `src/modules/catalog/repositories.py` | internal to catalog | KEEP |
| `src/modules/catalog/services.py` | internal to catalog | KEEP |
| `tests/integration/conftest.py` | `from src.infrastructure.database.models import ... Product ...` | KEEP -- creates ORM objects via session directly |

**Category 7: TYPE_CHECKING imports of Product model (KEEP)**
| File | Current Import | Action |
|------|---------------|--------|
| `src/modules/inventory/models.py` | `from src.modules.catalog.models import Product` (under TYPE_CHECKING) | KEEP -- SQLAlchemy relationship type hints |
| `src/modules/orders/models.py` | `from src.modules.catalog.models import Product` (under TYPE_CHECKING) | KEEP |

**Category 8: Internal catalog imports (KEEP -- module-internal)**
| File | Current Import | Action |
|------|---------------|--------|
| `src/modules/catalog/models.py` | `from src.modules.catalog.enums import ProductType` | KEEP -- internal |
| `src/modules/catalog/schemas.py` | `from src.modules.catalog.enums import ProductType` | KEEP -- internal |
| `src/modules/catalog/repositories.py` | `from src.modules.catalog.enums import ProductType` | KEEP -- internal |
| `src/modules/catalog/services.py` | multiple internal imports | KEEP -- internal |
| `src/modules/catalog/dependencies.py` | multiple internal imports | KEEP -- internal |
| `src/modules/catalog/uow.py` | `from src.modules.catalog.repositories import ProductRepository` | KEEP -- internal |

### Summary: 18 import statements updated (across 13 files), 23+ kept as-is, 4 deferred

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Immutable data objects | Custom `__setattr__` override | `@dataclass(frozen=True, slots=True)` | stdlib, no bugs, slots give memory + speed benefits |
| Type aliases | String constants or `TypeAlias` | PEP 695 `type Paginated[T] = ...` | Native syntax on Python 3.14, better tooling support |
| Enum label control | Manual enum-to-string mapping | `values_callable=lambda e: [m.value for m in e]` | SQLAlchemy built-in, ensures PG labels match Python values |
| Migration SQL execution | String interpolation | `pathlib.Path(...).read_text()` + `op.execute()` | Clean separation, SQL stays in .sql files per D-25 |
| Public API enforcement | Convention-only ("don't import internals") | `__all__` in public.py + future pytest-archon rules (Phase 6) | Explicit contract, tooling can verify |

**Key insight:** Every pattern in this phase uses stdlib or existing SQLAlchemy features. No new dependencies.

## Migration Rebuild Details

### Enum Label Fix (Critical for D-24)

**Problem:** 8 of 10 SQLAlchemy `Enum()` declarations across models are missing `values_callable`. Without it, Alembic autogenerate creates PG enum labels from **member names** (uppercase), but asyncpg maps `StrEnum` values (which may be lowercase) back from PG. This causes runtime failures for enums where name != value.

**Current migration state (verified from `cefde77d7774_init.py`):** ALL enum labels in the existing migration are UPPERCASE member names, even for finance enums where `values_callable` was added during Phase 1 (because the migration was already generated before the fix was applied to models).

**Models requiring `values_callable` addition (verified audit):**

| File | Enum Declaration | Member Names | Values | Fix Needed |
|------|-----------------|-------------|--------|------------|
| `src/modules/catalog/models.py` | `product_type_enum` (module-level) | WATER, CONTAINER, EQUIPMENT | water, container, equipment | YES -- name != value |
| `src/modules/users/models.py` | `Enum(AuthProvider, ...)` (inline, line 29) | LOCAL, GOOGLE, TELEGRAM, APPLE | local, google, telegram, apple | YES -- name != value |
| `src/modules/users/models.py` | `Enum(Role, ...)` (inline, line 71) | SYSTEM, ADMIN, ... | system, admin, ... | YES -- name != value |
| `src/modules/orders/models.py` | `Enum(PaymentMethod, ...)` (inline, line 43) | CASH, CARD, CONTRACT | cash, card, contract | YES -- name != value |
| `src/modules/orders/models.py` | `Enum(OrderStatus, ...)` (inline, line 53) | NEW, ASSIGNED, ... | new, assigned, ... | YES -- name != value |
| `src/modules/inventory/models.py` | `Enum(InventoryType, ...)` (inline, line 42) | WAREHOUSE, COURIER, ... | WAREHOUSE, COURIER, ... | ADD for uniformity (name == value) |
| `src/modules/inventory/models.py` | `Enum(TransferType, ...)` (inline, line 131) | COURIER_LOAD, ... | COURIER_LOAD, ... | ADD for uniformity (name == value) |
| `src/modules/inventory/models.py` | `Enum(TransferStatus, ...)` (inline, line 141) | DRAFT, COMPLETED, CANCELLED | DRAFT, COMPLETED, CANCELLED | ADD for uniformity (name == value) |
| `src/modules/finances/models.py` | `account_type_enum` (module-level, line 16) | Already has `values_callable` | -- | NO change needed |
| `src/modules/finances/models.py` | `transaction_status_enum` (module-level, line 23) | Already has `values_callable` | -- | NO change needed |

**Safest approach:** Add `values_callable` to ALL enum declarations (including inventory where name == value). This makes the pattern uniform and prevents future bugs if enum values change.

### Migration Rebuild Procedure

1. **Fix all enum declarations** in model files -- add `values_callable` where missing (8 declarations)
2. **Delete old migration files** -- remove `alembic/versions/cefde77d7774_init.py` and `alembic/versions/c650cec7ccb0_triggers.py`
3. **Generate fresh schema migration:** `uv run alembic revision --autogenerate -m "init"`
4. **Create trigger migration manually:** `uv run alembic revision -m "triggers"` then add SQL execution code
5. **Trigger migration reads .sql files:** Use `pathlib.Path` to read from `src/infrastructure/database/scripts/`
6. **Drop and recreate dev DB:** Use Docker compose volume reset:
   - DB is in `deploy/compose.db.yml` (container: `postgres`, volume: `postgres_data`)
   - Command: `docker compose -f deploy/compose.db.yml down -v && docker compose -f deploy/compose.db.yml up -d`
   - Wait for health check: `pg_isready` configured with 10s interval
7. **Run migrations:** `uv run alembic upgrade head`
8. **Run seed + tests:** Verify init_data() and characterization tests pass

**Note on compose files (verified):**
- `deploy/compose.db.yml` -- PostgreSQL 18-alpine only (volume: `postgres_data`)
- `deploy/compose.dev.yml` -- FastAPI service only (references external network)
- The `Makefile` uses `deploy/compose.dev.yml` for `make up/down`, but for DB volume reset, use `compose.db.yml`

### Trigger Migration Pattern

The current trigger migration (`c650cec7ccb0`) inlines SQL as Python multi-line strings. Per D-25, the fresh migration should read from .sql files instead.

**Verified: Two .sql files exist:**
- `src/infrastructure/database/scripts/update_account_balances.sql` (47 lines) -- function + trigger for `transactions` table
- `src/infrastructure/database/scripts/update_inventory_balances.sql` (34 lines) -- function + trigger for `stock_transactions` table

Each .sql file contains the complete DROP TRIGGER + CREATE OR REPLACE FUNCTION + CREATE TRIGGER sequence. A single `op.execute()` per file handles everything.

```python
# alembic/versions/XXXX_triggers.py
from pathlib import Path

from alembic import op

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "infrastructure"
    / "database"
    / "scripts"
)


def upgrade() -> None:
    account_sql = (
        SCRIPTS_DIR / "update_account_balances.sql"
    ).read_text()
    op.execute(account_sql)

    inventory_sql = (
        SCRIPTS_DIR / "update_inventory_balances.sql"
    ).read_text()
    op.execute(inventory_sql)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trigger_update_inventory_balances "
        "ON stock_transactions;"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "update_inventory_balances();"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trigger_update_account_balances "
        "ON transactions;"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "update_account_balances();"
    )
```

**Path resolution verified:** From `alembic/versions/XXXX.py`, `.parents[2]` goes to project root, then `src/infrastructure/database/scripts/` leads to the .sql files.

## Common Pitfalls

### Pitfall 1: Frozen Dataclass with Mutable Default
**What goes wrong:** Using `dict` as default value in frozen dataclass fails at class definition.
**Why it happens:** Frozen dataclasses require immutable defaults or `field(default_factory=...)`.
**How to avoid:** For `attributes: dict[str, Any]`, do NOT set a default. The converter always provides the value explicitly.
**Warning signs:** `ValueError: mutable default <class 'dict'> for field attributes is not allowed`.

### Pitfall 2: Pydantic from_attributes with Slots Dataclass
**What goes wrong:** `ProductResponse.model_validate(dto)` fails if `from_attributes=True` is not set.
**Why it happens:** Pydantic v2 defaults to dict-mode validation. With `from_attributes=True` (verified present in `ProductResponse.model_config`), it uses `getattr()` which works on slots dataclasses.
**How to avoid:** Verify `model_config = ConfigDict(from_attributes=True)` is present on response schemas.
**Warning signs:** `ValidationError: Input should be a valid dictionary`.

### Pitfall 3: Enum Label Mismatch Breaks Existing Data
**What goes wrong:** If the DB has existing data with old UPPERCASE labels and the new migration creates lowercase labels, all existing rows become unreadable.
**Why it happens:** PG enum types are case-sensitive. `'WATER'` != `'water'`.
**How to avoid:** Since D-23 mandates dropping and recreating the DB from scratch, this is not a concern for the fresh migration. But document clearly that this is a destructive operation -- only safe for dev.
**Warning signs:** `asyncpg.exceptions.InvalidTextRepresentationError: invalid input value for enum`.

### Pitfall 4: Alembic Version History Contamination
**What goes wrong:** Old migration revision IDs remain in `alembic_version` table after deleting migration files.
**Why it happens:** Alembic tracks applied revisions in the DB. Deleting files without cleaning the table causes "Can't locate revision" errors.
**How to avoid:** Drop the dev DB entirely (D-23) so the `alembic_version` table is gone. Fresh `alembic upgrade head` starts clean.
**Warning signs:** `alembic.util.exc.CommandError: Can't locate revision identified by 'cefde77d7774'`.

### Pitfall 5: BaseService DTOType Breaking Existing Subclasses
**What goes wrong:** Adding a 4th generic parameter to `BaseService` breaks all existing services that only pass 3 params.
**Why it happens:** Python PEP 695 generics require all params to be specified unless defaults are provided.
**How to avoid:** Use `DTOType = object` as default (PEP 696, Python 3.13+) so existing 3-param subclasses continue to work unchanged.
**Warning signs:** `TypeError: Too few type arguments`.

### Pitfall 6: Application-Layer UoW Imports Not Updated
**What goes wrong:** Updating `src/application/order/uow.py` to import from `catalog.public` would require exporting `ProductRepository` -- which violates D-28 (UoW/repo are internal).
**Why it happens:** Application-layer UoWs directly compose repositories from multiple modules -- this is the ARCH-04 problem deferred to Phase 6.
**How to avoid:** Leave application-layer UoW imports as-is in Phase 2. There are exactly 4 files affected: `src/application/{order,courier,client,inventories}/uow.py`.
**Warning signs:** Attempting to add `ProductRepository` to public.py exports.

### Pitfall 7: Docker Compose File Confusion
**What goes wrong:** Running `docker compose -f deploy/compose.dev.yml down -v` doesn't drop the DB volume because the FastAPI compose doesn't own the postgres volume.
**Why it happens:** The postgres container with its volume is in `deploy/compose.db.yml`, not `deploy/compose.dev.yml`.
**How to avoid:** Use `deploy/compose.db.yml` for DB volume operations. The Makefile's `make up/down` targets use `compose.dev.yml` (FastAPI container), not the DB.
**Warning signs:** `alembic upgrade head` succeeds but old data still present.

### Pitfall 8: SaleType Not a PG Enum
**What goes wrong:** Treating `SaleType` as a PG enum that needs `values_callable`.
**Why it happens:** `SaleType` is defined in `src/modules/orders/enums.py` as a `StrEnum`, but `Order.sale_type` uses `String(30)`, NOT `Enum()`. It is stored as a plain string column.
**How to avoid:** Do not add `values_callable` for SaleType -- it is not used as a PG enum type.
**Warning signs:** None (would just be wasted effort).

## Code Examples

### Complete ProductDTO (verified field order from model)
```python
# src/modules/catalog/dtos.py
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.modules.catalog.enums import ProductType


@dataclass(frozen=True, slots=True)
class ProductDTO:
    """Frozen data transfer object for Product.

    Field order matches Product model column
    definitions.
    """

    id: uuid.UUID
    returnable_item_id: uuid.UUID | None
    type: ProductType
    name: str
    price: int
    attributes: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


def product_to_dto(product: Any) -> ProductDTO:
    """Convert ORM Product instance to frozen DTO."""
    return ProductDTO(
        id=product.id,
        returnable_item_id=product.returnable_item_id,
        type=product.type,
        name=product.name,
        price=product.price,
        attributes=dict(product.attributes),
        is_active=product.is_active,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )
```

### Complete public.py (verified Ruff F401 compatibility)
```python
# src/modules/catalog/public.py
"""Catalog module public API.

Other modules MUST import only from this file.
Do not import from catalog.models,
catalog.repositories, catalog.uow, or
catalog.exceptions directly.
"""
from src.modules.catalog.dtos import ProductDTO
from src.modules.catalog.enums import ProductType
from src.modules.catalog.services import CatalogService

__all__ = [
    "CatalogService",
    "ProductDTO",
    "ProductType",
]
```

### BaseService with DTOType Default
```python
# src/common/service.py (modified signature)
class BaseService[
    ModelType: BaseModel,
    CreateSchemaType: PydanticSchema,
    UoWType: BaseSQLAlchemyUoW,
    DTOType = object,
](ABC):
    ...
```

### CatalogService with 4th Generic Param
```python
# src/modules/catalog/services.py (modified)
class CatalogService(
    BaseService[
        Product,
        ProductCreate,
        CatalogUnitOfWork,
        ProductDTO,
    ]
):
    ...
```

### Paginated Type Alias
```python
# src/common/types.py
from collections.abc import Sequence

type Paginated[T] = tuple[int, Sequence[T]]
```

### Enum Fix Pattern (add values_callable)
```python
# In any model file -- add values_callable:
product_type_enum = Enum(
    ProductType,
    name="product_type_enum",
    native_enum=True,
    create_type=True,
    values_callable=lambda e: [m.value for m in e],
)
```

For inline enum declarations (e.g., in users/models.py):
```python
role: Mapped[Role] = mapped_column(
    Enum(
        Role,
        name="user_role_enum",
        native_enum=True,
        create_type=True,
        values_callable=lambda e: [m.value for m in e],
    ),
    nullable=False,
    ...
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Return ORM objects from services | Return frozen DTOs | This phase | Prevents lazy-load errors, enforces immutability |
| Import module internals directly | Import from `public.py` facade | This phase | Explicit contract, future pytest-archon enforcement |
| Alembic enum with member names | `values_callable` for lowercase labels | Phase 1 fix, Phase 2 bakes in | Prevents asyncpg StrEnum mapping failures |
| PEP 484 `TypeAlias` | PEP 695 `type X[T] = ...` | Python 3.12+ | Cleaner syntax, better tooling |
| `typing.TypeVar` | PEP 695 generics `class Foo[T: Bound]` | Python 3.12+ | Already used in project |
| Manual TypeVar defaults | PEP 696 `DTOType = object` | Python 3.13+ | Backward-compatible generic param extension |

## Open Questions

1. **BaseService inherited methods: override or leave?**
   - What we know: BaseService's `get()`, `get_multi()`, `add()`, `update()` return `ModelType` (ORM objects). CatalogService inherits these.
   - What's unclear: Should CatalogService override all inherited methods to return DTOs, or only its own methods (like `get_catalog()`, `add_product()`)?
   - Recommendation: Override `get()`, `get_multi()`, and `add()` in CatalogService to return DTOs. Leave `archive()` and `delete()` (return `bool`) as-is. This demonstrates the complete DTO pattern for the pilot module.

2. **Should `get_catalog_service()` import path change?**
   - What we know: Per D-28, dependencies.py is internal. API routers import `get_catalog_service` from `src.modules.catalog.dependencies`.
   - Recommendation: Keep dependencies.py imports as-is. Dependency factories are FastAPI DI wiring, not module-to-module contracts. Verified: `get_catalog_service` exists at `src/modules/catalog/dependencies.py` line 15.

3. **Trigger SQL files: formatting concerns?**
   - What we know: The .sql files use compact formatting (minimal whitespace). The current trigger migration has well-formatted SQL with comments.
   - Recommendation: Leave .sql files as-is. The new migration reads them verbatim. Formatting is a cosmetic concern that doesn't affect behavior.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2+ with pytest-asyncio (auto mode) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/integration/ -x -v` |
| Full suite command | `uv run pytest -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ARCH-02 | public.py facade exports correct symbols, consumers import from it | unit | `uv run pytest tests/unit/test_catalog_public.py -x` | No -- Wave 0 |
| ARCH-03 | Service returns frozen DTO, not ORM object; DTO is immutable | unit | `uv run pytest tests/unit/test_catalog_dto.py -x` | No -- Wave 0 |
| DB-01 | `alembic upgrade head` produces working schema from empty DB | integration | `uv run alembic upgrade head` (idempotent check) | Implicit in existing test setup |
| DB-02 | PG triggers enforce ledger balances after migration rebuild | integration | `uv run pytest tests/integration/test_delivery_fulfillment.py -x` | Yes -- Phase 1 |
| ARCH-02+03 | Existing characterization tests pass after facade + DTO conversion | integration | `uv run pytest tests/integration/ -x -v` | Yes -- Phase 1 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/integration/ -x -v`
- **Per wave merge:** `uv run pytest -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_catalog_public.py` -- verifies public.py exports (`__all__` contents, importability)
- [ ] `tests/unit/test_catalog_dto.py` -- verifies ProductDTO is frozen, has correct fields, converter works
- [ ] `tests/unit/__init__.py` -- must be created (`tests/unit/` directory exists but is empty)

*(Existing integration tests from Phase 1 cover DB-01 and DB-02 implicitly -- they exercise the full ORM + PG trigger chain)*

## Sources

### Primary (HIGH confidence)
- **Codebase audit** -- Direct reading of all files that import from `src.modules.catalog.*` (exhaustive grep across `src/` and `tests/`)
- **Model file verification** -- All 10 enum declarations across 5 model files verified for `values_callable` presence
- **Migration file audit** -- Existing `cefde77d7774_init.py` verified: all enum labels are UPPERCASE member names
- **Trigger SQL verification** -- Both .sql files read and confirmed complete (function + trigger in each)
- **Docker compose audit** -- Both `compose.db.yml` (postgres) and `compose.dev.yml` (fastapi) verified for correct volume management

### Secondary (MEDIUM confidence)
- **PEP 696 TypeVar defaults** -- Confirmed landed in Python 3.13 via [PEP 696](https://peps.python.org/pep-0696/). Project uses Python 3.14+.
- **Pydantic v2 `from_attributes`** -- Works with frozen dataclass slots objects (Pydantic uses `getattr()` which works on slots objects). Verified `from_attributes=True` present on `ProductResponse`.

### Tertiary (LOW confidence)
- None -- all findings verified against actual codebase and official PEP documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all stdlib/existing
- Architecture: HIGH -- patterns verified against actual codebase files and Python 3.14 feature availability
- Pitfalls: HIGH -- enum label issue confirmed in existing migration, BaseService generics verified against PEP 695/696
- Migration rebuild: HIGH -- existing migration structure understood, .sql files audited, Docker compose files verified
- Consumer update scope: HIGH -- exhaustive grep audit of all imports with per-file verification

**Research date:** 2026-03-28 (re-validated)
**Valid until:** 2026-04-28 (stable -- no external dependency changes expected)
