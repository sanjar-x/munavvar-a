

<!-- GSD:project-start source:PROJECT.md -->
## Project

**HOD (Home & Office Delivery)**

A B2B/B2C water delivery management platform that automates the full cycle: from client order intake through courier delivery, stock movement between warehouses, and financial reconciliation. Built as a DDD modular monolith with Python/FastAPI/PostgreSQL. Currently a working MVP requiring architectural cleanup and API buildout.

**Core Value:** The dual ledger system (Stock Ledger + Financial Ledger) must always maintain integrity — every stock movement and financial transaction is traceable through double-entry bookkeeping. If everything else breaks, the ledgers must be correct.

### Constraints

- **Tech stack**: Python 3.14+, SQLAlchemy 2.x (async), PostgreSQL, FastAPI, Alembic — non-negotiable
- **Architecture**: DDD modular monolith — modules communicate via services, not direct model access
- **Ledger integrity**: PG triggers enforce balance consistency — application code cannot bypass
- **lazy="raise"**: On bulk-risk SQLAlchemy relationships — no accidental N+1 queries
- **ondelete="RESTRICT"**: On critical foreign keys — no silent cascade deletes
- **Service returns**: Frozen DTOs only — never expose ORM objects to consumers
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.14 - Backend API, business logic, database models, migrations (`src/`, `alembic/`, `scripts/`)
- JavaScript (ES2020+, JSX) - Frontend admin SPA (`frontend/src/`)
- SQL (PL/pgSQL) - Database triggers for balance materialization (`src/infrastructure/database/scripts/*.sql`)
- Shell (POSIX sh) - Entrypoint and deployment scripts (`scripts/entrypoint.sh`)
## Runtime
- CPython 3.14 (requires-python = ">=3.14")
- Base Docker image: `python:3.14-slim-trixie` (`deploy/docker/Dockerfile.railway`)
- ASGI server: Uvicorn (bundled with FastAPI via `fastapi[standard]`)
- Node.js (version not pinned; no `.nvmrc` or `.node-version` present)
- Browser target: ES2020+ (configured in `frontend/eslint.config.js`)
- `uv` (Astral) - Python dependency management and task runner
- `npm` - Frontend dependency management
## Frameworks
- FastAPI >=0.132.0 - Async REST API framework (`src/api/server.py`)
- SQLAlchemy >=2.1.0b1 (async mode) - ORM with asyncpg driver (`src/infrastructure/database/session.py`)
- Pydantic v2 (via pydantic-settings) - Schema validation and settings management (`src/core/config.py`)
- React 19.2.0 - Frontend UI library (`frontend/package.json`)
- Redux Toolkit 2.11.2 + RTK Query - Frontend state management and API layer (`frontend/src/app/store.js`, `frontend/src/services/baseApi.js`)
- Vite 7.3.1 - Frontend build tool (`frontend/vite.config.js`)
- Ruff >=0.15.1 - Python linter and formatter (`pyproject.toml` [tool.ruff])
- ESLint 9.39.1 - JavaScript linter (`frontend/eslint.config.js`)
- pre-commit - Git hooks for code quality (`.pre-commit-config.yaml`)
- pytest >=9.0.2 - Test runner (`pyproject.toml` [tool.pytest.ini_options])
- pytest-asyncio >=1.3.0 - Async test support (asyncio_mode = "auto")
- pytest-cov >=7.0.0 - Coverage reporting
- pytest-archon >=0.0.7 - Architecture/dependency rule enforcement
- httpx >=0.28.1 - Async HTTP test client for FastAPI
- polyfactory >=3.3.0 - Test data factory generation
- Locust >=2.43.3 - Load testing
- ty >=0.0.17 - Astral's Python type checker (dev dependency)
## Key Dependencies
- `fastapi[standard]` >=0.132.0 - API framework (includes uvicorn, httptools, python-multipart)
- `sqlalchemy[asyncio]` >=2.1.0b1 - ORM with async extension
- `asyncpg` >=0.31.0 - PostgreSQL async driver
- `pyjwt` >=2.11.0 - JWT token encoding/decoding (`src/core/security/jwt.py`)
- `pwdlib[argon2,bcrypt]` >=0.3.0 - Password hashing with Bcrypt (`src/core/security/password.py`)
- `alembic` >=1.18.4 - Database schema migrations (`alembic/`)
- `structlog` >=25.5.0 - Structured logging framework (`src/core/logger.py`)
- `structlog-config` >=0.11.0 - Structlog configuration helpers
- `pydantic-settings` - Environment variable loading and validation (`src/core/config.py`)
- `react-router-dom` ^7.13.0 - Frontend client-side routing (`frontend/package.json`)
## Configuration
- `SECRET_KEY` - JWT signing key (SecretStr)
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` - PostgreSQL connection
- `REDISHOST`, `REDISPORT`, `REDISUSER`, `REDISPASSWORD` - Redis connection (configured but not yet used in application code)
- `ENVIRONMENT` - "dev" | "test" | "prod" (default: "dev")
- `DEBUG` - Enables SQL echo and console log renderer (default: False)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - JWT TTL (default: 10080 = 7 days)
- `CORS_ORIGINS` - Comma-separated allowed origins
- `ADMIN_PHONE`, `ADMIN_PASSWORD` - Initial admin seeding credentials
- `VITE_API_BASE_URL` - Backend API base URL
- `VITE_USE_PROXY` - Enable dev proxy ("true"/"false")
- `VITE_PROXY_TARGET` - Proxy target for dev mode
- `VITE_MOCK_SALES_ANALYTICS` - Enable mock analytics data
- `pyproject.toml` - Python project config, Ruff config, pytest config
- `alembic.ini` - Alembic migration config
- `frontend/vite.config.js` - Vite build config with `@` alias to `./src`
- `frontend/eslint.config.js` - ESLint flat config
- `frontend/vercel.json` - Vercel SPA rewrites
- `.pre-commit-config.yaml` - pre-commit hooks (ruff, trailing whitespace, YAML check, large file check, secret detection)
- Line length: 79
- Auto-fix enabled
- Rule sets: E, W, F, I, B, C4, UP, SIM
- Ignored: UP037
## Platform Requirements
- Python >=3.14 (latest; uses new generic syntax `class Foo[T: Base]`)
- Docker + Docker Compose (for local PostgreSQL via `deploy/compose.db.yml`)
- `uv` package manager (replaces pip/poetry)
- Node.js + npm (for frontend)
- Make (optional, for `Makefile` shortcuts)
- Backend: Railway (Dockerfile-based deployment via `railway.toml` pointing to `deploy/docker/Dockerfile.railway`)
- Frontend: Vercel (SPA with `vercel.json` rewrites)
- Database: PostgreSQL 18 (Alpine image in dev; Railway-hosted in prod)
- Entrypoint runs migrations before starting: `scripts/entrypoint.sh`
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Use `snake_case.py` for all Python files
- Module files follow a fixed set per domain: `models.py`, `schemas.py`, `services.py`, `repositories.py`, `uow.py`, `dependencies.py`, `exceptions.py`, `enums.py`
- Router files named by domain entity plural: `users.py`, `orders.py`, `clients.py`, `couriers.py`
- Special files: `queries.py` for read-only CQRS-style query objects (`src/modules/users/queries.py`)
- Use `snake_case` for all functions and methods
- Async functions use `async def` consistently (no sync DB calls)
- Repository methods: `get`, `get_by`, `get_multi`, `add`, `add_many`, `update`, `archive`, `delete`, `count`
- Service methods: business verbs like `register_client`, `create_order`, `assign_courier`, `complete_pickup`
- Private helper methods prefixed with underscore: `_handle_order_fulfillment`, `_process_financial_settlement`, `_ensure_insertable_keys`
- Dependency providers: `get_{entity}_service`, `get_{entity}_uow` (see `src/modules/users/dependencies.py`)
- Use `snake_case` for all variables
- Type annotations required on all function signatures
- `self.uow` for unit of work, `self.session` for DB session in repositories
- Constants: `UPPER_SNAKE_CASE` (see `src/core/constants.py`)
- Context vars: prefixed with underscore `_request_id_ctx_var` (see `src/core/context.py`)
- Use `PascalCase` for classes
- Models: singular nouns matching domain entity (`User`, `Order`, `Product`, `Inventory`)
- Schemas: `{Entity}{Action}` pattern (`UserAdminCreate`, `OrderCreate`, `ProductResponse`)
- Services: `{Entity}Service` (`UserService`, `CatalogService`, `BaseOrderService`)
- Repositories: `{Entity}Repository` (`UserRepository`, `ProductRepository`)
- UoW: `{Entity}UnitOfWork` (`UserUnitOfWork`, `BaseOrderUnitOfWork`)
- Exceptions: descriptive `{Entity}{Problem}Error` (`UserAlreadyExistsError`, `InsufficientStockError`)
- Enums: `PascalCase` class, `UPPER_SNAKE_CASE` or `snake_case` values depending on domain (see below)
- All enums inherit from `enum.StrEnum` (Python 3.11+ style)
- Role/system enums use `snake_case` values: `Role.CLIENT_B2C = "client_b2c"` (`src/modules/users/enums.py`)
- Inventory/transfer enums use `UPPER_SNAKE_CASE` values: `InventoryType.WAREHOUSE = "WAREHOUSE"` (`src/modules/inventory/enums.py`)
- Order enums use `snake_case` values: `OrderStatus.IN_TRANSIT = "in_transit"` (`src/modules/orders/enums.py`)
## Code Style
- Ruff formatter via pre-commit hook
- Line length: 79 characters (`pyproject.toml` `[tool.ruff]`)
- Ruff auto-fix enabled on commit
- Ruff linter with rules: `["E", "W", "F", "I", "B", "C4", "UP", "SIM"]`
- `UP037` ignored (unnecessary `Optional` type annotation)
- Pre-commit hooks also run: trailing-whitespace, end-of-file-fixer, check-yaml, check-merge-conflict, detect-private-key
- `ty:ignore[invalid-argument-type]` used for Starlette/FastAPI middleware typing edge cases
## Import Organization
- Always use absolute imports from `src.` root: `from src.modules.users.services import UserService`
- Never use relative imports
- No path aliases configured
- Use `TYPE_CHECKING` guard for circular dependency prevention in models:
## Error Handling
- `message`: Human-readable Russian string
- `error_code`: `UPPER_SNAKE_CASE` machine-readable code
- `details`: Dict with context (IDs, counts, etc.)
- `AppException` -> business error JSON
- `RequestValidationError` -> Pydantic validation JSON
- `StarletteHTTPException` -> HTTP error JSON
- `Exception` -> unhandled 500 JSON
- Raise domain-specific exceptions from services, never generic `HTTPException`
- Use `ValueError` only for programming errors that should not reach production (e.g., missing courier on delivery)
- Never catch and suppress errors silently in services; let UoW rollback handle cleanup
## Logging
- Dev: `ConsoleRenderer` with colors
- Production: `JSONRenderer`
- Uses `contextvars` for request-scoped context (request_id, IP, method, path)
- Business errors (warning level): via exception handler, not manual logging
- System errors (error level): unhandled exceptions
- HTTP access (info/warning/error by status code): via `AccessLoggerMiddleware`
- Lifecycle events (info): startup, shutdown, seeding
- Successful CRUD operations (noisy)
- Request/response bodies (security risk)
## Comments
- Complex SQL queries: explain the JOIN strategy and why
- Business rules: explain the "why" behind validation logic
- Non-obvious design decisions: explain trade-offs
## Function Design
- Service methods: typically 20-80 lines for complex business operations (e.g., `create_order` in `src/modules/orders/services.py`)
- Repository methods: typically 5-20 lines
- Helper methods: extracted with `_` prefix when logic repeats (e.g., `_handle_order_fulfillment`, `_process_financial_settlement`)
- Use Pydantic schemas for input validation in API layer
- Use `dict[str, Any]` for data passed between repository methods
- Use `model_dump(exclude_unset=True)` to convert schemas to dicts: `data = schema.model_dump(exclude_unset=True)`
- Use `uuid.UUID` for all entity identifiers, never strings
- Repository methods return `ModelType | None` for single lookups, `Sequence[ModelType]` for lists
- Service methods return domain model objects, not schemas (serialization happens at API layer)
- Use `tuple[int, Sequence[ModelType]]` for paginated results with total count
## Module Design
## Dependency Injection Pattern
## Authentication & Authorization Pattern
- Scopes defined as string constants on `Scope` class: `Scope.USERS_WRITE = "users:write"`
- `ROLE_SCOPES` dict maps `Role` -> list of scope strings
- Scopes checked in route via `Security(get_current_user, scopes=[Scope.ORDERS_EDIT])`
## Unit of Work Pattern
## Python Version Features
- PEP 695 generics syntax used extensively:
- `uuid.uuid7()` used for primary keys (UUIDv7 for time-ordered IDs)
- `enum.StrEnum` used for all enums
## API Response Conventions
- `201` for resource creation
- `204` for actions without response body (e.g., block user)
- `200` (default) for reads and updates
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Domain modules (`src/modules/`) own their models, repositories, services, schemas, and enums
- Application layer (`src/application/`) orchestrates cross-domain operations (client onboarding, courier management)
- Unit of Work pattern manages database transactions per-domain with explicit repository composition
- PostgreSQL triggers enforce ledger integrity (financial balances, inventory balances)
- RBAC via JWT scopes derived from role-to-permission mapping at token creation time
## Layers
- Purpose: HTTP routing, request validation, auth enforcement, response serialization
- Location: `src/api/`
- Contains: FastAPI routers grouped by audience (backoffice, client, courier, auth), middleware, exception handlers
- Depends on: Application layer services, Module layer services, Auth dependencies
- Used by: External HTTP clients (frontend SPA, mobile apps)
- Purpose: Cross-domain business processes that span multiple modules
- Location: `src/application/`
- Contains: `client/`, `courier/`, `order/`, `inventories/` -- each with service, schemas, UoW, dependencies, exceptions
- Depends on: Multiple module-level repositories via composite UoWs, CatalogService for price lookups
- Used by: API layer routers (primarily backoffice)
- Purpose: Single-domain business logic, each module owns its data model and rules
- Location: `src/modules/`
- Contains: 6 modules -- `auth`, `users`, `catalog`, `orders`, `inventory`, `finances`
- Depends on: `src/common/` base classes, `src/infrastructure/database/` session/base model
- Used by: Application layer, API layer
- Purpose: Base classes and interfaces shared across all modules
- Location: `src/common/`
- Contains: `BaseRepository` (`repository.py`), `BaseService` (`service.py`), `IUnitOfWork` (`uow.py`)
- Depends on: `src/infrastructure/database/base.py` for BaseModel
- Used by: All modules
- Purpose: Database engine, session management, external integrations (empty stubs for cache/clients/external)
- Location: `src/infrastructure/`
- Contains: SQLAlchemy engine/session (`database/session.py`), BaseSQLAlchemyUoW (`database/uow.py`), BaseModel (`database/base.py`), model registry (`database/models.py`)
- Depends on: `src/core/config.py` for connection strings
- Used by: All UoW implementations, Alembic migrations
- Purpose: Application configuration, security, logging, exception hierarchy, constants
- Location: `src/core/`
- Contains: `config.py` (Settings), `exceptions.py` (AppException hierarchy), `security/` (JWT, password hashing, RBAC permissions), `logger.py` (structlog setup), `context.py` (request ID), `constants.py` (system UUIDs), `seeder.py`, `init.py`
- Depends on: External libs (pydantic-settings, structlog, PyJWT, bcrypt)
- Used by: Every other layer
## Data Flow
- Backend: Stateless request handling. All state in PostgreSQL.
- Balances are materialized views updated by PG triggers, not application code.
- Financial ledger is append-only (strict ledger enforced by triggers that block UPDATE/DELETE).
- Inventory ledger is append-only (same strict enforcement).
## Key Abstractions
- Purpose: Generic CRUD operations for any SQLAlchemy model
- Location: `src/common/repository.py`
- Pattern: Generic class parameterized by model type. Provides `get()`, `get_by()`, `get_multi()`, `add()`, `add_many()`, `update()`, `archive()`, `delete()`, `count()`
- All domain repositories inherit from this
- Purpose: Generic service with standard CRUD delegating to a repository via UoW
- Location: `src/common/service.py`
- Pattern: Triple-generic abstract class. Subclasses implement `_repo` property. Provides `get()`, `get_multi()`, `add()`, `update()`, `archive()`, `delete()`
- Examples: `CatalogService`, `UserService`, `BaseOrderService`
- Purpose: Transaction boundary management
- Interface: `src/common/uow.py` -- defines `__aenter__`, `__aexit__`, `flush()`, `commit()`, `rollback()`
- Implementation: `src/infrastructure/database/uow.py` -- async context manager, handles IntegrityError -> ConflictError conversion
- Domain UoWs compose specific repositories onto a shared session:
- Purpose: Typed business errors that map to HTTP status codes
- Location: `src/core/exceptions.py`
- Pattern: Each exception carries `message`, `status_code`, `error_code`, `details`. Global handler in `src/api/exceptions/handlers.py` converts to standard JSON `{error: {code, message, details}}`
- Subclasses: `NotFoundError` (404), `BadRequestError` (400), `UnauthorizedError` (401), `ForbiddenError` (403), `ConflictError` (409), `UnprocessableEntityError` (422), `ServiceUnavailableError` (503)
- Domain-specific exceptions extend these (e.g., `InsufficientStockError` in `src/modules/inventory/exceptions.py`, `OrderNotFoundError` in `src/modules/orders/exceptions.py`)
- Purpose: Common columns for all database tables
- Location: `src/infrastructure/database/base.py`
- Provides: `id` (UUIDv7), `is_active` (soft-delete flag), `created_at`, `updated_at`
- Auto-generates `__tablename__` from CamelCase class name -> snake_case_plural
## Entry Points
- Location: `src/main.py` (imports from `src/api/server.py`)
- Triggers: `uv run fastapi dev src/main.py` or `make dev`
- Responsibilities: Creates FastAPI app, registers middleware (RequestID -> AccessLogger -> CORS), exception handlers, mounts `api_v1_router` at `/api/v1`
- Location: `alembic/env.py`, `alembic/versions/`
- Triggers: `make upgrade` / `make migrate m="name"`
- Responsibilities: Schema evolution. Two migrations: `cefde77d7774_init.py` (tables), `c650cec7ccb0_triggers.py` (PG trigger functions)
- Location: `src/core/init.py` (`init_data()`)
- Triggers: Called at app startup (via lifespan or seeder)
- Responsibilities: Creates system user, system financial accounts (Revenue, Cash, Card, Discount), virtual inventories (VIRTUAL_VENDOR, VIRTUAL_LOSS), admin user, walk-in user with client inventory
- Location: `src/core/seeder.py`
- Triggers: `POST /api/v1/backoffice/system/seed` (admin-only)
- Responsibilities: Generates test data (products, warehouses, couriers, clients, orders)
- Location: `src/api/server.py` (inline in `create_app()`)
- Endpoint: `GET /health`
## Error Handling
- Domain services raise `AppException` subclasses (e.g., `OrderNotFoundError`, `InsufficientStockError`)
- Module-level exceptions defined in each module's `exceptions.py` file
- Global exception handler in `src/api/exceptions/handlers.py` catches:
- UoW `commit()` converts `IntegrityError` -> `ConflictError` (409)
- Response format: `{"error": {"code": "ERROR_CODE", "message": "...", "details": {...}}}`
## Cross-Cutting Concerns
- Framework: structlog with contextvars
- Configuration: `src/core/logger.py` -- JSON in prod, colored console in dev
- Request correlation: `RequestIDMiddleware` (`src/api/middlewares/request_id.py`) binds `request_id` to structlog context
- Access logging: `AccessLoggerMiddleware` (`src/api/middlewares/logger.py`) logs method, path, status, duration
- Pydantic v2 schemas for all request/response models
- FastAPI `Body()`, `Query()`, `Path()` with constraints (`gt=0`, `ge=0`, `min_length=1`)
- Business validation in service layer (e.g., tara exchange rules, route validation for transfers)
- JWT-based OAuth2 flow
- Token creation: `src/core/security/jwt.py` -- HS256 signed, 7-day expiry
- Two-level auth dependency:
- Scope-based authorization: `Security(get_current_user, scopes=[Scope.ORDERS_READ])`
- 8 roles defined in `src/modules/users/enums.py`: SYSTEM, ADMIN, ACCOUNTANT, STOREKEEPER, CASHIER, COURIER, CLIENT_B2C, CLIENT_B2B
- Permission mapping in `src/core/security/permissions.py`: `ROLE_SCOPES` dict maps each role to its allowed scopes
- Scopes embedded in JWT at login time, checked at request time
- `update_account_balances()` -- on `transactions` INSERT/UPDATE: atomically adjusts `accounts.balance` with deadlock-safe row locking
- `update_inventory_balances()` -- on `stock_transactions` INSERT: upserts `inventory_balances.quantity` via conflict resolution
- Both enforce strict append-only ledger (block DELETE and certain UPDATEs)
- Defined in `alembic/versions/c650cec7ccb0_triggers.py`, SQL source in `src/infrastructure/database/scripts/`
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
