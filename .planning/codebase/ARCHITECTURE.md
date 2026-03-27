# Architecture

**Analysis Date:** 2026-03-27

## Pattern Overview

**Overall:** Modular Monolith with DDD-inspired layers

**Key Characteristics:**
- Domain modules (`src/modules/`) own their models, repositories, services, schemas, and enums
- Application layer (`src/application/`) orchestrates cross-domain operations (client onboarding, courier management)
- Unit of Work pattern manages database transactions per-domain with explicit repository composition
- PostgreSQL triggers enforce ledger integrity (financial balances, inventory balances)
- RBAC via JWT scopes derived from role-to-permission mapping at token creation time

## Layers

**API Layer (Presentation):**
- Purpose: HTTP routing, request validation, auth enforcement, response serialization
- Location: `src/api/`
- Contains: FastAPI routers grouped by audience (backoffice, client, courier, auth), middleware, exception handlers
- Depends on: Application layer services, Module layer services, Auth dependencies
- Used by: External HTTP clients (frontend SPA, mobile apps)

**Application Layer (Orchestration):**
- Purpose: Cross-domain business processes that span multiple modules
- Location: `src/application/`
- Contains: `client/`, `courier/`, `order/`, `inventories/` -- each with service, schemas, UoW, dependencies, exceptions
- Depends on: Multiple module-level repositories via composite UoWs, CatalogService for price lookups
- Used by: API layer routers (primarily backoffice)

**Module Layer (Domain):**
- Purpose: Single-domain business logic, each module owns its data model and rules
- Location: `src/modules/`
- Contains: 6 modules -- `auth`, `users`, `catalog`, `orders`, `inventory`, `finances`
- Depends on: `src/common/` base classes, `src/infrastructure/database/` session/base model
- Used by: Application layer, API layer

**Common Layer (Shared Abstractions):**
- Purpose: Base classes and interfaces shared across all modules
- Location: `src/common/`
- Contains: `BaseRepository` (`repository.py`), `BaseService` (`service.py`), `IUnitOfWork` (`uow.py`)
- Depends on: `src/infrastructure/database/base.py` for BaseModel
- Used by: All modules

**Infrastructure Layer:**
- Purpose: Database engine, session management, external integrations (empty stubs for cache/clients/external)
- Location: `src/infrastructure/`
- Contains: SQLAlchemy engine/session (`database/session.py`), BaseSQLAlchemyUoW (`database/uow.py`), BaseModel (`database/base.py`), model registry (`database/models.py`)
- Depends on: `src/core/config.py` for connection strings
- Used by: All UoW implementations, Alembic migrations

**Core Layer (Cross-Cutting):**
- Purpose: Application configuration, security, logging, exception hierarchy, constants
- Location: `src/core/`
- Contains: `config.py` (Settings), `exceptions.py` (AppException hierarchy), `security/` (JWT, password hashing, RBAC permissions), `logger.py` (structlog setup), `context.py` (request ID), `constants.py` (system UUIDs), `seeder.py`, `init.py`
- Depends on: External libs (pydantic-settings, structlog, PyJWT, bcrypt)
- Used by: Every other layer

## Data Flow

**Order Creation (Client Checkout):**

1. Client sends `POST /api/v1/client/orders/` with `OrderCreate` schema
2. Router in `src/api/v1/client/orders.py` validates JWT scopes via `Security(get_current_user, scopes=[Scope.ORDERS_EDIT])`
3. FastAPI DI resolves `BaseOrderService` via `get_base_order_service()` in `src/modules/orders/dependencies.py`
4. `BaseOrderService.create_order()` in `src/modules/orders/services.py`:
   - Calls `CatalogService.get_by_ids()` to fetch current prices (Snapshot Pattern)
   - Opens `BaseOrderUnitOfWork` context (`async with self.uow`)
   - Validates returnable tara balances against `inventory_balances` (with `FOR UPDATE` lock)
   - Optionally capitalizes missing tara (INITIAL_BALANCE transfer via VIRTUAL_VENDOR)
   - Creates `Order` + `OrderItem` records
   - Commits -- PG trigger on `stock_transactions` auto-updates `inventory_balances`
5. Returns eager-loaded `Order` for response serialization

**Order Delivery Fulfillment:**

