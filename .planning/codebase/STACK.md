# Technology Stack

**Analysis Date:** 2026-03-27

## Languages

**Primary:**
- Python 3.14 - Backend API, business logic, database models, migrations (`src/`, `alembic/`, `scripts/`)
- JavaScript (ES2020+, JSX) - Frontend admin SPA (`frontend/src/`)

**Secondary:**
- SQL (PL/pgSQL) - Database triggers for balance materialization (`src/infrastructure/database/scripts/*.sql`)
- Shell (POSIX sh) - Entrypoint and deployment scripts (`scripts/entrypoint.sh`)

## Runtime

**Backend:**
- CPython 3.14 (requires-python = ">=3.14")
- Base Docker image: `python:3.14-slim-trixie` (`deploy/docker/Dockerfile.railway`)
- ASGI server: Uvicorn (bundled with FastAPI via `fastapi[standard]`)

**Frontend:**
- Node.js (version not pinned; no `.nvmrc` or `.node-version` present)
- Browser target: ES2020+ (configured in `frontend/eslint.config.js`)

**Package Managers:**
- `uv` (Astral) - Python dependency management and task runner
  - Lockfile: `uv.lock` (present, committed)
  - Installed via Docker: `COPY --from=ghcr.io/astral-sh/uv:latest`
- `npm` - Frontend dependency management
  - Lockfile: `frontend/package-lock.json` (present)

## Frameworks

**Core:**
- FastAPI >=0.132.0 - Async REST API framework (`src/api/server.py`)
- SQLAlchemy >=2.1.0b1 (async mode) - ORM with asyncpg driver (`src/infrastructure/database/session.py`)
- Pydantic v2 (via pydantic-settings) - Schema validation and settings management (`src/core/config.py`)
- React 19.2.0 - Frontend UI library (`frontend/package.json`)
- Redux Toolkit 2.11.2 + RTK Query - Frontend state management and API layer (`frontend/src/app/store.js`, `frontend/src/services/baseApi.js`)

**Build/Dev:**
- Vite 7.3.1 - Frontend build tool (`frontend/vite.config.js`)
- Ruff >=0.15.1 - Python linter and formatter (`pyproject.toml` [tool.ruff])
- ESLint 9.39.1 - JavaScript linter (`frontend/eslint.config.js`)
- pre-commit - Git hooks for code quality (`.pre-commit-config.yaml`)

**Testing:**
- pytest >=9.0.2 - Test runner (`pyproject.toml` [tool.pytest.ini_options])
- pytest-asyncio >=1.3.0 - Async test support (asyncio_mode = "auto")
- pytest-cov >=7.0.0 - Coverage reporting
- pytest-archon >=0.0.7 - Architecture/dependency rule enforcement
- httpx >=0.28.1 - Async HTTP test client for FastAPI
- polyfactory >=3.3.0 - Test data factory generation
- Locust >=2.43.3 - Load testing

**Type Checking:**
- ty >=0.0.17 - Astral's Python type checker (dev dependency)

## Key Dependencies

**Critical (production):**
- `fastapi[standard]` >=0.132.0 - API framework (includes uvicorn, httptools, python-multipart)
- `sqlalchemy[asyncio]` >=2.1.0b1 - ORM with async extension
- `asyncpg` >=0.31.0 - PostgreSQL async driver
- `pyjwt` >=2.11.0 - JWT token encoding/decoding (`src/core/security/jwt.py`)
- `pwdlib[argon2,bcrypt]` >=0.3.0 - Password hashing with Bcrypt (`src/core/security/password.py`)
- `alembic` >=1.18.4 - Database schema migrations (`alembic/`)
- `structlog` >=25.5.0 - Structured logging framework (`src/core/logger.py`)
- `structlog-config` >=0.11.0 - Structlog configuration helpers

**Infrastructure:**
- `pydantic-settings` - Environment variable loading and validation (`src/core/config.py`)
- `react-router-dom` ^7.13.0 - Frontend client-side routing (`frontend/package.json`)

## Configuration

**Environment Variables (backend):**
Settings are loaded from `.env` via `pydantic-settings` in `src/core/config.py`. All settings are defined in the `Settings` class.

Required variables (see `.env.example`):
- `SECRET_KEY` - JWT signing key (SecretStr)
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` - PostgreSQL connection
- `REDISHOST`, `REDISPORT`, `REDISUSER`, `REDISPASSWORD` - Redis connection (configured but not yet used in application code)

Optional variables:
- `ENVIRONMENT` - "dev" | "test" | "prod" (default: "dev")
- `DEBUG` - Enables SQL echo and console log renderer (default: False)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - JWT TTL (default: 10080 = 7 days)
- `CORS_ORIGINS` - Comma-separated allowed origins
- `ADMIN_PHONE`, `ADMIN_PASSWORD` - Initial admin seeding credentials

**Environment Variables (frontend):**
Loaded via Vite's `loadEnv` in `frontend/vite.config.js`:
- `VITE_API_BASE_URL` - Backend API base URL
- `VITE_USE_PROXY` - Enable dev proxy ("true"/"false")
- `VITE_PROXY_TARGET` - Proxy target for dev mode
- `VITE_MOCK_SALES_ANALYTICS` - Enable mock analytics data

**Build Configuration Files:**
- `pyproject.toml` - Python project config, Ruff config, pytest config
- `alembic.ini` - Alembic migration config
- `frontend/vite.config.js` - Vite build config with `@` alias to `./src`
- `frontend/eslint.config.js` - ESLint flat config
- `frontend/vercel.json` - Vercel SPA rewrites
- `.pre-commit-config.yaml` - pre-commit hooks (ruff, trailing whitespace, YAML check, large file check, secret detection)

**Ruff Configuration (`pyproject.toml`):**
- Line length: 79
- Auto-fix enabled
- Rule sets: E, W, F, I, B, C4, UP, SIM
- Ignored: UP037

## Platform Requirements

**Development:**
- Python >=3.14 (latest; uses new generic syntax `class Foo[T: Base]`)
- Docker + Docker Compose (for local PostgreSQL via `deploy/compose.db.yml`)
- `uv` package manager (replaces pip/poetry)
- Node.js + npm (for frontend)
- Make (optional, for `Makefile` shortcuts)

**Development Commands (via Makefile):**
```bash
make up        # Start local PostgreSQL (Docker)
make down      # Stop containers
make dev       # Run FastAPI dev server (uv run fastapi dev src/main.py)
make sync      # Install/sync Python dependencies
make migrate m="name"  # Create Alembic migration
make upgrade   # Apply migrations
make downgrade # Rollback last migration
make format    # Run Ruff formatter + linter fix
make lint      # Run Ruff linter (check only)
make test      # Run pytest
```

**Production:**
- Backend: Railway (Dockerfile-based deployment via `railway.toml` pointing to `deploy/docker/Dockerfile.railway`)
- Frontend: Vercel (SPA with `vercel.json` rewrites)
- Database: PostgreSQL 18 (Alpine image in dev; Railway-hosted in prod)
- Entrypoint runs migrations before starting: `scripts/entrypoint.sh`

---

*Stack analysis: 2026-03-27*
