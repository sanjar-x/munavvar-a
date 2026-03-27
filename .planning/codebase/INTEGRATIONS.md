# External Integrations

**Analysis Date:** 2026-03-27

## APIs & External Services

This application is largely self-contained with minimal external service dependencies. The backend is a monolithic REST API that the React frontend consumes directly. No third-party APIs (payment gateways, SMS providers, maps, etc.) are currently integrated.

**Internal REST API (Backend -> Frontend):**
- Base URL pattern: `{host}/api/v1/`
- Versioned routing: `src/api/v1/__init__.py`
- Route groups:
  - `/api/v1/auth/` - Authentication (login, register) via `src/api/v1/auth/`
  - `/api/v1/backoffice/` - Admin panel endpoints via `src/api/v1/backoffice/`
  - `/api/v1/courier/` - Courier-facing endpoints via `src/api/v1/courier/`
  - `/api/v1/client/` - Client-facing endpoints via `src/api/v1/client/`
  - `/health` - Health check (root level, in `src/api/server.py`)
- Frontend consumes via RTK Query: `frontend/src/services/baseApi.js`
  - API services: `authApi.js`, `catalogApi.js`, `clientsApi.js`, `couriersApi.js`, `financesApi.js`, `ordersApi.js`, `profileApi.js`, `shiftsApi.js`, `transfersApi.js`, `transportsApi.js`, `usersApi.js`, `warehousesApi.js`, `analyticsApi.js`

## Data Storage

**Primary Database: PostgreSQL 18**
- Driver: `asyncpg` (async, no ORM bypass)
- ORM: SQLAlchemy 2.1 (async mode)
- Connection config: `src/core/config.py` (Settings class, computed `database_url` property)
- Session management: `src/infrastructure/database/session.py`
  - Connection pool: `pool_size=15`, `max_overflow=10`, `pool_timeout=30`, `pool_pre_ping=True`
  - Session factory: `async_session_maker` with `expire_on_commit=False`
- Dependency injection: `get_session()` generator in `src/infrastructure/database/session.py`
- Connection env vars: `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`
- URL format: `postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}`
- Dev setup: `deploy/compose.db.yml` (postgres:18-alpine, tuned with shared_buffers=256MB, work_mem=16MB)

**Database Triggers (PL/pgSQL):**
- `src/infrastructure/database/scripts/update_inventory_balances.sql` - Materializes `inventory_balances` table on `stock_transactions` INSERT; blocks UPDATE/DELETE
- `src/infrastructure/database/scripts/update_account_balances.sql` - Updates `accounts.balance` on `transactions` INSERT/UPDATE; blocks DELETE and amount changes
- Applied via Alembic migration: `alembic/versions/c650cec7ccb0_triggers.py`

**Database Schema (12 tables):**
- `users` - User profiles with role-based access (`src/modules/users/models.py`)
- `identities` - Multi-provider auth credentials (`src/modules/users/models.py`)
- `products` - Product catalog with JSONB attributes (`src/modules/catalog/models.py`)
- `orders`, `order_items` - Order lifecycle (`src/modules/orders/models.py`)
- `inventories` - Storage locations (warehouses, courier vehicles, clients) (`src/modules/inventory/models.py`)
- `stock_transfers`, `stock_transfer_items` - Transfer documents (`src/modules/inventory/models.py`)
- `stock_transactions` - Immutable inventory ledger (`src/modules/inventory/models.py`)
- `inventory_balances` - Materialized balance cache (trigger-maintained) (`src/modules/inventory/models.py`)
- `accounts` - Financial accounts per user/system (`src/modules/finances/models.py`)
- `transactions` - Financial ledger (append-only) (`src/modules/finances/models.py`)

**Redis (Configured but not yet used):**
- Env vars defined in `src/core/config.py`: `REDISHOST`, `REDISPORT`, `REDISUSER`, `REDISPASSWORD`
- No Redis client library in `pyproject.toml` dependencies
- `src/infrastructure/cache/` directory exists but is empty
- `src/infrastructure/clients/` directory exists but is empty
- Status: Placeholder for future caching/session storage

**File Storage:**
- None. No file upload or cloud storage integration detected.

**Caching:**
- None active. Redis is configured at the settings level only.

## Authentication & Identity