1. Admin calls `PATCH /api/v1/backoffice/orders/{orderId}/status` with `new_status=delivered`
2. `BaseOrderService.update_status()` detects delivery transition
3. `_handle_order_fulfillment()` atomically:
   - Locks courier inventory (`FOR UPDATE`)
   - Validates courier has sufficient stock
   - Creates `CLIENT_DELIVERY` StockTransfer (Courier -> Client) with StockTransaction entries
   - Creates `CLIENT_RETURN` StockTransfer (Client -> Courier) for returnable tara
   - Creates financial transactions (Revenue -> Client debt, Client -> Courier/Card payment)
4. Commit triggers:
   - `update_inventory_balances()` trigger on `stock_transactions` table updates `inventory_balances`
   - `update_account_balances()` trigger on `transactions` table updates `accounts.balance`

**Warehouse Pickup Flow:**

1. Admin calls `POST /api/v1/backoffice/orders/warehouse-sale` with `WarehouseSaleCreate`
2. Creates order with `sale_type=WAREHOUSE_PICKUP` and `warehouse_id`
3. `PATCH /api/v1/backoffice/orders/{orderId}/complete-pickup` triggers `_handle_warehouse_pickup()`:
   - WAREHOUSE_SALE transfer (Warehouse -> Client)
   - WAREHOUSE_TARA_RETURN transfer (Client -> Warehouse)
   - For anonymous (walk-in) clients: LOSS_WRITE_OFF cleanup transfer
   - Financial settlement (Revenue -> Client -> Cash)

**State Management:**
- Backend: Stateless request handling. All state in PostgreSQL.
- Balances are materialized views updated by PG triggers, not application code.
- Financial ledger is append-only (strict ledger enforced by triggers that block UPDATE/DELETE).
- Inventory ledger is append-only (same strict enforcement).

## Key Abstractions

**BaseRepository[ModelType]:**
- Purpose: Generic CRUD operations for any SQLAlchemy model
- Location: `src/common/repository.py`
- Pattern: Generic class parameterized by model type. Provides `get()`, `get_by()`, `get_multi()`, `add()`, `add_many()`, `update()`, `archive()`, `delete()`, `count()`
- All domain repositories inherit from this

**BaseService[ModelType, CreateSchemaType, UoWType]:**
- Purpose: Generic service with standard CRUD delegating to a repository via UoW
- Location: `src/common/service.py`
- Pattern: Triple-generic abstract class. Subclasses implement `_repo` property. Provides `get()`, `get_multi()`, `add()`, `update()`, `archive()`, `delete()`
- Examples: `CatalogService`, `UserService`, `BaseOrderService`

**IUnitOfWork / BaseSQLAlchemyUoW:**
- Purpose: Transaction boundary management
- Interface: `src/common/uow.py` -- defines `__aenter__`, `__aexit__`, `flush()`, `commit()`, `rollback()`
- Implementation: `src/infrastructure/database/uow.py` -- async context manager, handles IntegrityError -> ConflictError conversion
- Domain UoWs compose specific repositories onto a shared session:
  - `CatalogUnitOfWork` (`src/modules/catalog/uow.py`) -- just `products`
  - `InventoryUnitOfWork` (`src/modules/inventory/uow.py`) -- inventories, transfers, transfer_items, transactions, accounts, financial_transactions
  - `BaseOrderUnitOfWork` (`src/modules/orders/uow.py`) -- orders, order_items + all inventory/finance repos
  - `ClientUnitOfWork` (`src/application/client/uow.py`) -- all repos across users, identity, accounts, inventory, orders
  - `UserUnitOfWork` (`src/modules/users/uow.py`) -- users, identities, accounts, inventory repos
  - `CourierUnitOfWork` (`src/application/courier/uow.py`) -- users, identities, accounts, inventories

**AppException Hierarchy:**
- Purpose: Typed business errors that map to HTTP status codes
- Location: `src/core/exceptions.py`
- Pattern: Each exception carries `message`, `status_code`, `error_code`, `details`. Global handler in `src/api/exceptions/handlers.py` converts to standard JSON `{error: {code, message, details}}`
- Subclasses: `NotFoundError` (404), `BadRequestError` (400), `UnauthorizedError` (401), `ForbiddenError` (403), `ConflictError` (409), `UnprocessableEntityError` (422), `ServiceUnavailableError` (503)
- Domain-specific exceptions extend these (e.g., `InsufficientStockError` in `src/modules/inventory/exceptions.py`, `OrderNotFoundError` in `src/modules/orders/exceptions.py`)

