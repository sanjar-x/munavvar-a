# Infrastructure & Database - Полная документация

## 1. Database Session Setup

**Файл:** `src/infrastructure/database/session.py`

- **Driver**: PostgreSQL + asyncpg
- **Pool**: pool_size=15, max_overflow=10, pool_timeout=30s, pool_pre_ping=True
- **Session**: expire_on_commit=False, autoflush=False, autocommit=False

Экспортирует:
- `engine` — глобальный `AsyncEngine`, создаётся один раз при старте
- `async_session_maker` — фабрика сессий (`async_sessionmaker[AsyncSession]`)
- `close_db_connection()` — корректное закрытие пула, вызывается при shutdown
- `get_session()` — FastAPI dependency, выдаёт сессию на один запрос

---

## 2. BaseModel

**Файл:** `src/infrastructure/database/base.py`

Единый базовый класс для всех ORM-моделей (`DeclarativeBase`). Автоматически генерирует `__tablename__` из имени класса (PascalCase → snake_case + plural suffix: `StockTransfer` → `stock_transfers`).

Общие колонки во всех таблицах:

| Колонка      | Тип                        | Описание                                      |
| ------------ | -------------------------- | --------------------------------------------- |
| `id`         | UUID PK (UUIDv7)           | `default=uuid.uuid7` (time-ordered)           |
| `is_active`  | BOOLEAN NOT NULL           | Флаг мягкого удаления; `server_default=true`  |
| `created_at` | TIMESTAMP WITH TIME ZONE   | `server_default=now()`                        |
| `updated_at` | TIMESTAMP WITH TIME ZONE   | `server_default=now()`, `onupdate=now()`      |

---

## 3. BaseSQLAlchemyUoW

**Файл:** `src/infrastructure/database/uow.py`

Реализует интерфейс `IUnitOfWork` (`src/common/uow.py`) поверх `AsyncSession`.

**Публичные методы:**

| Метод        | Поведение                                                                         |
| ------------ | --------------------------------------------------------------------------------- |
| `__aenter__` | Создаёт новую сессию через `_session_factory()`                                   |
| `__aexit__`  | При исключении — rollback; в любом случае закрывает сессию                        |
| `flush()`    | Синхронизирует изменения с БД без коммита                                         |
| `commit()`   | Фиксирует транзакцию; перехватывает `IntegrityError` → `ConflictError` (409)     |
| `rollback()` | Откатывает транзакцию                                                             |
| `session`    | Property; выбрасывает `RuntimeError` при обращении вне `async with`               |

---

## 4. Model Registry

**Файл:** `src/infrastructure/database/models.py`

Центральный импорт всех ORM-классов для регистрации метаданных. Используется `alembic/env.py` (`target_metadata = BaseModel.metadata`).

Экспортирует: `BaseModel`, `Product`, `Account`, `Transaction`, `Balance`, `Inventory`, `StockTransaction`, `StockTransfer`, `StockTransferItem`, `Order`, `OrderItem`, `Identity`, `User`.

---

## 5. Схема базы данных (12 таблиц)

### products

```
id (UUID PK), returnable_item_id (FK self RESTRICT nullable),
type (ENUM product_type_enum), name (VARCHAR 255),
price (BIGINT NOT NULL), attributes (JSONB server_default='{}'),
is_active, created_at, updated_at
Constraints: CK price >= 0 (ck_product_price_pos)
Indexes: GIN(attributes) idx_product_attributes_gin,
         ix_products_type, ix_products_returnable_item_id
```

### users

```
id (UUID PK), username (VARCHAR 255 NOT NULL), role (ENUM user_role_enum),
is_active, created_at, updated_at
Indexes: ix_users_role
```

### identities

```
id (UUID PK), user_id (FK users CASCADE NOT NULL),
provider (ENUM auth_provider_enum), provider_identity_id (VARCHAR 255),
password_hash (VARCHAR 255 nullable),
is_active, created_at, updated_at
Constraints: UNIQUE(provider, provider_identity_id) uq_identities_provider_identity_id
Indexes: ix_identities_user_id
```

### accounts

```
id (UUID PK), user_id (FK users RESTRICT NOT NULL), type (ENUM account_type_enum),
name (VARCHAR 255), balance (BIGINT NOT NULL server_default=0),
is_active, created_at, updated_at
Indexes: idx_account_user_type(user_id, type), ix_accounts_type
```

