# Codebase Structure

**Analysis Date:** 2026-03-27

## Directory Layout

```
munavvar-a/
├── src/                        # Backend (Python/FastAPI)
│   ├── main.py                 # App entry point (creates FastAPI instance)
│   ├── api/                    # Presentation layer (HTTP)
│   │   ├── server.py           # App factory: create_app(), middleware, lifespan
│   │   ├── exceptions/         # Global exception handlers
│   │   │   └── handlers.py     # AppException -> JSON, validation errors, 500s
│   │   ├── middlewares/        # ASGI middleware
│   │   │   ├── request_id.py   # X-Request-ID injection + structlog binding
│   │   │   └── logger.py       # Access log (method, path, status, duration)
│   │   └── v1/                 # API version 1
│   │       ├── __init__.py     # Assembles api_v1_router from all sub-routers
│   │       ├── auth/           # Login and registration endpoints
│   │       ├── backoffice/     # Admin panel endpoints (12 sub-routers)
│   │       ├── client/         # Client-facing endpoints (orders, catalog, profile)
│   │       └── courier/        # Courier-facing endpoints (orders, catalog, profile)
│   ├── application/            # Cross-domain orchestration services
│   │   ├── client/             # Client onboarding, CRUD, inventory management
│   │   ├── courier/            # Courier onboarding, CRUD
│   │   ├── inventories/        # (Partially commented out, stub)
│   │   └── order/              # Order-specific schemas (OrderCreate, CartValidate)
│   ├── modules/                # Domain modules (core business logic)
│   │   ├── auth/               # Authentication (login, JWT issuance)
│   │   ├── users/              # User management (registration, identity)
│   │   ├── catalog/            # Product catalog (CRUD, search, pricing)
│   │   ├── orders/             # Order lifecycle (creation, fulfillment, delivery)
│   │   ├── inventory/          # Stock management (transfers, warehouses, transports)
│   │   └── finances/           # Financial ledger (accounts, transactions)
│   ├── common/                 # Shared base classes
│   │   ├── repository.py       # BaseRepository[ModelType] -- generic CRUD
│   │   ├── service.py          # BaseService[Model, Schema, UoW] -- generic service
│   │   ├── uow.py             # IUnitOfWork -- abstract interface
│   │   └── pagination.py       # (Empty)
│   ├── core/                   # Cross-cutting concerns
│   │   ├── config.py           # Settings (pydantic-settings, loads from .env)
│   │   ├── constants.py        # SYSTEM_USER_ID, WALKIN_USER_ID
│   │   ├── exceptions.py       # AppException hierarchy (7 exception types)
│   │   ├── context.py          # ContextVar for request_id
│   │   ├── logger.py           # structlog configuration
│   │   ├── init.py             # Database initialization (system user, accounts, inventories)
│   │   ├── seeder.py           # Test data generator
│   │   └── security/           # Auth infrastructure
│   │       ├── jwt.py          # create_access_token, decode_access_token
│   │       ├── password.py     # bcrypt hash/verify
│   │       └── permissions.py  # Scope class, ROLE_SCOPES mapping
│   ├── infrastructure/         # Technical infrastructure
│   │   ├── database/
│   │   │   ├── base.py         # BaseModel (SQLAlchemy declarative base)
│   │   │   ├── session.py      # AsyncEngine, async_session_maker, get_session
│   │   │   ├── uow.py         # BaseSQLAlchemyUoW (concrete UoW base)
│   │   │   ├── models.py       # Model registry (__all__ imports for Alembic)
│   │   │   └── scripts/        # Raw SQL for triggers
│   │   ├── cache/              # (Empty -- Redis client placeholder)
│   │   ├── clients/            # (Empty -- external HTTP client placeholder)
│   │   └── external/           # (Empty -- external service placeholder)
│   └── workers/                # (Empty -- background job placeholder)
├── frontend/                   # React 19 SPA (git submodule)
│   ├── src/
│   │   ├── app/                # Redux store, router config
│   │   ├── pages/              # 15 page components (JSX + CSS Modules)
│   │   ├── components/         # Shared components (layout, ui, DateRangePicker, SalesAnalytics)
│   │   ├── services/           # RTK Query API slices (14 API files)
│   │   ├── features/           # Feature slices (auth)
│   │   ├── utils/              # Utility functions
│   │   └── assets/             # Static assets (icons, images)
│   └── docs/                   # Frontend-specific documentation
├── alembic/                    # Database migration system
│   ├── env.py                  # Alembic environment config
│   └── versions/               # Migration files
│       ├── cefde77d7774_init.py          # Initial schema (all tables)
│       └── c650cec7ccb0_triggers.py      # PG trigger functions
├── tests/                      # Test suite
│   ├── conftest.py             # Shared fixtures
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   └── factories/              # Test data factories
├── deploy/                     # Deployment configuration
│   ├── compose.dev.yml         # Local PostgreSQL + Redis
│   ├── compose.db.yml          # DB-only compose
│   ├── docker/                 # Dockerfile(s)
│   └── k8s/                    # Kubernetes manifests
├── scripts/
│   └── entrypoint.sh           # Container entrypoint
├── docs/                       # Project documentation
│   └── superpowers/            # Feature specs and plans
├── pyproject.toml              # Python project config (uv, ruff, pytest)
├── uv.lock                     # Dependency lockfile
├── alembic.ini                 # Alembic config
├── Makefile                    # Developer commands
├── railway.toml                # Railway deployment config
├── .env.example                # Environment variable template
├── .pre-commit-config.yaml     # Pre-commit hooks config
└── CLAUDE.md                   # AI assistant instructions (empty)
```

