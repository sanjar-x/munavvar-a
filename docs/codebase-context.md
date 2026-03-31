# Codebase Context

Updated: 2026-03-31

## TL;DR

- Это backend на FastAPI + PostgreSQL с асинхронным SQLAlchemy, построенный как modular monolith с элементами Clean Architecture.
- Основная бизнес-логика живет в `src/modules/*`.
- `src/application/*` не является изолированным application layer в строгом смысле. Это orchestration-слой для составных сценариев поверх нескольких модулей.
- Ключевые домены: пользователи/аутентификация, каталог, заказы, складские перемещения, финансы.
- Остатки товаров и балансы счетов считаются триггерами БД на основе append-only ledger таблиц, а не вручную в Python.

## Stack

- Python `>=3.14`
- Package manager: `uv`
- Web: `FastAPI`
- ORM: `SQLAlchemy 2.x` async
- Migrations: `Alembic`
- Validation: `Pydantic v2`
- Logging: `structlog`
- Tests: `pytest`, `pytest-asyncio`, `httpx`

## Entry Points And Startup

- Точка входа приложения: `src/main.py`
- `src/main.py` импортирует `src/infrastructure/database/models.py`, чтобы зарегистрировать все SQLAlchemy-модели до старта приложения.
- Приложение создается через `src/api/server.py:create_app()`.
- `create_app()`:
  - настраивает логирование через `src/core/logger.py`
  - создает `FastAPI` с `lifespan`
  - отключает OpenAPI и docs в `prod`
  - подключает middleware и exception handlers
  - монтирует `api_v1_router` под `/api/v1`
  - добавляет `/health`
- `lifespan` сейчас только логирует запуск/остановку. Реальная инициализация/очистка ресурсов там почти не реализована.

## Repository Map

- `src/api`
  HTTP-роуты, middleware, exception handlers, композиция API.
- `src/application`
  Составные use-case сервисы и cross-domain UoW.
- `src/common`
  Базовые абстракции `BaseRepository`, `BaseService`, `IUnitOfWork`.
- `src/core`
  Конфиг, security, базовые исключения, системная инициализация, seeding.
- `src/infrastructure`
  SQLAlchemy base, session factory, UoW implementation, агрегирующий импорт моделей, SQL scripts для триггеров.
- `src/modules`
  Доменные вертикали: `auth`, `catalog`, `finances`, `inventory`, `orders`, `users`.
- `tests`
  Unit + integration tests.
- `deploy`
  Docker и compose-конфигурация.
- `docs/superpowers`
  Архитектурные планы/спеки по отдельным фичам.

## Layering

### 1. API layer

- Корневой v1 router: `src/api/v1/__init__.py`
- Основные зоны:
  - `/auth`
  - `/backoffice`
  - `/client`
  - `/courier`
- Роутеры тонкие: получают сервисы через `Depends(...)` и `Security(...)`.

### 2. Domain/modules layer

- `src/modules/*` содержит:
  - модели
  - схемы
  - репозитории
  - UoW
  - сервисы
  - зависимости DI
- Здесь находится основная бизнес-логика.

### 3. Application/orchestration layer

- `src/application/client/service.py`
  CRM/onboarding сценарии клиента.
- `src/application/courier/service.py`
  Регистрация курьера и создание его инвентаря.
- `src/application/inventories/service.py`
  Сейчас фактически не используется, сервис закомментирован.
- `src/application/order/uow.py`
  Есть составной UoW, но нет полноценного сервиса.

Итог: архитектура больше похожа на modular monolith с orchestration-слоем, чем на строгое разделение application/domain/infrastructure.

## Config And Security

- Конфиг: `src/core/config.py`
  - использует `BaseSettings`
  - читает `.env`
  - собирает `database_url` из PG-переменных
  - содержит JWT, CORS, Redis, admin bootstrap и system user settings
- JWT: `src/core/security/jwt.py`
  - токен содержит `exp`, `iat`, `jti`
- Пароли: `src/core/security/password.py`
  - `pwdlib` + bcrypt
- Scopes/permissions: `src/core/security/permissions.py`
  - роли мапятся в список scopes
- Auth DI: `src/modules/auth/dependencies.py`
  - Bearer token -> decode -> validate scopes -> load current user

## Request Pipeline

- Middleware:
  - `RequestIDMiddleware`
    - очищает `structlog` contextvars
    - поднимает или генерирует `X-Request-ID`
  - `AccessLoggerMiddleware`
    - добавляет request metadata
    - измеряет duration
    - записывает access log
