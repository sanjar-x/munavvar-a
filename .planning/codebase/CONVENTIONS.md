# Coding Conventions

**Analysis Date:** 2026-03-27

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python files
- Module files follow a fixed set per domain: `models.py`, `schemas.py`, `services.py`, `repositories.py`, `uow.py`, `dependencies.py`, `exceptions.py`, `enums.py`
- Router files named by domain entity plural: `users.py`, `orders.py`, `clients.py`, `couriers.py`
- Special files: `queries.py` for read-only CQRS-style query objects (`src/modules/users/queries.py`)

**Functions:**
- Use `snake_case` for all functions and methods
- Async functions use `async def` consistently (no sync DB calls)
- Repository methods: `get`, `get_by`, `get_multi`, `add`, `add_many`, `update`, `archive`, `delete`, `count`
- Service methods: business verbs like `register_client`, `create_order`, `assign_courier`, `complete_pickup`
- Private helper methods prefixed with underscore: `_handle_order_fulfillment`, `_process_financial_settlement`, `_ensure_insertable_keys`
- Dependency providers: `get_{entity}_service`, `get_{entity}_uow` (see `src/modules/users/dependencies.py`)

**Variables:**
- Use `snake_case` for all variables
- Type annotations required on all function signatures
- `self.uow` for unit of work, `self.session` for DB session in repositories
- Constants: `UPPER_SNAKE_CASE` (see `src/core/constants.py`)
- Context vars: prefixed with underscore `_request_id_ctx_var` (see `src/core/context.py`)

**Types/Classes:**
- Use `PascalCase` for classes
- Models: singular nouns matching domain entity (`User`, `Order`, `Product`, `Inventory`)
- Schemas: `{Entity}{Action}` pattern (`UserAdminCreate`, `OrderCreate`, `ProductResponse`)
- Services: `{Entity}Service` (`UserService`, `CatalogService`, `BaseOrderService`)
- Repositories: `{Entity}Repository` (`UserRepository`, `ProductRepository`)
- UoW: `{Entity}UnitOfWork` (`UserUnitOfWork`, `BaseOrderUnitOfWork`)
- Exceptions: descriptive `{Entity}{Problem}Error` (`UserAlreadyExistsError`, `InsufficientStockError`)
- Enums: `PascalCase` class, `UPPER_SNAKE_CASE` or `snake_case` values depending on domain (see below)

**Enums:**
- All enums inherit from `enum.StrEnum` (Python 3.11+ style)
- Role/system enums use `snake_case` values: `Role.CLIENT_B2C = "client_b2c"` (`src/modules/users/enums.py`)
- Inventory/transfer enums use `UPPER_SNAKE_CASE` values: `InventoryType.WAREHOUSE = "WAREHOUSE"` (`src/modules/inventory/enums.py`)
- Order enums use `snake_case` values: `OrderStatus.IN_TRANSIT = "in_transit"` (`src/modules/orders/enums.py`)

## Code Style

**Formatting:**
- Ruff formatter via pre-commit hook
- Line length: 79 characters (`pyproject.toml` `[tool.ruff]`)
- Ruff auto-fix enabled on commit

**Linting:**
- Ruff linter with rules: `["E", "W", "F", "I", "B", "C4", "UP", "SIM"]`
- `UP037` ignored (unnecessary `Optional` type annotation)
- Pre-commit hooks also run: trailing-whitespace, end-of-file-fixer, check-yaml, check-merge-conflict, detect-private-key
- `ty:ignore[invalid-argument-type]` used for Starlette/FastAPI middleware typing edge cases

**Run commands:**
```bash
make format       # Ruff format + lint fix
make lint         # Check without fixing
```

## Import Organization

**Order:**
1. Standard library imports (`import uuid`, `from collections.abc import Sequence`)
2. Third-party imports (`from fastapi import ...`, `from sqlalchemy import ...`, `import structlog`)
3. Local imports (`from src.core.exceptions import ...`, `from src.modules.users.schemas import ...`)

**Path style:**
- Always use absolute imports from `src.` root: `from src.modules.users.services import UserService`
- Never use relative imports
- No path aliases configured

**Conditional imports:**
- Use `TYPE_CHECKING` guard for circular dependency prevention in models:
```python
# src/modules/users/models.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.finances.models import Account
    from src.modules.inventory.models import Inventory
```

## Error Handling