## Directory Purposes

**`src/api/v1/backoffice/`:**
- Purpose: Admin panel API endpoints
- Contains: 12 router files -- `catalog.py`, `clients.py`, `couriers.py`, `orders.py`, `transfers.py`, `transport.py`, `warehouses.py`, `users.py`, `finances.py`, `profile.py`, `shifts.py`, `system.py`
- Key files: `orders.py` (most complex, handles delivery + warehouse pickup flows), `clients.py` (client CRUD + onboarding), `transfers.py` (stock transfer management)

**`src/api/v1/client/`:**
- Purpose: Client-facing API (mobile app / web)
- Contains: `login.py`, `profile.py`, `catalog.py`, `orders.py`, `inventory.py`
- Key file: `orders.py` (client order creation, tara check)

**`src/api/v1/courier/`:**
- Purpose: Courier terminal API
- Contains: `profile.py`, `catalog.py`, `orders.py`

**`src/modules/` (each module follows identical structure):**
- Purpose: Domain logic encapsulation
- Contains per module:
  - `models.py` -- SQLAlchemy ORM models
  - `repositories.py` -- Data access (extends BaseRepository)
  - `services.py` -- Business logic
  - `schemas.py` -- Pydantic request/response schemas
  - `uow.py` -- Unit of Work (interface + implementation)
  - `dependencies.py` -- FastAPI DI factory functions
  - `enums.py` -- Domain enumerations
  - `exceptions.py` -- Domain-specific exceptions
  - `__init__.py`

**`src/application/` (cross-domain services):**
- Purpose: Complex operations that span multiple domain modules
- Contains per sub-package: `service.py`, `schemas.py`, `uow.py`, `dependencies.py`, `exceptions.py`
- Key files:
  - `client/service.py` -- `ClientService` (onboarding flow: create user + identity + account + inventory + initial balance + optional first order)
  - `courier/service.py` -- `CourierService` (create courier + identity + account)
  - `order/schemas.py` -- Shared order schemas used by both client and backoffice APIs

## Key File Locations

**Entry Points:**
- `src/main.py`: App instantiation (imports `create_app` from `src/api/server.py`)
- `src/api/server.py`: FastAPI factory with middleware stack and router registration

**Configuration:**
- `src/core/config.py`: `Settings` class (Pydantic BaseSettings, loaded from `.env`)
- `src/core/constants.py`: Hard-coded system UUIDs (`SYSTEM_USER_ID`, `WALKIN_USER_ID`)
- `alembic.ini`: Alembic configuration
- `pyproject.toml`: Python package config, ruff settings, pytest settings

**Core Domain Logic:**
- `src/modules/orders/services.py`: `BaseOrderService` -- order creation, delivery fulfillment, warehouse pickup, financial settlement (~1150 lines, most complex service)
- `src/modules/inventory/services.py`: `TransportService`, `WarehouseService`, `StockTransferService`, `CapitalizeTaraService` -- all stock movement operations
- `src/modules/users/services.py`: `UserService` -- registration with multi-entity creation (user + identity + account + inventory + initial balance)
- `src/application/client/service.py`: `ClientService` -- full client onboarding orchestration
- `src/application/courier/service.py`: `CourierService` -- courier CRUD with account/inventory creation

**Database:**
- `src/infrastructure/database/base.py`: `BaseModel` -- shared columns (id, is_active, created_at, updated_at)
- `src/infrastructure/database/session.py`: Engine + session factory (asyncpg pool: 15+10 connections)
- `src/infrastructure/database/uow.py`: `BaseSQLAlchemyUoW` -- transaction management base
- `src/infrastructure/database/models.py`: Model registry that imports all models for Alembic autodetection

**Auth & Security:**
- `src/modules/auth/dependencies.py`: `get_token_payload()` (fast, no DB), `get_current_user()` (slow, DB lookup)
- `src/core/security/permissions.py`: `Scope` class (all permissions), `ROLE_SCOPES` mapping
- `src/core/security/jwt.py`: Token encode/decode

**Database Triggers (SQL):**
- `alembic/versions/c650cec7ccb0_triggers.py`: Trigger definitions (Python migration wrapping SQL)
- `src/infrastructure/database/scripts/update_account_balances.sql`: Financial balance trigger SQL
- `src/infrastructure/database/scripts/update_inventory_balances.sql`: Inventory balance trigger SQL

