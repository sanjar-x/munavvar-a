# Phase 2: Module Convention & Database Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-28
**Phase:** 02-module-convention-database-foundation
**Areas discussed:** Pilot module, Frozen DTO design, Migration rebuild, Facade scope

---

## Pilot Module

| Option | Description | Selected |
|--------|-------------|----------|
| Catalog | Simplest module, no inbound dependencies. Clean slate for pattern demo. | ✓ |
| Users | Most imported, higher risk but proves pattern under dependency pressure. | |
| Auth | Small, well-isolated. More infra than domain. | |

**User's choice:** Catalog
**Notes:** None

### Follow-up: Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Catalog only | One module enough to establish convention. | ✓ |
| Catalog + Auth | Two modules prove pattern across types. | |
| You decide | | |

**User's choice:** Catalog only

### Follow-up: Consumer Updates

| Option | Description | Selected |
|--------|-------------|----------|
| Update consumers now | Change all imports to catalog.public. | ✓ |
| Leave for later | Add public.py but don't rewrite imports. | |

**User's choice:** Update consumers now

### Follow-up: Test Imports

| Option | Description | Selected |
|--------|-------------|----------|
| Keep direct imports | Tests are internal consumers. | |
| Update test imports too | Tests go through public.py to prove facade. | ✓ |
| You decide | | |

**User's choice:** Update test imports too

### Follow-up: Schema Coexistence

| Option | Description | Selected |
|--------|-------------|----------|
| Both coexist | Pydantic for API, DTOs for service returns. | ✓ |
| Replace Pydantic schemas | DTOs replace response schemas entirely. | |
| You decide | | |

**User's choice:** Both coexist

---

## Frozen DTO Design

| Option | Description | Selected |
|--------|-------------|----------|
| dtos.py | New file alongside models.py and schemas.py. | ✓ |
| Inside public.py | DTOs defined in public.py directly. | |
| Inside schemas.py | Add DTOs to existing schemas.py. | |

**User's choice:** dtos.py

### Follow-up: Naming Convention
**User's choice:** ProductDTO ({Entity}DTO pattern)

### Follow-up: List Returns
**User's choice:** tuple[int, Sequence[DTO]] (existing pattern)

### Follow-up: Conversion Location
**User's choice:** Standalone function in dtos.py (product_to_dto)

### Follow-up: UUID Type
**User's choice:** uuid.UUID (not str)

### Follow-up: Timestamp Fields
**User's choice:** Include timestamps (created_at, updated_at)

### Follow-up: Base DTO
**User's choice:** Standalone DTOs (no base class)

### Follow-up: Generics
**User's choice:** Plain dataclasses (no generic syntax)

### Follow-up: Optional Fields
**User's choice:** PEP 604 union syntax (Type | None)

### Follow-up: ProductDTO Fields
**User's choice:** All model fields

### Follow-up: BaseService Update
**User's choice:** Update BaseService with DTOType generic parameter

### Follow-up: Paginated Type Alias
**User's choice:** Yes, `type Paginated[T] = tuple[int, Sequence[T]]` in common/types.py

### Follow-up: DTO Field Ordering
**User's choice:** Match model definition order

### Follow-up: Converter Export
**User's choice:** Internal only (not via public.py)

### Follow-up: Enums in DTOs
**User's choice:** Re-export via public.py

---

## Migration Rebuild

| Option | Description | Selected |
|--------|-------------|----------|
| Two migrations | Schema + triggers separate. | ✓ |
| Single migration | Everything in one file. | |
| You decide | | |

**User's choice:** Two migrations

### Follow-up: Autogenerate
**User's choice:** Autogenerate from current models

### Follow-up: Dev DB
**User's choice:** Drop and recreate from scratch

### Follow-up: Enum Labels
**User's choice:** Include Phase 1 fix (lowercase labels from start)

### Follow-up: Trigger SQL Location
**User's choice:** Keep separate .sql files in scripts/

---

## Facade Scope

| Option | Description | Selected |
|--------|-------------|----------|
| DTOs + Service + Enums | Export what consumers need from one import. | ✓ |
| DTOs + Service + Enums + Exceptions | Also export module-specific exceptions. | |
| DTOs + Service only | Minimal, enums separate. | |
| You decide | | |

**User's choice:** DTOs + Service + Enums

### Follow-up: __all__
**User's choice:** Explicit __all__ list

### Follow-up: UoW Export
**User's choice:** Internal only (not exported)

---

## Claude's Discretion

- get_catalog_service() dependency factory details
- Trigger SQL formatting adjustments
- Type stubs or Protocol definitions
- Alembic version history cleanup

## Deferred Ideas

None — discussion stayed within phase scope