> `balance` имеет `server_default=0` в ORM (`src/modules/finances/models.py`),
> однако реальные изменения вносятся строго через SQL-триггер `update_account_balances`.
> Прямые UPDATE баланса через приложение не допускаются.

### inventories

```
id (UUID PK), user_id (FK users RESTRICT NOT NULL), type (ENUM inventory_type_enum),
name (VARCHAR 255), is_active, created_at, updated_at
Indexes: idx_inventory_user_type(user_id, type), ix_inventories_type,
         uq_active_courier_inventory UNIQUE(user_id) WHERE type='COURIER' AND is_active=true
```

### inventory_balances

```
id (UUID PK), inventory_id (FK inventories CASCADE),
product_id (FK products CASCADE), quantity (INTEGER NOT NULL),
is_active, created_at, updated_at
Constraints: UNIQUE(inventory_id, product_id) uq_inventory_product_balance
Indexes: ix_inventory_balances_product_id
```

> **ВАЖНО (расхождение модель/миграция):** ORM-модель `Balance`
> (`src/modules/inventory/models.py`) объявляет
> `CheckConstraint("quantity >= 0", name="ck_inventory_balances_quantity_non_negative")`,
> однако эта проверка **отсутствует** в миграции `4a1ea97312ca_init.py`.
> В реальной БД ограничение не применяется. Необходима новая миграция
> `op.create_check_constraint(...)`. До её применения остатки могут уйти
> в отрицательные значения на уровне БД.

### orders

```
id (UUID PK), client_id (FK users RESTRICT NOT NULL),
client_inventory_id (FK inventories RESTRICT NOT NULL),
courier_id (FK users SET NULL nullable),
payment_method (ENUM payment_method_enum),
status (ENUM order_status_enum default=new),
total_amount (BIGINT NOT NULL default=0),
capitalization_applied (BOOL NOT NULL server_default=false),
sale_type (VARCHAR 30 NOT NULL server_default='delivery'),
warehouse_id (FK inventories RESTRICT nullable),
is_active, created_at, updated_at
Indexes: ix_orders_client_id, ix_orders_client_inventory_id,
         ix_orders_courier_id, ix_orders_status,
         ix_orders_sale_type, ix_orders_warehouse_id
```

> **Расхождение модель/миграция:** ORM-модель (`src/modules/orders/models.py`)
> объявляет `sale_type` как `Enum(SaleType, name="sale_type_enum")`,
> тогда как в миграции `4a1ea97312ca_init.py` это колонка `String(30)` с
> `server_default="delivery"`. В реальной БД — VARCHAR(30), не enum-тип.

### order_items

```
id (UUID PK), order_id (FK orders CASCADE NOT NULL),
product_id (FK products RESTRICT NOT NULL),
quantity (INTEGER NOT NULL), unit_price (BIGINT NOT NULL),
is_active, created_at, updated_at
Constraints: CK quantity > 0 (ck_order_item_quantity_pos),
             CK unit_price >= 0 (ck_order_item_price_pos)
Indexes: ix_order_items_order_id, ix_order_items_product_id
```

### stock_transfers

```
id (UUID PK), from_id (FK inventories RESTRICT), to_id (FK inventories RESTRICT),
created_by_id (FK users RESTRICT), accepted_by_id (FK users RESTRICT nullable),
order_id (FK orders RESTRICT nullable), reason (VARCHAR 255 nullable),
route_sheet_id (UUID nullable), type (ENUM transfer_type_enum),
status (ENUM transfer_status_enum default=DRAFT),
is_active, created_at, updated_at
Constraints: CK from_id != to_id (ck_stock_transfer_no_circular),
             UNIQUE(id, from_id, to_id) uq_stock_transfer_route
Indexes: ix_stock_transfers_from_id, ix_stock_transfers_to_id,
         ix_stock_transfers_order_id, ix_stock_transfers_route_sheet_id,
         ix_stock_transfers_status, ix_stock_transfers_type
```

### stock_transfer_items

```
id (UUID PK), transfer_id (FK stock_transfers CASCADE),
product_id (FK products RESTRICT), quantity (INTEGER NOT NULL),
is_active, created_at, updated_at
Constraints: CK quantity > 0 (ck_stock_transfer_item_quantity_pos)
Indexes: ix_stock_transfer_items_transfer_id, ix_stock_transfer_items_product_id
```

