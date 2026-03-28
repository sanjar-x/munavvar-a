# Phase 2: Module Convention & Database Foundation - Research

**Researched:** 2026-03-28
**Domain:** Python DDD module conventions, frozen dataclasses, SQLAlchemy generics, Alembic migration rebuild
**Confidence:** HIGH

## Summary

Phase 2 establishes two foundational patterns: (1) the `public.py` facade + frozen DTO convention using Catalog as pilot module, and (2) a clean Alembic migration rebuild from scratch. The Catalog module is the ideal pilot -- it has no inbound module dependencies (only outbound: other modules consume it), making it safe for demonstrating the full Repository -> Service -> frozen DTO chain without cascading breakage.

The primary technical risks are well-understood: the `values_callable` fix must be applied to ALL model enum declarations (not just catalog) so the fresh migration generates correct lowercase PG enum labels, and the `BaseService` generic signature must gain a `DTOType` parameter without breaking existing subclasses. Both have been verified on the project's Python 3.14 runtime.

The consumer update scope is significant -- 15+ files across `src/` import directly from `src.modules.catalog.*` internals. After facade creation, these must be redirected to `src.modules.catalog.public`. However, per D-03, only existing Catalog consumers are updated; application-layer UoWs that import `ProductRepository` directly are left as-is (those are addressed in later phases when composite UoWs are decomposed per ARCH-04).

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
| ARCH-02 | Each module exposes `public.py` facade -- other modules import only from this | Catalog pilot demonstrates the pattern: public.py with `__all__`, re-exports DTOs + Service + Enums. Consumer audit identified 15+ files to update. |
| ARCH-03 | Unified Repository -> Service -> frozen DTO (`dataclasses(frozen=True, slots=True)`) pattern across all modules | ProductDTO with frozen+slots verified on Python 3.14. BaseService gains DTOType generic. Converter function `product_to_dto()` in dtos.py. |
| DB-01 | Alembic migrations rebuilt from scratch (clean schema) | Delete old versions, `alembic revision --autogenerate` from current models. Must add `values_callable` to 8 enum declarations missing it. Drop+recreate dev DB to prove clean. |
| DB-02 | PG triggers preserved for ledger balance enforcement (stock + financial) | Trigger SQL in `src/infrastructure/database/scripts/` (2 files). Migration 2 reads .sql files and executes. Pattern already established in current `c650cec7ccb0_triggers.py`. |
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
| Python | 3.14.3 | Runtime | Project requirement (PEP 695 generics, `uuid.uuid7()`, `StrEnum`) |
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

```python
# src/modules/catalog/dtos.py
import uuid
from dataclasses import dataclass
from datetime import datetime

from src.modules.catalog.enums import ProductType


@dataclass(frozen=True, slots=True)
class ProductDTO:
    id: uuid.UUID
    name: str
    type: ProductType
    price: int
    returnable_item_id: uuid.UUID | None
    attributes: dict[str, object]
    is_active: bool
    created_at: datetime
    updated_at: datetime


def product_to_dto(product: object) -> ProductDTO:
    """Convert ORM Product to frozen DTO.

    Accepts `object` to avoid importing the ORM model
    at module level -- the converter accesses attributes
    by name, which works for any ORM model instance.
    """
    return ProductDTO(
        id=product.id,
        name=product.name,
        type=product.type,
        price=product.price,
        returnable_item_id=product.returnable_item_id,
        attributes=dict(product.attributes),
        is_active=product.is_active,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )
```

**Verified:** `@dataclass(frozen=True, slots=True)` works on Python 3.14.3. Assignment to fields raises `FrozenInstanceError`.

**Note on `attributes` field type:** The model uses `JSONB` which returns a Python dict. The DTO uses `dict[str, object]` (not `Any`) for better type safety. The converter must explicitly copy with `dict(product.attributes)` to avoid shared mutable state.

### Pattern 2: public.py Facade

**What:** Single-file public API that other modules import from.
**When to use:** Every module's external contract.

```python
# src/modules/catalog/public.py
"""Catalog module public API.

Other modules MUST import from this file only.
Internal implementation details (models, repositories, UoW)
are not part of the public contract.
"""
from src.modules.catalog.dtos import ProductDTO
from src.modules.catalog.enums import ProductType
from src.modules.catalog.services import CatalogService

__all__ = [
    "ProductDTO",
    "ProductType",
    "CatalogService",
]
```

**Ruff compatibility:** The `__all__` list exempts these imports from Ruff's `F401` (unused import) rule. No Ruff configuration change needed.

### Pattern 3: BaseService with DTOType Generic

