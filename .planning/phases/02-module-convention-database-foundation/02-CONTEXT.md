# Phase 2: Module Convention & Database Foundation - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Establish the public.py facade pattern and frozen DTO convention using Catalog as the pilot module, then rebuild Alembic migrations from scratch. This phase sets the reference implementation that all other modules (Phases 3-6) will follow. Only Catalog is converted — other modules are extracted in their respective phases.

</domain>

<decisions>
## Implementation Decisions

### Pilot Module
- **D-01:** Catalog is the pilot module — simplest, no inbound dependencies, safest for demonstrating the full pattern
- **D-02:** Only Catalog is converted in Phase 2 — other modules follow in Phases 3-6 using Catalog as reference
- **D-03:** All existing consumers of Catalog internals are updated to import from `catalog.public` — proves the facade end-to-end
- **D-04:** Characterization tests from Phase 1 are also updated to import from `catalog.public`
- **D-05:** Pydantic schemas (ProductResponse, etc.) coexist with frozen DTOs — schemas stay for API request/response validation, DTOs are what services return internally. API layer converts DTO → Pydantic response

### Frozen DTO Design
- **D-06:** Frozen DTOs use `@dataclass(frozen=True, slots=True)` per REQUIREMENTS.md ARCH-03
- **D-07:** DTOs live in a new `dtos.py` file per module (alongside models.py, schemas.py)
- **D-08:** DTO naming convention: `{Entity}DTO` (e.g., ProductDTO)
- **D-09:** Service methods return `tuple[int, Sequence[ProductDTO]]` for paginated results — keeping existing pattern
- **D-10:** ORM-to-DTO conversion happens inside the service via standalone function `product_to_dto()` in `dtos.py` — converter is module-internal, NOT exported via public.py
- **D-11:** UUIDs represented as `uuid.UUID` in DTOs (not str)
- **D-12:** DTOs include timestamps (id, domain fields, is_active, created_at, updated_at)
- **D-13:** Standalone DTOs — no base DTO class, each DTO declares all fields explicitly (frozen+slots inheritance is tricky)
- **D-14:** Plain dataclasses, no generic syntax — DTOs are concrete domain types
- **D-15:** Optional fields use PEP 604 union syntax: `container_id: uuid.UUID | None`
- **D-16:** DTO field ordering: match the SQLAlchemy model's column definition order
- **D-17:** ProductDTO includes all model fields: id, name, type, price, container_id, is_active, created_at, updated_at
- **D-18:** BaseService updated with DTOType generic parameter — type checker catches services returning ORM objects
- **D-19:** `type Paginated[T] = tuple[int, Sequence[T]]` added to `src/common/types.py` for cleaner signatures
- **D-20:** Enums referenced by DTOs (e.g., ProductType) re-exported via public.py — consumers get everything from one import

### Migration Rebuild
- **D-21:** Two fresh migrations: Migration 1 (schema: tables, indexes, constraints) + Migration 2 (PG triggers)
- **D-22:** Schema migration uses `alembic revision --autogenerate` from current models
- **D-23:** Dev DB is dropped and recreated from scratch — proves the migration set works end-to-end
- **D-24:** Fresh migration generates enums with lowercase labels (Phase 1 fix baked in from the start)
- **D-25:** Trigger SQL stays in separate .sql files (`src/infrastructure/database/scripts/`) — migration reads and executes them

### Facade Scope
- **D-26:** public.py exports: DTOs + Service class + Enums referenced by DTOs (e.g., ProductDTO, CatalogService, ProductType)
- **D-27:** public.py uses `__all__` list for explicit contract enforcement
- **D-28:** UoW is internal — not exported via public.py (only dependencies.py creates it)
- **D-29:** Exceptions stay internal — not exported via public.py

### Claude's Discretion
- Whether to add a `get_catalog_service()` dependency factory if one doesn't exist
- Exact trigger SQL adjustments for the fresh migration (preserve behavior, may improve formatting)
- Whether to add type stubs or Protocol definitions for the facade contract
- Exact handling of Alembic version history cleanup

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Module convention target
- `src/modules/catalog/` — Pilot module: models.py, schemas.py, services.py, repositories.py, uow.py, dependencies.py, enums.py, exceptions.py
- `src/common/service.py` — BaseService generic class (needs DTOType parameter added)
- `src/common/repository.py` — BaseRepository (stays unchanged)
- `src/common/uow.py` — IUnitOfWork interface (stays unchanged)

### Migration rebuild
- `alembic/versions/cefde77d7774_init.py` — Current schema migration (to be replaced)
- `alembic/versions/c650cec7ccb0_triggers.py` — Current trigger migration (to be replaced)
- `src/infrastructure/database/scripts/` — PG trigger SQL source files (preserved)
- `alembic/env.py` — Alembic environment config
- `src/infrastructure/database/models.py` — Model registry for autogenerate

### Consumers to update
- `src/modules/orders/services.py` — Imports CatalogService for price lookups
- `src/application/order/` — Application-layer references to Catalog
- `tests/integration/conftest.py` — Test fixtures that create Product objects

### Phase 1 test infrastructure
- `tests/conftest.py` — Root conftest (savepoint isolation)
- `tests/integration/test_delivery_fulfillment.py` — Must pass after migration rebuild
- `tests/integration/test_warehouse_pickup.py` — Must pass after migration rebuild
- `tests/integration/test_walkin_sale.py` — Must pass after migration rebuild
- `tests/integration/test_courier_shift_close.py` — Must pass after migration rebuild

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BaseService[ModelType, CreateSchemaType, UoWType]` in `src/common/service.py` — needs DTOType generic added
- `BaseRepository[ModelType]` in `src/common/repository.py` — stays as-is (returns ORM objects)
- `BaseSQLAlchemyUoW` in `src/infrastructure/database/uow.py` — stays as-is
- PG trigger SQL in `src/infrastructure/database/scripts/` — copy to new migration

### Established Patterns
- Module structure: models.py, schemas.py, services.py, repositories.py, uow.py, dependencies.py, enums.py, exceptions.py
- All async with `asyncio_mode = "auto"`
- Absolute imports from `src.` root
- `model_dump(exclude_unset=True)` for schema → dict conversion

### Integration Points
- CatalogService used by OrderService for price snapshots — import path must be updated to catalog.public
- Product model referenced in test fixtures — fixtures need public.py imports
- Alembic env.py reads from `src/infrastructure/database/models.py` model registry

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

*Phase: 02-module-convention-database-foundation*
*Context gathered: 2026-03-28*