**Exception Hierarchy:**
All business exceptions inherit from `AppException` (`src/core/exceptions.py`):
```
AppException (base, HTTP 500)
  +-- NotFoundError (404)
  +-- BadRequestError (400)
  +-- UnauthorizedError (401)
  +-- ForbiddenError (403)
  +-- ConflictError (409)
  +-- UnprocessableEntityError (422)
  +-- ServiceUnavailableError (503)
```

**Pattern - Domain-specific exceptions:**
Each module defines its own exceptions inheriting from the core set. Place in `src/modules/{module}/exceptions.py`:
```python
# src/modules/users/exceptions.py
class UserNotFoundError(NotFoundError):
    def __init__(self, user_id: uuid.UUID):
        super().__init__(
            message=f"Пользователь с идентификатором {user_id} не найден.",
            error_code="USER_NOT_FOUND",
            details={"user_id": user_id},
        )
```

**Exception fields (always include all three):**
- `message`: Human-readable Russian string
- `error_code`: `UPPER_SNAKE_CASE` machine-readable code
- `details`: Dict with context (IDs, counts, etc.)

**Global exception handlers** (`src/api/exceptions/handlers.py`):
- `AppException` -> business error JSON
- `RequestValidationError` -> Pydantic validation JSON
- `StarletteHTTPException` -> HTTP error JSON
- `Exception` -> unhandled 500 JSON

**Standard error JSON format** (consistent across all handlers):
```json
{
  "error": {
    "code": "USER_NOT_FOUND",
    "message": "Пользователь не найден.",
    "details": {"user_id": "..."}
  }
}
```

**Raising exceptions:**
- Raise domain-specific exceptions from services, never generic `HTTPException`
- Use `ValueError` only for programming errors that should not reach production (e.g., missing courier on delivery)
- Never catch and suppress errors silently in services; let UoW rollback handle cleanup

## Logging

**Framework:** structlog (structured logging)

**Configuration:** `src/core/logger.py`
- Dev: `ConsoleRenderer` with colors
- Production: `JSONRenderer`
- Uses `contextvars` for request-scoped context (request_id, IP, method, path)

**Patterns:**
```python
# Module-level logger declaration
import structlog
logger = structlog.get_logger(__name__)

# Or with explicit type
from structlog.stdlib import BoundLogger
logger: BoundLogger = structlog.get_logger(__name__)
```

**When to log:**
- Business errors (warning level): via exception handler, not manual logging
- System errors (error level): unhandled exceptions
- HTTP access (info/warning/error by status code): via `AccessLoggerMiddleware`
- Lifecycle events (info): startup, shutdown, seeding

**Do NOT log:**
- Successful CRUD operations (noisy)
- Request/response bodies (security risk)

## Comments

**Language:** Comments in Russian (project is Russian-speaking team)

**When to Comment:**
- Complex SQL queries: explain the JOIN strategy and why
- Business rules: explain the "why" behind validation logic
- Non-obvious design decisions: explain trade-offs

**Block comments with section headers** are used extensively:
```python
# ==========================================
# 1. СИСТЕМНЫЕ ОШИБКИ И КОНФИГУРАЦИЯ (500)
# ==========================================
```

**Inline comments:** Used for explaining non-obvious values or database column semantics:
```python
comment="Флаг активности записи. False означает логическое удаление.",
```

**JSDoc/TSDoc:** Not applicable (Python project). No docstring convention strictly enforced, but docstrings used on public service methods.

## Function Design

**Size:**
- Service methods: typically 20-80 lines for complex business operations (e.g., `create_order` in `src/modules/orders/services.py`)
- Repository methods: typically 5-20 lines
- Helper methods: extracted with `_` prefix when logic repeats (e.g., `_handle_order_fulfillment`, `_process_financial_settlement`)

**Parameters:**
- Use Pydantic schemas for input validation in API layer
- Use `dict[str, Any]` for data passed between repository methods
- Use `model_dump(exclude_unset=True)` to convert schemas to dicts: `data = schema.model_dump(exclude_unset=True)`
- Use `uuid.UUID` for all entity identifiers, never strings

**Return Values:**
- Repository methods return `ModelType | None` for single lookups, `Sequence[ModelType]` for lists
- Service methods return domain model objects, not schemas (serialization happens at API layer)
- Use `tuple[int, Sequence[ModelType]]` for paginated results with total count

## Module Design