**BaseModel (SQLAlchemy Declarative Base):**
- Purpose: Common columns for all database tables
- Location: `src/infrastructure/database/base.py`
- Provides: `id` (UUIDv7), `is_active` (soft-delete flag), `created_at`, `updated_at`
- Auto-generates `__tablename__` from CamelCase class name -> snake_case_plural

## Entry Points

**FastAPI Application:**
- Location: `src/main.py` (imports from `src/api/server.py`)
- Triggers: `uv run fastapi dev src/main.py` or `make dev`
- Responsibilities: Creates FastAPI app, registers middleware (RequestID -> AccessLogger -> CORS), exception handlers, mounts `api_v1_router` at `/api/v1`

**Alembic Migrations:**
- Location: `alembic/env.py`, `alembic/versions/`
- Triggers: `make upgrade` / `make migrate m="name"`
- Responsibilities: Schema evolution. Two migrations: `cefde77d7774_init.py` (tables), `c650cec7ccb0_triggers.py` (PG trigger functions)

**Database Initialization:**
- Location: `src/core/init.py` (`init_data()`)
- Triggers: Called at app startup (via lifespan or seeder)
- Responsibilities: Creates system user, system financial accounts (Revenue, Cash, Card, Discount), virtual inventories (VIRTUAL_VENDOR, VIRTUAL_LOSS), admin user, walk-in user with client inventory

**Database Seeder:**
- Location: `src/core/seeder.py`
- Triggers: `POST /api/v1/backoffice/system/seed` (admin-only)
- Responsibilities: Generates test data (products, warehouses, couriers, clients, orders)

**Health Check:**
- Location: `src/api/server.py` (inline in `create_app()`)
- Endpoint: `GET /health`

## Error Handling

**Strategy:** Layered exception handling with a unified JSON response format

**Patterns:**
- Domain services raise `AppException` subclasses (e.g., `OrderNotFoundError`, `InsufficientStockError`)
- Module-level exceptions defined in each module's `exceptions.py` file
- Global exception handler in `src/api/exceptions/handlers.py` catches:
  1. `AppException` -> business error JSON with appropriate HTTP status
  2. `RequestValidationError` -> 422 with field-level error details
  3. `StarletteHTTPException` -> standard HTTP error in unified format
  4. `Exception` (catch-all) -> 500 with generic message (no stack trace to client)
- UoW `commit()` converts `IntegrityError` -> `ConflictError` (409)
- Response format: `{"error": {"code": "ERROR_CODE", "message": "...", "details": {...}}}`

## Cross-Cutting Concerns

**Logging:**
- Framework: structlog with contextvars
- Configuration: `src/core/logger.py` -- JSON in prod, colored console in dev
- Request correlation: `RequestIDMiddleware` (`src/api/middlewares/request_id.py`) binds `request_id` to structlog context
- Access logging: `AccessLoggerMiddleware` (`src/api/middlewares/logger.py`) logs method, path, status, duration

**Validation:**
- Pydantic v2 schemas for all request/response models
- FastAPI `Body()`, `Query()`, `Path()` with constraints (`gt=0`, `ge=0`, `min_length=1`)
- Business validation in service layer (e.g., tara exchange rules, route validation for transfers)

**Authentication:**
- JWT-based OAuth2 flow
- Token creation: `src/core/security/jwt.py` -- HS256 signed, 7-day expiry
- Two-level auth dependency:
  1. `get_token_payload()` -- JWT-only validation + scope check (no DB hit)
  2. `get_current_user()` -- fetches `User` from DB via `UserService` (heavier)
- Scope-based authorization: `Security(get_current_user, scopes=[Scope.ORDERS_READ])`

**RBAC:**
- 8 roles defined in `src/modules/users/enums.py`: SYSTEM, ADMIN, ACCOUNTANT, STOREKEEPER, CASHIER, COURIER, CLIENT_B2C, CLIENT_B2B
- Permission mapping in `src/core/security/permissions.py`: `ROLE_SCOPES` dict maps each role to its allowed scopes
- Scopes embedded in JWT at login time, checked at request time

**Database Triggers (Critical):**
- `update_account_balances()` -- on `transactions` INSERT/UPDATE: atomically adjusts `accounts.balance` with deadlock-safe row locking
- `update_inventory_balances()` -- on `stock_transactions` INSERT: upserts `inventory_balances.quantity` via conflict resolution
- Both enforce strict append-only ledger (block DELETE and certain UPDATEs)
- Defined in `alembic/versions/c650cec7ccb0_triggers.py`, SQL source in `src/infrastructure/database/scripts/`

---

*Architecture analysis: 2026-03-27*
