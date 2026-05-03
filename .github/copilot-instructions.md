# Copilot Instructions — HOD (Home & Office Delivery)

B2B/B2C water delivery platform built as a DDD modular monolith. Python 3.14+ / FastAPI / SQLAlchemy 2.x (async) / PostgreSQL.

## Commands

```bash
uv sync                          # Install/sync dependencies
make dev                         # Dev server (hot reload)
make test                        # Run all tests
uv run pytest tests/unit/ -v     # Unit tests only
uv run pytest tests/unit/test_orders.py -v          # Single test file
uv run pytest tests/unit/test_orders.py::test_name  # Single test
make lint                        # Lint (no fix)
make format                      # Lint + format (auto-fix)
make upgrade                     # Apply Alembic migrations
make migrate m="description"     # Generate new migration
```

## Architecture

Four layers with strict dependency direction: **API → Application → Modules → Common/Infrastructure**.

- **`src/api/`** — FastAPI routers grouped by audience: `backoffice/`, `client/`, `courier/`, `auth/`. Handles HTTP, auth enforcement, response serialization. Never contains business logic.
- **`src/application/`** — Cross-domain orchestration (client onboarding, order creation with tara auto-provisioning). Composes repositories from multiple modules via composite UoWs.
- **`src/modules/`** — **Seven** bounded contexts: `auth`, `users`, `catalog`, `orders`, `inventory`, `finances`, **`contracts`**. Each owns its `models.py`, `repositories.py`, `services.py`, `schemas.py`, `uow.py`, `dependencies.py`, `exceptions.py`, `enums.py`. `contracts/` covers B2B: договоры, прайс-листы с per-product-quantity квотами, инвойсы, акты сверки, журнал статусов, доп. соглашения — самый активный модуль.
- **`src/common/`** — `BaseRepository[ModelType]`, `BaseService[Model, Schema, UoW]`, `IUnitOfWork` interface.
- **`src/infrastructure/database/`** — `BaseModel` (UUIDv7 PK, `is_active`, timestamps), `BaseSQLAlchemyUoW`, engine/session factory.
- **`src/core/`** — Config, JWT, password hashing, RBAC permissions, structured logging, exception hierarchy, system constants.

### Ledger integrity is paramount

Both the **Stock Ledger** (`stock_transactions`) and **Financial Ledger** (`transactions`) are append-only. PostgreSQL triggers enforce balance materialization and block DELETE/UPDATE on ledger tables. Application code cannot bypass this — do not attempt to modify or delete ledger entries.

⛔ **Sacred rules — нарушение = автоматический 🔴 Critical в Code Review:**

- **НИКОГДА** не пиши `session.execute(update(StockTransaction)...)`, `session.execute(delete(Transaction)...)`, `session.delete(tx)` — упадёт на триггере и/или нарушит инвариант двойной записи.
- **НИКОГДА** не «исправляй» неверную проводку правкой существующей записи.
- **Коррекция = новая компенсирующая запись** (reversal/adjustment), которая ссылается на исходную через `parent_id` или метаданные.
- Балансы (`accounts.balance`, `inventory_balances.quantity`) — это материализованный кеш, обновляемый триггерами. Не пытайся его править руками.
- Если триггер упал на INSERT — значит, бизнес-инвариант нарушен. Понять почему, не глушить try/except.

### 🚧 Active Feature: Soft Quota Limits (untracked)

Идёт фича мягких квот по B2B-договорам. Untracked миграция `alembic/versions/d4e5f6a7b8c9_soft_quota_limits.py` снимает CHECK на `quantity_used <= quantity_limit` и добавляет `Order.quota_exceeded`. 15 modified-файлов в working tree (`src/modules/{contracts,orders,inventory}/...`, `src/api/v1/{backoffice,courier}/...`, `src/core/init.py`) относятся к этой фиче.

**Правило:** не предлагай рефакторингов / переименований / extract-хелперов в перечисленных файлах, пока коммит не закрыт. Допустимы только точечные правки в рамках самой фичи.

### 📝 API Changelog

Authoritative file: `/CHANGELOG.md` (root). Frontend submodule синхронизируется через symlink `frontend/CHANGELOG.md → ../CHANGELOG.md`. Любое API-breaking/extending изменение фиксируется в `/CHANGELOG.md` в том же коммите. Pre-commit hook (`scripts/check-changelog-sync.sh`) падает, если меняется `src/api/v1/**` или `src/modules/*/schemas.py` без правки CHANGELOG.

### 🧩 Frontend as git submodule

`frontend/` is both a git submodule of this monorepo and a standalone GitHub repo (`Yokubjanovichh/MunnavarA`, branches `main` + `dev`) deployed on Vercel. Backend repo pins the frontend SHA via `.gitmodules`. Commands inside `frontend/` operate on the frontend repo; commands at backend root only update the pin via `git submodule update --remote frontend`. Clone with `git clone --recurse-submodules` or run `git submodule update --init` post-clone.

## Key Patterns

### Unit of Work

Every domain defines an interface (`IXxxUnitOfWork`) and implementation (`XxxUnitOfWork`). The implementation extends `BaseSQLAlchemyUoW` and composes repositories in `__aenter__`:

```python
class UserUnitOfWork(BaseSQLAlchemyUoW, IUserUnitOfWork):
    async def __aenter__(self) -> "UserUnitOfWork":
        await super().__aenter__()
        self.users = UserRepository(session=self.session)
        self.identities = IdentityRepository(session=self.session)
        return self
```

### Dependency Injection

FastAPI `Depends` chain: `get_{entity}_uow()` → `get_{entity}_service(uow)` → route handler.

### Repository / Service Generics

Uses PEP 695 syntax: `class BaseRepository[ModelType: BaseModel]`, `class BaseService[ModelType, CreateSchemaType, UoWType, DTOType]`.

### Error Handling

Raise domain-specific exceptions from `src/core/exceptions.py` hierarchy (`NotFoundError`, `BadRequestError`, `ConflictError`, etc.) — never `HTTPException`. Error messages are in Russian. The global handler converts to `{"error": {"code": "ERROR_CODE", "message": "...", "details": {...}}}`.

`IntegrityError` is caught by `BaseSQLAlchemyUoW.commit()` and re-raised as `ConflictError`.

### Auth

JWT with embedded scopes. Roles map to scopes via `ROLE_SCOPES` dict in `src/core/security/permissions.py`. Routes enforce with `Security(get_current_user, scopes=[Scope.ORDERS_READ])`.

## Conventions

- **Line length**: 79 characters (Ruff enforced)
- **Imports**: Always absolute from `src.` root — never relative
- **Async**: All DB operations use `async def` — no sync DB calls
- **IDs**: `uuid.UUID` everywhere, generated with `uuid.uuid7()` (UUIDv7)
- **Enums**: Always `enum.StrEnum`
- **Relationships**: `lazy="raise"` on bulk-risk relationships to prevent N+1
- **Foreign keys**: `ondelete="RESTRICT"` on critical FKs — no silent cascades
- **Schema conversion**: `schema.model_dump(exclude_unset=True)` for partial updates
- **Service returns**: Domain model objects to API layer; serialization happens at router level
- **Soft deletes**: `is_active=False` via `archive()`, not hard deletes
- **Type annotations**: Required on all function signatures
- **`TYPE_CHECKING` guard**: Used in models to prevent circular imports

## Testing

Tests use a rollback-per-test strategy: each test gets a connection with an outer transaction that rolls back after the test. The `client` fixture monkeypatches `async_session_maker` across all dependency modules to use the test session factory. Auth headers are created via `make_auth_headers(user_id, role)` helper in `conftest.py`.