**Auth Provider: Custom JWT (self-hosted)**
- Implementation: `src/core/security/jwt.py` (create/decode JWT tokens using PyJWT)
- Algorithm: HS256 with `SECRET_KEY` from environment
- Token payload: `sub` (user UUID), `scopes` (permission list), `exp`, `iat`, `jti`
- Token TTL: `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 10080 min = 7 days)
- OAuth2 scheme: `OAuth2PasswordBearer` in `src/modules/auth/dependencies.py`
- Two-level auth:
  - **Fast path** (`get_token_payload`): JWT validation + scope check only, no DB query
  - **Slow path** (`get_current_user`): Loads full `User` from DB via `UserService`

**Password Hashing:**
- Library: `pwdlib` with Bcrypt hasher (`src/core/security/password.py`)
- Functions: `get_password_hash()`, `verify_password()`

**Multi-Provider Identity Model:**
- `Identity` model supports: `LOCAL`, `GOOGLE`, `TELEGRAM`, `APPLE` (`src/modules/users/enums.py`)
- Currently only `LOCAL` (phone + password) is implemented
- One user can have multiple identities (one-to-many)

**RBAC (Role-Based Access Control):**
- 8 roles defined in `src/modules/users/enums.py`: SYSTEM, ADMIN, ACCOUNTANT, STOREKEEPER, CASHIER, COURIER, CLIENT_B2C, CLIENT_B2B
- Scope-based permissions mapped per role in `src/core/security/permissions.py`
- Scopes embedded in JWT token at login time
- FastAPI `SecurityScopes` used for endpoint-level authorization

## Monitoring & Observability

**Structured Logging:**
- Framework: `structlog` >=25.5.0 (`src/core/logger.py`)
- Dev mode: `ConsoleRenderer(colors=True)` (human-readable)
- Prod mode: `JSONRenderer()` (machine-parseable)
- Context propagation: `structlog.contextvars` for request-scoped data
- Request ID: Generated per-request via `RequestIDMiddleware` (`src/api/middlewares/request_id.py`), propagated in `X-Request-ID` header
- Access logging: `AccessLoggerMiddleware` (`src/api/middlewares/logger.py`) logs method, path, status, duration for every HTTP request
- Response headers: `X-Request-ID` and `X-Process-Time` added to all responses

**Error Tracking:**
- No external error tracking service (no Sentry, Datadog, etc.)
- All errors caught by centralized exception handlers in `src/api/exceptions/handlers.py`
- Standardized JSON error format: `{"error": {"code": "...", "message": "...", "details": {...}}}`
- Exception hierarchy: `AppException` base with `NotFoundError`, `BadRequestError`, `UnauthorizedError`, `ForbiddenError`, `ConflictError`, `UnprocessableEntityError`, `ServiceUnavailableError` (`src/core/exceptions.py`)

**Health Check:**
- `GET /health` returns `{"status": "ok", "environment": "dev|test|prod"}` (`src/api/server.py`)

## CI/CD & Deployment

**Backend Hosting: Railway**
- Config: `railway.toml` (builder = "DOCKERFILE", path = `deploy/docker/Dockerfile.railway`)
- Docker image: `python:3.14-slim-trixie` with `uv` for dependency management
- Entrypoint: `scripts/entrypoint.sh` (runs `alembic upgrade head` then `fastapi run`)
- Production URL: `https://backend-production-91c56.up.railway.app` (referenced in frontend config)

**Frontend Hosting: Vercel**
- Config: `frontend/vercel.json` (SPA rewrite rule)
- Build: `vite build` (outputs to `dist/`)

**CI Pipeline:**
- No CI configuration files detected (no `.github/workflows/`, no `Jenkinsfile`, no `.gitlab-ci.yml`)
- Code quality enforced locally via pre-commit hooks (Ruff lint + format, trailing whitespace, YAML validation, secret detection)

**Docker Compose (Development):**
- `deploy/compose.db.yml` - PostgreSQL 18 only (database for local dev)
- `deploy/compose.dev.yml` - FastAPI app container (mounts source code, runs migrations + dev server)
- Shared Docker network named `network`

## Environment Configuration

**Required env vars (backend `.env`):**
- `SECRET_KEY` - JWT signing secret
- `PGHOST` - PostgreSQL host
- `PGPORT` - PostgreSQL port
- `PGUSER` - PostgreSQL username
- `PGPASSWORD` - PostgreSQL password
- `PGDATABASE` - PostgreSQL database name
- `REDISHOST` - Redis host (required by Settings validation but unused)
- `REDISPORT` - Redis port
- `REDISUSER` - Redis username
- `REDISPASSWORD` - Redis password

**Optional env vars (backend):**
- `ENVIRONMENT` - Runtime environment ("dev", "test", "prod")
- `DEBUG` - Enable debug mode
- `ACCESS_TOKEN_EXPIRE_MINUTES` - JWT token expiry
- `CORS_ORIGINS` - Comma-separated CORS origins
- `ADMIN_PHONE` - Phone number for initial admin user
- `ADMIN_PASSWORD` - Password for initial admin user

**Required env vars (frontend `.env.local`):**
- `VITE_API_BASE_URL` - Backend API URL
- `VITE_USE_PROXY` - Enable Vite dev proxy ("true"/"false")

**Secrets location:**
- Backend: `.env` file at project root (gitignored)
- Frontend: `frontend/.env.local` (gitignored)
- Example: `.env.example` committed with placeholder values
- Production: Environment variables provided by Railway/Vercel platform

## Webhooks & Callbacks

**Incoming:**
- None detected. No webhook receiver endpoints.

**Outgoing:**
- None detected. No webhook dispatch or event publishing.

## Data Initialization

**System Bootstrap (`src/core/init.py`):**
- Creates SYSTEM user (UUID zero)
- Creates system financial accounts (REVENUE, CASH, CARD, BANK)
- Creates virtual inventories (VIRTUAL_VENDOR, VIRTUAL_LOSS)
- Creates WALK-IN user for anonymous warehouse sales
- Creates initial ADMIN user from `ADMIN_PHONE` / `ADMIN_PASSWORD` env vars

**Development Seeder (`src/core/seeder.py`):**
- Creates mock products (water, containers, equipment)
- Creates mock warehouses, couriers, clients
- Creates initial stock movements and sample orders
- Run via: `python -m src.core.seeder`

## Future Integration Points

Based on configured but unused infrastructure:
- **Redis** (`src/infrastructure/cache/` empty, env vars defined) - Likely planned for caching or session storage
- **External auth providers** (`AuthProvider` enum includes GOOGLE, TELEGRAM, APPLE) - Only LOCAL is implemented
- **External services** (`src/infrastructure/external/` empty, `src/infrastructure/clients/` empty) - Directories exist as scaffolding
- **Background workers** (`src/workers/` empty) - Planned for async task processing

---

*Integration audit: 2026-03-27*