**Testing:**
- `tests/conftest.py`: Shared test fixtures
- `tests/unit/`: Unit tests
- `tests/integration/`: Integration tests
- `tests/factories/`: Test data factories

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (e.g., `stock_transfer_service.py`)
- Module `__init__.py` files: Used for router assembly and re-exports
- Frontend pages: `PascalCase.jsx` with co-located `PascalCase.module.css`
- Frontend services: `camelCaseApi.js`

**Directories:**
- Backend: `snake_case` (e.g., `src/modules/orders/`)
- Frontend: `camelCase` for components (`DateRangePicker/`), `lowercase` for standard dirs (`pages/`, `services/`)

**Classes:**
- Models: Singular PascalCase (e.g., `Order`, `StockTransfer`, `Balance`)
- Repositories: `{Model}Repository` (e.g., `OrderRepository`, `InventoryRepository`)
- Services: `{Domain}Service` or `{Feature}Service` (e.g., `CatalogService`, `StockTransferService`, `ClientService`)
- UoWs: `{Domain}UnitOfWork` (e.g., `CatalogUnitOfWork`, `BaseOrderUnitOfWork`)
- Schemas: Descriptive PascalCase (e.g., `OrderCreate`, `ClientResponse`, `WarehouseSaleCreate`)
- Exceptions: `{Description}Error` (e.g., `InsufficientStockError`, `OrderNotFoundError`)

**API Routers:**
- Variable: `{name}_router` (e.g., `orders_router`, `catalog_router`)
- Prefix pattern: plural noun (`/orders`, `/clients`, `/couriers`)
- Backoffice uses camelCase aliases for query params (`clientId`, `dateFrom`)

**Database Tables:**
- Auto-generated from model class name: CamelCase -> snake_case_plural (e.g., `StockTransfer` -> `stock_transfers`)
- Override with `__tablename__` when needed (e.g., `inventory_balances`)

## Where to Add New Code

**New API Endpoint (existing domain):**
- Add route function to appropriate router file in `src/api/v1/{audience}/{domain}.py`
- Use `Security(get_current_user, scopes=[Scope.XXX])` for auth
- Inject service via `Depends(get_{domain}_service)`

**New Domain Module:**
1. Create directory: `src/modules/{module_name}/`
2. Create files following the standard module pattern:
   - `models.py` -- SQLAlchemy models extending `BaseModel`
   - `repositories.py` -- Repository class extending `BaseRepository`
   - `services.py` -- Service class extending `BaseService`
   - `schemas.py` -- Pydantic schemas
   - `uow.py` -- UoW interface + implementation
   - `dependencies.py` -- FastAPI DI factories
   - `enums.py` -- Domain enumerations
   - `exceptions.py` -- Domain exceptions extending `AppException`
   - `__init__.py`
3. Register models in `src/infrastructure/database/models.py` for Alembic detection
4. Create migration: `make migrate m="add_{module_name}"`

**New Cross-Domain Service:**
- Create directory under `src/application/{feature}/`
- Create composite UoW that includes repositories from all needed domains
- Register dependency in `dependencies.py`

**New API Version:**
- Create `src/api/v2/` following same pattern as `src/api/v1/`
- Mount in `src/api/server.py` with `settings.API_V2_STR` prefix

**New Background Worker:**
- Place in `src/workers/` (currently empty placeholder)
- Would need Celery/ARQ integration in `src/infrastructure/`

**New External Integration:**
- Client code in `src/infrastructure/clients/` (currently empty)
- External service adapters in `src/infrastructure/external/` (currently empty)

**New Frontend Page:**
- Create `frontend/src/pages/{PageName}.jsx` + `{PageName}.module.css`
- Create API slice in `frontend/src/services/{domainApi}.js`
- Register route in `frontend/src/app/` router config

## Special Directories

**`src/infrastructure/database/scripts/`:**
- Purpose: Raw SQL files for complex database logic (trigger functions)
- Generated: No (hand-written SQL)
- Committed: Yes

**`src/infrastructure/cache/`, `src/infrastructure/clients/`, `src/infrastructure/external/`:**
- Purpose: Placeholder directories for future Redis cache, HTTP clients, and external service integrations
- Generated: No
- Committed: Yes (empty directories)
- Note: Redis config exists in `src/core/config.py` (REDISHOST, REDISPORT, etc.) but no Redis client code yet

**`src/workers/`:**
- Purpose: Placeholder for background job processing (Celery/ARQ)
- Generated: No
- Committed: Yes (empty directory)

**`frontend/`:**
- Purpose: React 19 admin SPA (git submodule -- has its own `.git`)
- Generated: Build artifacts in `frontend/dist/` (not committed)
- Committed: Submodule reference committed to parent repo

**`alembic/versions/`:**
- Purpose: Database migration files
- Generated: Auto-generated by `alembic revision --autogenerate`
- Committed: Yes (migrations are source of truth for schema)

**`deploy/`:**
- Purpose: Docker Compose files and Kubernetes manifests for deployment
- Contains: `compose.dev.yml` (local dev), `compose.db.yml` (DB only), `docker/` (Dockerfiles), `k8s/` (K8s manifests)
- Committed: Yes

---

*Structure analysis: 2026-03-27*