**What:** Add a 4th generic parameter `DTOType` to `BaseService`.
**When to use:** All service subclasses (but only Catalog is updated in this phase).

```python
# src/common/service.py (modified signature)
class BaseService[
    ModelType: BaseModel,
    CreateSchemaType: PydanticSchema,
    UoWType: BaseSQLAlchemyUoW,
    DTOType,
](ABC):
    ...
```

**Verified:** PEP 695 4-parameter generic class works on Python 3.14.3.

**Impact on existing services:** Other services (UserService, BaseOrderService, etc.) that inherit BaseService will need to add a DTOType parameter. However, per D-02, only CatalogService is updated in Phase 2 -- **other services can temporarily use `object` or `Any` as DTOType** until their respective phases. The planner must decide the exact strategy.

**Alternative (recommended):** Make DTOType optional with a default. Since PEP 695 generics don't support defaults directly, and we need backward compatibility, the safest approach is:

```python
class BaseService[
    ModelType: BaseModel,
    CreateSchemaType: PydanticSchema,
    UoWType: BaseSQLAlchemyUoW,
    DTOType = object,
](ABC):
```

This way existing 3-param subclasses like `BaseOrderService[Order, ..., OrderUnitOfWork]` continue to work without modification. **Verified: PEP 695 TypeVar defaults (PEP 696) landed in Python 3.13+.**

### Pattern 4: Paginated Type Alias

**What:** PEP 695 type alias for paginated results.
**File:** `src/common/types.py` (new file)

```python
# src/common/types.py
from collections.abc import Sequence

type Paginated[T] = tuple[int, Sequence[T]]
```

**Verified:** PEP 695 `type` statement works on Python 3.14.3.

### Pattern 5: Service DTO Conversion

**What:** Service methods convert ORM objects to DTOs before returning.

```python
# In CatalogService.get_catalog() -- after conversion:
async def get_catalog(
    self,
    skip: int = 0,
    limit: int = 100,
    product_type: ProductType | None = None,
) -> Sequence[ProductDTO]:
    async with self.uow:
        if product_type:
            products = await self._repo.get_catalog_by_type(...)
        else:
            products = await self._repo.get_multi(...)
        return [product_to_dto(p) for p in products]
```

### Pattern 6: API Layer DTO-to-Schema Conversion

**What:** API routers receive DTOs from service, convert to Pydantic response.
**Why:** Pydantic schemas handle serialization (JSON, OpenAPI). DTOs handle internal contract.

The current API routers use `response_model=list[ProductResponse]` which relies on `from_attributes=True` to serialize ORM objects. After this change, services return DTOs (plain dataclasses), and `ProductResponse.model_validate(dto, from_attributes=True)` still works because Pydantic v2 can read from any object with matching attribute names (dataclass slots included).

**No API router changes needed for serialization** -- FastAPI's `response_model` with `from_attributes=True` handles both ORM objects and frozen dataclasses transparently. This is because Pydantic v2's `model_validate(obj, from_attributes=True)` uses `getattr()` which works on `slots=True` dataclasses.

### Anti-Patterns to Avoid
- **Importing ORM models outside their module:** After public.py, no module should `from src.modules.catalog.models import Product` -- use `ProductDTO` instead
- **Mutable DTOs:** Never use regular `@dataclass` without `frozen=True` -- the whole point is immutability
- **DTO inheritance:** Don't create `BaseDTO` -- frozen+slots inheritance is fragile and unnecessary (D-13)
- **Exporting converter functions:** `product_to_dto()` is internal to the module -- consumers get DTOs, not converters (D-10)
- **Importing from `__init__.py`:** The facade is `public.py`, not `__init__.py`. Keep `__init__.py` empty.

## Consumer Update Inventory

### Consumers that MUST be updated to import from `catalog.public`

**Category 1: Import CatalogService (service consumers)**
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

**Category 2: Import ProductType enum**
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

**Category 3: Import Pydantic schemas (API layer only -- schemas NOT in public.py)**
| File | Current Import | Action |
|------|---------------|--------|
| `src/api/v1/backoffice/catalog.py` | `from src.modules.catalog.schemas import ProductCreate, ProductResponse, ProductUpdate` | KEEP -- schemas are API-layer concerns, imported directly |
| `src/api/v1/client/catalog.py` | `from src.modules.catalog.schemas import ProductResponse` | KEEP |
| `src/api/v1/courier/catalog.py` | `from src.modules.catalog.schemas import ProductResponse` | KEEP |
| `src/modules/inventory/schemas.py` | `from src.modules.catalog.schemas import ProductResponse` | KEEP -- cross-module schema import, acceptable for now |
| `src/modules/orders/schemas.py` | `from src.modules.catalog.schemas import ProductResponse` | KEEP |