**Standard module structure** (each domain module in `src/modules/{name}/`):
```
src/modules/{name}/
    __init__.py          # Empty
    enums.py             # StrEnum definitions
    models.py            # SQLAlchemy ORM models
    schemas.py           # Pydantic schemas (Create, Update, Response)
    repositories.py      # Data access layer (extends BaseRepository)
    services.py          # Business logic (extends BaseService)
    uow.py               # Unit of Work (interface + implementation)
    dependencies.py      # FastAPI dependency injection providers
    exceptions.py        # Domain-specific exception classes
```
Optional files: `queries.py` for complex read-only CQRS queries (`src/modules/users/queries.py`)

**Exports:** No re-exports from `__init__.py` -- all module `__init__.py` files are empty. Consumers import directly from submodules.

**Central model registry:** `src/infrastructure/database/models.py` imports and re-exports all models via `__all__` for Alembic autogenerate and cross-module imports.

**Barrel Files:** Not used. Import directly: `from src.modules.users.services import UserService`

## Dependency Injection Pattern

**FastAPI DI chain** (see `src/modules/users/dependencies.py`):
```python
# 1. UoW provider (creates UoW with session factory)
def get_user_uow() -> UserUnitOfWork:
    return UserUnitOfWork(session_factory=async_session_maker)

# 2. Service provider (injects UoW into service)
def get_user_service(
    uow: Annotated[UserUnitOfWork, Depends(get_user_uow)],
) -> UserService:
    return UserService(uow=uow)
```

**Router injection pattern:**
```python
@router.post("/")
async def create_user(
    schema: UserAdminCreate,                                          # Request body
    current_admin: Annotated[User, Security(get_current_user, scopes=[Scope.USERS_WRITE])],  # Auth
    user_service: Annotated[UserService, Depends(get_user_service)],  # Service
):
```

**Key rule:** Use `Annotated[Type, Depends(...)]` syntax everywhere. Never use `Depends()` as default value.

## Authentication & Authorization Pattern

**Two-level auth** (`src/modules/auth/dependencies.py`):
1. **Fast path** (`get_token_payload`): JWT decode + scope check, no DB query
2. **Slow path** (`get_current_user`): Fetches user from DB using payload from level 1

**Scope-based RBAC** (`src/core/security/permissions.py`):
- Scopes defined as string constants on `Scope` class: `Scope.USERS_WRITE = "users:write"`
- `ROLE_SCOPES` dict maps `Role` -> list of scope strings
- Scopes checked in route via `Security(get_current_user, scopes=[Scope.ORDERS_EDIT])`

## Unit of Work Pattern

**Interface** (`src/common/uow.py`): Abstract `IUnitOfWork` with `__aenter__`, `__aexit__`, `flush`, `commit`, `rollback`.

**Base implementation** (`src/infrastructure/database/uow.py`): `BaseSQLAlchemyUoW` manages session lifecycle. `commit()` catches `IntegrityError` and raises `ConflictError`.

**Domain UoW** (e.g., `src/modules/users/uow.py`):
```python
class UserUnitOfWork(BaseSQLAlchemyUoW, IUserUnitOfWork):
    async def __aenter__(self) -> "UserUnitOfWork":
        await super().__aenter__()
        self.users = UserRepository(session=self.session)
        self.identities = IdentityRepository(session=self.session)
        # ... more repos
        return self
```

**Usage pattern in services:**
```python
async with self.uow:
    # All operations share the same DB session/transaction
    user = await self.uow.users.add(user_data)
    await self.uow.identities.add(identity_data)
    await self.uow.commit()
    return user
```

## Python Version Features

**Python 3.14+ (required)**:
- PEP 695 generics syntax used extensively:
  ```python
  class BaseRepository[ModelType: BaseModel]:
  class BaseService[ModelType: BaseModel, CreateSchemaType: PydanticSchema, UoWType: BaseSQLAlchemyUoW](ABC):
  ```
- `uuid.uuid7()` used for primary keys (UUIDv7 for time-ordered IDs)
- `enum.StrEnum` used for all enums

## API Response Conventions

**Soft delete:** Use `is_active=False` (archive), never hard delete in production flows. All base queries filter `is_active=True` by default.

**Pagination:** `skip`/`limit` query params, with `total_count` in list responses.

**Path parameter aliasing:** Use camelCase aliases for frontend compatibility:
```python
order_id: Annotated[uuid.UUID, Path(alias="orderId")]
courier_id: Annotated[uuid.UUID | None, Query(alias="courierId")]
```

**Status codes:**
- `201` for resource creation
- `204` for actions without response body (e.g., block user)
- `200` (default) for reads and updates

---

*Convention analysis: 2026-03-27*