### stock_transactions (Строгий леджер)

```
id (UUID PK), product_id (FK products RESTRICT),
transfer_id (UUID NOT NULL), from_id (FK inventories RESTRICT),
to_id (FK inventories RESTRICT), quantity (INTEGER NOT NULL),
is_active, created_at, updated_at
Constraints: CK quantity > 0 (ck_stock_transaction_quantity_positive)
FK: (transfer_id, from_id, to_id) -> stock_transfers(id, from_id, to_id)
    CASCADE (fk_stock_transaction_strict_route)
Indexes: idx_st_product_from(product_id, from_id), idx_st_product_to(product_id, to_id),
         ix_stock_transactions_from_id, ix_stock_transactions_to_id,
         ix_stock_transactions_product_id, ix_stock_transactions_transfer_id
```

### transactions (Финансовый леджер)

```
id (UUID PK), from_id (FK accounts RESTRICT), to_id (FK accounts RESTRICT),
order_id (FK orders SET NULL nullable),
verified_by_id (FK users RESTRICT nullable),
amount (BIGINT NOT NULL), status (ENUM transaction_status_enum default=pending),
reason (VARCHAR 255 NOT NULL),
is_active, created_at, updated_at
Constraints: CK amount > 0 (ck_transaction_amount_pos),
             CK from_id != to_id (ck_transaction_no_self_transfer)
Indexes: idx_transaction_from_status(from_id, status),
         idx_transaction_to_status(to_id, status),
         ix_transactions_order_id, ix_transactions_verified_by_id
```

---

## 6. PG Triggers

**Файлы:** `src/infrastructure/database/scripts/update_account_balances.sql`,
`src/infrastructure/database/scripts/update_inventory_balances.sql`

**Миграция:** `alembic/versions/b8e855f8adba_triggers.py`

### update_account_balances()

**Таблица:** `transactions` → `accounts.balance`

**Логика:**

- **DELETE**: ЗАПРЕЩЕНО (Strict Ledger) — исключение
- **UPDATE**: `amount` и `from_id`/`to_id` неизменяемы — исключение при попытке
- **INSERT** со `status='completed'`: `diff_from = -amount`, `diff_to = +amount`
- **UPDATE** `status` из другого в `'completed'`: применяет дельту
- **UPDATE** `status` из `'completed'` в другой: откатывает дельту
- **Deadlock protection**: блокирует строки `accounts` в ORDER BY `id` перед UPDATE

### update_inventory_balances()

**Таблица:** `stock_transactions` → `inventory_balances.quantity`

**Логика:**

- **UPDATE**: ЗАПРЕЩЕНО (Strict Ledger) — исключение
- **DELETE**: ЗАПРЕЩЕНО (Strict Ledger) — исключение
- **INSERT**: Upsert двух строк в `inventory_balances`:
  - `(from_id, product_id, -quantity)` — списание
  - `(to_id, product_id, +quantity)` — поступление
  - `ON CONFLICT (inventory_id, product_id) DO UPDATE SET quantity += EXCLUDED.quantity`
  - Вставка в `ORDER BY inv_id` для избежания deadlock

---

## 7. Все Enum типы

### Role (users, name=`user_role_enum`)

`system`, `admin`, `accountant`, `storekeeper`, `cashier`, `courier`, `client_b2c`, `client_b2b`

### AuthProvider (users, name=`auth_provider_enum`)

`local`, `google`, `telegram`, `apple`

### ProductType (catalog, name=`product_type_enum`)

`water`, `container`, `equipment`

### AccountType (finances, name=`account_type_enum`)

`revenue`, `cash`, `card`, `bank`, `discount`, `client`, `courier`

### TransactionStatus (finances, name=`transaction_status_enum`)

`pending`, `completed`, `rejected`

### InventoryType (inventory, name=`inventory_type_enum`)

`WAREHOUSE`, `COURIER`, `CLIENT`, `VIRTUAL_LOSS`, `VIRTUAL_VENDOR`

### TransferType (inventory, name=`transfer_type_enum`)

`COURIER_LOAD`, `COURIER_RETURN`, `CLIENT_DELIVERY`, `CLIENT_RETURN`, `LOSS_WRITE_OFF`, `INVENTORY_FINDING`, `INITIAL_BALANCE`, `WAREHOUSE_SALE`, `WAREHOUSE_TARA_RETURN`