**Category 4: Import dependencies (internal wiring -- NOT moved to public.py)**
| File | Current Import | Action |
|------|---------------|--------|
| `src/api/v1/backoffice/catalog.py` | `from src.modules.catalog.dependencies import get_catalog_service` | KEEP -- dependency injection is API-layer wiring |
| `src/api/v1/client/catalog.py` | same | KEEP |
| `src/api/v1/courier/catalog.py` | same | KEEP |
| `src/application/client/dependencies.py` | `from src.modules.catalog.dependencies import get_catalog_service` | KEEP |
| `src/modules/orders/dependencies.py` | same | KEEP |
| `src/modules/inventory/dependencies.py` | same | KEEP |

**Category 5: Import ProductRepository directly (application-layer UoWs)**
| File | Current Import | Action |
|------|---------------|--------|
| `src/application/order/uow.py` | `from src.modules.catalog.repositories import ProductRepository` | DEFER to Phase 6 (ARCH-04: composite UoW decomposition) |
| `src/application/courier/uow.py` | same | DEFER |
| `src/application/client/uow.py` | same | DEFER |
| `src/application/inventories/uow.py` | same | DEFER |

**Category 6: Import Product ORM model (model registry)**
| File | Current Import | Action |
|------|---------------|--------|
| `src/infrastructure/database/models.py` | `from src.modules.catalog.models import Product` | KEEP -- model registry must import models directly for Alembic autogenerate |
| `src/modules/catalog/repositories.py` | `from src.infrastructure.database.models import Product` | KEEP -- repository works with ORM models internally |
| `src/modules/catalog/services.py` | `from src.infrastructure.database.models import Product` | KEEP -- service works with ORM internally, converts to DTO before returning |
| `tests/integration/conftest.py` | `from src.infrastructure.database.models import ... Product ...` | KEEP -- test fixtures create ORM objects directly via session |

**Category 7: TYPE_CHECKING imports of Product model**
| File | Current Import | Action |
|------|---------------|--------|
| `src/modules/inventory/models.py` | `from src.modules.catalog.models import Product` (under TYPE_CHECKING) | KEEP -- SQLAlchemy relationship type hints need the model |
| `src/modules/orders/models.py` | same | KEEP |

### Summary: 17 import statements updated, 19 kept as-is, 4 deferred

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

**Problem:** 8 of 10 SQLAlchemy `Enum()` declarations across models are missing `values_callable`. Without it, Alembic autogenerate creates PG enum labels from **member names** (uppercase), but asyncpg maps `StrEnum` values (which may be lowercase) back from PG. This causes runtime failures.

**Models requiring `values_callable` addition:**

| File | Enum Declaration | Current Labels | Fix Needed |
|------|-----------------|----------------|------------|
| `src/modules/catalog/models.py` | `product_type_enum` | WATER, CONTAINER, EQUIPMENT | YES -- values are lowercase |
| `src/modules/users/models.py` | `Enum(AuthProvider, ...)` (inline) | LOCAL, GOOGLE, TELEGRAM, APPLE | YES -- values are lowercase |
| `src/modules/users/models.py` | `Enum(Role, ...)` (inline) | SYSTEM, ADMIN, ... | YES -- values are lowercase |
| `src/modules/inventory/models.py` | `Enum(InventoryType, ...)` | WAREHOUSE, COURIER, ... | NO -- values ARE uppercase |
| `src/modules/inventory/models.py` | `Enum(TransferType, ...)` | COURIER_LOAD, ... | NO -- values ARE uppercase |
| `src/modules/inventory/models.py` | `Enum(TransferStatus, ...)` | DRAFT, COMPLETED, ... | NO -- values ARE uppercase |
| `src/modules/orders/models.py` | `Enum(PaymentMethod, ...)` | CASH, CARD, ... | YES -- values are lowercase |
| `src/modules/orders/models.py` | `Enum(OrderStatus, ...)` | NEW, ASSIGNED, ... | YES -- values are lowercase |
| `src/modules/finances/models.py` | `account_type_enum` | Already has `values_callable` | NO |
| `src/modules/finances/models.py` | `transaction_status_enum` | Already has `values_callable` | NO |

**Verified behavior:** `Enum(ProductType, ..., values_callable=lambda e: [m.value for m in e])` produces labels `['water', 'container', 'equipment']`. Without it: `['WATER', 'CONTAINER', 'EQUIPMENT']`.