- Глобальные ошибки: `src/api/exceptions/handlers.py`
  - `AppException` -> стандартизированный JSON
  - `RequestValidationError` -> кастомный 422
  - `HTTPException` -> унифицированный ответ
  - `Exception` -> 500 + логирование

## Core Domain Model

- `User`
  общий реестр всех пользователей и сотрудников.
- `Identity`
  login/provider binding.
- `Account`
  финансовые счета: revenue, cash, card, bank, client, courier.
- `Inventory`
  физические и виртуальные точки хранения.
- `Product`
  товар, оборудование, тара. Для воды может быть `returnable_item_id`.
- `Order`, `OrderItem`
  клиентский заказ.
- `StockTransfer`, `StockTransferItem`, `StockTransaction`
  перемещение товаров и товарный ledger.
- `Transaction`
  финансовый ledger.

## Major Business Flows

### Auth and users

- `src/modules/auth/services.py`
  - `local_login()`: обычный login по телефону и паролю
  - `client_login()`: выдает токен только по телефону, без проверки пароля
- `src/modules/users/services.py`
  - регистрация и чтение пользователей

### Catalog

- `src/modules/catalog/*`
  - товары, цены, признаки возвратной тары
- `src/modules/catalog/public.py`
  - публичный API каталога для других модулей

### Orders

- Главный сервис: `src/modules/orders/services.py`
- Поддерживает:
  - создание заказа с фиксацией snapshot-цены
  - проверку нехватки тары
  - автокапитализацию дефицита тары
  - изменение состава нового заказа
  - назначение курьера
  - delivery flow
  - warehouse pickup flow
  - partial delivery через `actual_items`

#### Delivery flow

- Жизненный цикл: `NEW -> ASSIGNED -> ... -> DELIVERED`
- При доставке создаются:
  - `CLIENT_DELIVERY` transfer: курьер -> клиент
  - `CLIENT_RETURN` transfer: клиент -> курьер для возвратной тары
- Финансовое закрытие:
  - `Revenue -> Client`
  - далее `Client -> Courier` для `CASH`
  - либо `Client -> Card` со статусом `PENDING` для `CARD`

#### Warehouse pickup flow

- Создание заказа на самовывоз: `create_warehouse_sale()`
- Завершение: `complete_pickup()`
- При завершении создаются:
  - `WAREHOUSE_SALE`: склад -> клиент
  - `WAREHOUSE_TARA_RETURN`: клиент -> склад
- Для walk-in клиента используется `WALKIN_USER_ID`
- После анонимной продажи выполняется cleanup:
  - `LOSS_WRITE_OFF` для обнуления walk-in inventory
- Финансовое закрытие:
  - `Revenue -> Client`
  - `Client -> Cash`

### Inventory / logistics

- Главный сервис: `src/modules/inventory/services.py`
- Основные сервисы:
  - `TransportService`
  - `WarehouseService`
  - `StockTransferService`
  - `CapitalizeTaraService`
- `StockTransferService.create_transfer()` реализует single-step transfers:
  - автоматически подставляет виртуальные склады там, где нужно
  - валидирует маршрут по `_VALID_ROUTES`
  - блокирует исходный inventory
  - проверяет остатки
  - создает transfer и ledger записи
- Больше нет полноценного draft workflow на уровне сервиса, несмотря на то, что enum `TransferStatus` все еще содержит `DRAFT`.

### Client and courier orchestration

- `src/application/client/service.py`
  - создание клиента
  - создание client inventory
  - расширенный onboarding: клиент + счет + inventory + initial balance + optional first order
- `src/application/courier/service.py`
  - создание курьера
  - identity
  - courier account
  - courier inventory

## Persistence And Invariants

### Session/UoW

- Session factory: `src/infrastructure/database/session.py`
- Base UoW: `src/infrastructure/database/uow.py`
- Репозитории получают `AsyncSession`, а сервисы обычно работают через `async with self.uow`.

### Important DB rule

Истинный источник агрегированных остатков и балансов не поля Python-сервисов, а ledger + SQL-триггеры.

### Financial ledger

- Таблица `transactions` append-only по смыслу.
- Триггер `update_account_balances()`:
  - обновляет `accounts.balance`
  - запрещает destructive mutations вроде delete
  - поддерживает изменение эффекта при смене статуса `pending/completed`

### Inventory ledger

- Таблица `stock_transactions` append-only.
- Триггер `update_inventory_balances()`:
  - обновляет `inventory_balances`
  - запрещает update/delete истории

### Consequence for future work