### TransferStatus (inventory, name=`transfer_status_enum`)

`DRAFT`, `COMPLETED`, `CANCELLED`

### OrderStatus (orders, name=`order_status_enum`)

`new`, `assigned`, `in_transit`, `arrived`, `delivered`, `pickup_completed`, `cancelled`

### PaymentMethod (orders, name=`payment_method_enum`)

`cash`, `card`, `contract`

### SaleType (orders)

`delivery`, `warehouse_pickup`

> ORM-модель объявляет enum `sale_type_enum`, но в реальной БД (миграция
> `4a1ea97312ca_init.py`) колонка `orders.sale_type` — `VARCHAR(30)`, а не
> PostgreSQL enum-тип. SaleType не создаётся как DB-тип через миграцию.

---

## 8. Миграции Alembic

**Конфигурация:** `alembic/env.py` — async-режим, `target_metadata = BaseModel.metadata`, `sqlalchemy.url` подставляется из `settings.database_url` в рантайме.

| Revision     | Файл                                   | Описание                                          |
| ------------ | -------------------------------------- | ------------------------------------------------- |
| 4a1ea97312ca | `4a1ea97312ca_init.py`                 | init — все 12 таблиц, индексы, FK, CHECK          |
| b8e855f8adba | `b8e855f8adba_triggers.py`             | triggers — 2 PL/pgSQL функции и триггера          |

---

## 9. Инициализация данных

**Файл:** `src/core/init.py`, функция `init_data()`

Вызывается при старте приложения. Создаёт базовые записи идемпотентно (проверяет существование перед вставкой):

1. **Системный пользователь** — `role=SYSTEM`, фиксированный UUID из `settings.SYSTEM_USER_ID`
2. **Системные финансовые счета** (владелец — системный пользователь):
   - `REVENUE` — "Выручка"
   - `CASH` — "Кассовый счёт"
   - `CARD` — "Карта"
   - `BANK` — "Банковский счёт"
3. **Виртуальные инвентари** (владелец — системный пользователь):
   - `VIRTUAL_VENDOR` — "Оприходование"
   - `VIRTUAL_LOSS` — "Списание (Брак и Потери)"
4. **Walk-in пользователь** — фиксированный UUID `WALKIN_USER_ID` (из `src/core/constants.py`), `role=CLIENT_B2C`, `provider_identity_id="00000000002"`. Создаётся вместе с `CLIENT` инвентарём "Самовывоз" и `CLIENT` счётом "Счёт анонимных покупок". Используется для складских продаж без привязки к конкретному клиенту.
5. **Главный администратор** — создаётся только если заданы `ADMIN_PHONE` и `ADMIN_PASSWORD` в environment-переменных.

---

## 10. Конфигурация проекта

### pyproject.toml

- Python >= 3.14, line-length = 79
- Ruff rules: E, W, F, I, B, C4, UP, SIM (ignore UP037)
- pytest: asyncio_mode = "auto", testpaths = ["tests"]

### Makefile

```
make up          # docker compose up
make dev         # uv run fastapi dev src/main.py
make migrate     # alembic revision --autogenerate
make upgrade     # alembic upgrade head
make test        # pytest -v
make format      # ruff format + check --fix
make lint        # ruff check
```

### Docker

- Base: python:3.14-slim-trixie
- Package manager: uv (Astral)
- DB: postgres:18-alpine (pool: max_connections=100, shared_buffers=256MB)
- Deploy: Railway (Dockerfile)

### Environment

```
SECRET_KEY, ENVIRONMENT, DEBUG
PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
REDISHOST, REDISPORT, REDISUSER, REDISPASSWORD
CORS_ORIGINS, ADMIN_PHONE, ADMIN_PASSWORD
ACCESS_TOKEN_EXPIRE_MINUTES (default: 10080 = 7 days)
SYSTEM_USER_ID (default: UUID(int=0))
```

---

## 11. Статистика

| Категория          | Количество |
| ------------------ | ---------- |
| Таблицы            | 12         |
| PL/pgSQL функции   | 2          |
| Триггеры           | 2          |
| Индексы            | ~40        |
| Foreign Keys       | ~26        |
| Check Constraints  | 9          |
| Unique Constraints | 4          |
| Enum типов DB      | 10         |
| Enum типов Python  | 11         |