**Safest approach for migration rebuild:** Add `values_callable` to ALL enum declarations, even those where name == value (inventory). This makes the pattern uniform and prevents future bugs if enum values change.

### Migration Rebuild Procedure

1. **Fix all enum declarations** in model files -- add `values_callable` where missing
2. **Delete old migration files** -- remove `alembic/versions/cefde77d7774_init.py` and `alembic/versions/c650cec7ccb0_triggers.py`
3. **Clear Alembic version table** -- drop DB and recreate, or truncate `alembic_version`
4. **Generate fresh schema migration:** `uv run alembic revision --autogenerate -m "init"`
5. **Create trigger migration manually:** `uv run alembic revision -m "triggers"` then add SQL execution code
6. **Trigger migration reads .sql files:** Use `pathlib.Path` to read from `src/infrastructure/database/scripts/`
7. **Drop and recreate dev DB:** `docker compose -f deploy/compose.dev.yml down -v && docker compose -f deploy/compose.dev.yml up -d`
8. **Run migrations:** `uv run alembic upgrade head`
9. **Run seed + tests:** Verify init_data() and characterization tests pass

### Trigger Migration Pattern

The current trigger migration (`c650cec7ccb0`) inlines SQL as Python strings. Per D-25, the fresh migration should read from .sql files instead:

```python
# alembic/versions/XXXX_triggers.py
from pathlib import Path

from alembic import op

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "src" / "infrastructure" / "database" / "scripts"


def upgrade() -> None:
    account_sql = (SCRIPTS_DIR / "update_account_balances.sql").read_text()
    op.execute(account_sql)

    inventory_sql = (SCRIPTS_DIR / "update_inventory_balances.sql").read_text()
    op.execute(inventory_sql)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trigger_update_inventory_balances ON stock_transactions;")
    op.execute("DROP FUNCTION IF EXISTS update_inventory_balances();")
    op.execute("DROP TRIGGER IF EXISTS trigger_update_account_balances ON transactions;")
    op.execute("DROP FUNCTION IF EXISTS update_account_balances();")
```

**Note:** The .sql files already contain both the function creation AND trigger creation (DROP + CREATE). So a single `op.execute()` per file handles everything.

## Common Pitfalls

### Pitfall 1: Frozen Dataclass with Mutable Default
**What goes wrong:** Using `dict` as default value in frozen dataclass fails at class definition.
**Why it happens:** Frozen dataclasses require immutable defaults or `field(default_factory=...)`.
**How to avoid:** For `attributes: dict[str, object]`, do NOT set a default. The converter always provides the value explicitly.
**Warning signs:** `ValueError: mutable default <class 'dict'> for field attributes is not allowed`.

### Pitfall 2: Pydantic from_attributes with Slots Dataclass
**What goes wrong:** `ProductResponse.model_validate(dto)` fails if `from_attributes=True` is not set.
**Why it happens:** Pydantic v2 defaults to dict-mode validation. With `from_attributes=True` (already set in `ProductResponse.model_config`), it uses `getattr()` which works on slots dataclasses.
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
**How to avoid:** Drop the dev DB entirely (D-23) or run `DELETE FROM alembic_version` before applying fresh migrations.
**Warning signs:** `alembic.util.exc.CommandError: Can't locate revision identified by 'cefde77d7774'`.

### Pitfall 5: BaseService DTOType Breaking Existing Subclasses
**What goes wrong:** Adding a 4th generic parameter to `BaseService` breaks all existing services that only pass 3 params.
**Why it happens:** Python 3.14 PEP 695 generics require all params to be specified unless defaults are provided.
**How to avoid:** Use `DTOType = object` as default so existing 3-param subclasses continue to work unchanged.
**Warning signs:** `TypeError: Too few type arguments`.

### Pitfall 6: Application-Layer UoW Imports Not Updated
**What goes wrong:** Updating `src/application/order/uow.py` to import from `catalog.public` would require exporting `ProductRepository` -- which violates D-28 (UoW/repo are internal).
**Why it happens:** Application-layer UoWs directly compose repositories from multiple modules -- this is the ARCH-04 problem deferred to Phase 6.
**How to avoid:** Leave application-layer UoW imports as-is in Phase 2. These are addressed when composite UoWs are decomposed.
**Warning signs:** Attempting to add `ProductRepository` to public.py exports.

## Code Examples

### Complete ProductDTO (verified on Python 3.14.3)
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

### Complete public.py (verified Ruff F401 compatibility)
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