- Нельзя безопасно менять `accounts.balance` или `inventory_balances` вручную как primary source.
- Любые новые складские/финансовые сценарии должны, как правило, создавать ledger записи, а не напрямую редактировать агрегаты.

## Database Initialization And Seeding

- `src/core/init.py`
  - создает system user
  - создает системные accounts
  - создает виртуальные inventories
  - создает walk-in пользователя, inventory и account
  - опционально создает стартового админа из env
- `src/core/seeder.py`
  - создает mock products
  - создает mock warehouse
  - создает mock couriers/clients
  - создает начальные перемещения и mock orders
- Endpoint для seeding:
  - `POST /api/v1/backoffice/system/seed`

## Tests

- Unit tests:
  - `tests/unit/test_catalog_dto.py`
  - `tests/unit/test_catalog_public.py`
- Integration tests покрывают характеризационные бизнес-флоу:
  - delivery fulfillment
  - courier shift close
  - warehouse pickup
  - walk-in sale
- Тесты используют:
  - отдельный engine на тест
  - внешнюю транзакцию с rollback
  - monkeypatch `async_session_maker` в известных dependency modules

### Important test nuance

- Интеграционные тесты ожидают существующую схему БД и часть системных сущностей.
- Фикстуры берут `system_user`, virtual inventories, system accounts и walk-in user из уже инициализированной БД.
- Если добавится новый модуль, который напрямую импортирует `async_session_maker`, его нужно добавить в `_SESSION_FACTORY_MODULES` в `tests/conftest.py`, иначе тесты могут использовать не ту session factory.
- В текущем локальном окружении `pytest` не стартует уже на импорте `settings`: отсутствуют обязательные env-переменные (`SECRET_KEY`, `PG*`, `REDIS*` и т.д.), а `DEBUG=release` не парсится как boolean.

## Deploy And Runtime Ops

- Dockerfile: `deploy/docker/Dockerfile`
- Compose dev:
  - `deploy/compose.db.yml` поднимает PostgreSQL
  - `deploy/compose.dev.yml` поднимает FastAPI и прогоняет `alembic upgrade head`
- Railway:
  - `railway.toml`
  - `deploy/docker/Dockerfile.railway`
- Локальный старт из README:
  - `uv run fastapi dev src/main.py`
- Несостыковка в документации:
  - `README.md` заявляет PostgreSQL 16
  - `deploy/compose.db.yml` использует `postgres:18-alpine`
- Стандартный entrypoint запускает миграции и сервер, но не вызывает `src/core/init.py:init_data()`, поэтому системные сущности нужно инициализировать отдельно.

## API Surface Snapshot

- `/api/v1/auth`
  - login/register
- `/api/v1/backoffice`
  - profile
  - users
  - clients
  - couriers
  - catalog
  - transports
  - warehouses
  - transfers
  - orders
  - shifts
  - system
- `/api/v1/client`
  - login
  - profile
  - catalog
  - orders
  - inventory
- `/api/v1/courier`
  - profile
  - catalog
  - orders

## Notable Oddities And Refactor Hotspots

- `src/application/inventories/service.py` закомментирован и выглядит как незавершенная ветка рефакторинга.
- `src/application/order/uow.py` существует без соответствующего полноценного сервиса.
- Граница между `application` и `modules` размыта.
- `src/api/v1/backoffice/__init__.py` подключает `system_router` дважды.
- `src/modules/auth/services.py:client_login()` выдает токен по одному телефону без проверки пароля. Это нужно считать осознанной особенностью или security debt.
- `src/api/server.py` содержит декларативный `lifespan`, но реального cleanup DB pool там нет, хотя `close_db_connection()` существует отдельно.
- В `src/application/courier/service.py` сервис напрямую использует `uow.session.flush()`, что немного протекает через слой абстракции.
- Enum/status model местами содержит следы прошлой модели работы, например `DRAFT` в transfer status при текущем single-step execution.

## Useful Files To Reopen First In Future Tasks

- `src/api/server.py`
- `src/core/config.py`
- `src/core/init.py`
- `src/infrastructure/database/session.py`
- `src/infrastructure/database/uow.py`
- `src/modules/orders/services.py`
- `src/modules/inventory/services.py`
- `src/application/client/service.py`
- `tests/conftest.py`
- `tests/integration/conftest.py`

## Recommended Reading Order For New Work

1. `README.md`
2. `src/api/server.py`
3. `src/core/config.py`
4. `src/core/init.py`
5. `src/modules/orders/services.py`
6. `src/modules/inventory/services.py`
7. `src/application/client/service.py`
8. relevant router in `src/api/v1/*`
9. relevant integration test in `tests/integration/*`