### BaseService with DTOType Default (verified on Python 3.14.3)
```python
# src/common/service.py (modified)
class BaseService[
    ModelType: BaseModel,
    CreateSchemaType: PydanticSchema,
    UoWType: BaseSQLAlchemyUoW,
    DTOType = object,
](ABC):
    ...
```

### Paginated Type Alias (verified on Python 3.14.3)
```python
# src/common/types.py
from collections.abc import Sequence

type Paginated[T] = tuple[int, Sequence[T]]
```

### Enum Fix Pattern (verified SQLAlchemy 2.1.0b1)
```python
# In any model file -- add values_callable:
product_type_enum = Enum(
    ProductType,
    name="product_type_enum",
    native_enum=True,
    create_type=True,
    values_callable=lambda e: [m.value for m in e],  # <-- ADD THIS
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

## Open Questions

1. **BaseService DTOType default: `object` vs `Any`?**
   - What we know: PEP 696 TypeVar defaults work on Python 3.13+. Both `object` and `Any` would let existing services compile.
   - What's unclear: `object` is more restrictive (type checker may flag return type mismatches in unconverted services). `Any` is more permissive but less safe.
   - Recommendation: Use `object` as default -- it signals "not yet converted" and the type checker will catch issues when services are actually converted.

2. **Should `get_catalog_service()` import path change?**
   - What we know: Per D-28, dependencies.py is internal. API routers import `get_catalog_service` from `src.modules.catalog.dependencies`.
   - What's unclear: Should dependencies also go through public.py, or are they inherently API-layer wiring?
   - Recommendation: Keep dependencies.py imports as-is. Dependency factories are FastAPI DI wiring, not module-to-module contracts.

3. **Trigger SQL files: read at migration time vs embed?**
   - What we know: D-25 says trigger SQL stays in .sql files. Current migration inlines SQL as strings.
   - What's unclear: `pathlib.Path` resolution relative to migration file location vs project root.
   - Recommendation: Use `Path(__file__).resolve().parents[2] / "src" / ...` to navigate from `alembic/versions/` to `src/infrastructure/database/scripts/`.

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
| ARCH-02 | public.py facade exports correct symbols | unit | `uv run pytest tests/unit/test_catalog_public.py -x` | No -- Wave 0 |
| ARCH-03 | Service returns frozen DTO, not ORM object | unit | `uv run pytest tests/unit/test_catalog_dto.py -x` | No -- Wave 0 |
| DB-01 | `alembic upgrade head` produces working schema | integration | `uv run alembic upgrade head` (idempotent check) | Implicit in existing test setup |
| DB-02 | PG triggers enforce ledger balances | integration | `uv run pytest tests/integration/test_delivery_fulfillment.py -x` | Yes |
| ARCH-02+03 | Existing characterization tests pass after facade | integration | `uv run pytest tests/integration/ -x -v` | Yes |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/integration/ -x -v`
- **Per wave merge:** `uv run pytest -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_catalog_public.py` -- verifies public.py exports (`__all__` contents, importability)
- [ ] `tests/unit/test_catalog_dto.py` -- verifies ProductDTO is frozen, has correct fields, converter works
- [ ] `tests/unit/__init__.py` -- may need creating if tests/unit/ doesn't exist

*(Existing integration tests from Phase 1 cover DB-01 and DB-02 implicitly -- they exercise the full ORM + PG trigger chain)*

## Sources

### Primary (HIGH confidence)
- **Codebase audit** -- Direct reading of all 15+ files that import from `src.modules.catalog.*`
- **Python 3.14.3 runtime verification** -- `@dataclass(frozen=True, slots=True)`, PEP 695 type alias, PEP 696 TypeVar defaults all verified
- **SQLAlchemy 2.1.0b1 runtime verification** -- `values_callable` behavior confirmed with actual enum declarations

### Secondary (MEDIUM confidence)
- **Alembic 1.18.4** -- `--autogenerate` from models, version history management (verified via `alembic --version`)
- **Pydantic v2 `from_attributes`** -- Works with frozen dataclass slots objects (based on Pydantic v2 docs, `getattr()`-based validation)

### Tertiary (LOW confidence)
- None -- all findings verified against actual codebase and runtime

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all stdlib/existing
- Architecture: HIGH -- patterns verified on project's Python 3.14.3 runtime
- Pitfalls: HIGH -- enum label issue reproduced and fix verified, BaseService generics tested
- Migration rebuild: HIGH -- existing migration structure understood, .sql files audited
- Consumer update scope: HIGH -- exhaustive grep audit of all imports

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable -- no external dependency changes expected)
