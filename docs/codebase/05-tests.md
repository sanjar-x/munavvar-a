# Test Suite - Полная документация

## 1. Структура

```
tests/
+-- conftest.py                              # Root fixtures (DB, client, auth)
+-- data.json                                # Snapshot данных (не используется в тестах)
+-- integration/
|   +-- conftest.py                          # Domain fixtures (users, products, inventories)
|   +-- test_order_fsm.py                    # Order state machine validation
|   +-- test_delivery_fulfillment.py         # TEST-01: Full delivery cycle
|   +-- test_warehouse_pickup.py             # TEST-02: Warehouse pickup flow
|   +-- test_walkin_sale.py                  # TEST-03: Walk-in anonymous sale
|   +-- test_courier_shift_close.py          # TEST-04: Shift close reconciliation
|   +-- test_backoffice_user_roles.py        # User management & role transitions
|   +-- test_backoffice_staff_list.py        # Staff filtering
|   +-- test_backoffice_staff_delete.py      # Staff deletion
|   +-- test_backoffice_transfer_create.py   # Transfer with product serialization
|   +-- test_backoffice_warehouse_create.py  # Warehouse creation
+-- unit/
    +-- test_auth_service.py                 # AuthService logic (8 tests)
    +-- test_bootstrap_alembic.py            # Migration bootstrap (6 tests)
    +-- test_catalog_dto.py                  # ARCH-03: Frozen DTO convention
    +-- test_catalog_public.py               # ARCH-02: Public facade pattern
    +-- test_courier_api.py                  # Courier API routes (4 tests)
    +-- test_courier_orders_auth.py          # Courier permissions (5 tests)
```

---

## 2. Root Conftest (`tests/conftest.py`)

### Key Fixtures

**`anyio_backend` [session scope]**: Фиксирует asyncio-backend на уровне сессии

**`_test_engine` [function scope]**: Новый async SQLAlchemy engine per test

**`db_connection` [function scope]**: Соединение с внешней транзакцией, rollback после теста

**`session_factory` [function scope]**: SessionFactory привязанная к тестовому соединению

**`db_session` [function scope]**: Прямая сессия для fixture data и проверки балансов

**`client` [function scope]**: httpx AsyncClient с monkeypatched session factory для ВСЕХ UoW модулей:

- src.infrastructure.database.session
- src.modules.users/catalog/orders/inventory/finances.dependencies
- src.application.client/courier/inventories.dependencies

### Helper Functions

`make_auth_headers(user_id, role) -> dict` -- генерирует Bearer JWT с role scopes

---

## 3. Integration Conftest (`tests/integration/conftest.py`)

### Helper Functions

`load_stock(session, from_inv_id, to_inv_id, product_id, qty, created_by_id)` -- создает completed stock transfer + ledger entry (PG trigger обновляет inventory_balances)

`credit_account(session, from_account_id, to_account_id, amount, created_by_id)` -- seed account balance через completed transaction

### System Fixtures

**`system_entities` [function]**: Pre-existing entities из init_data():

- system_user, walkin_user
- revenue_account, cash_account, card_account
- virtual_vendor, virtual_loss, walkin_inventory, walkin_account

### Domain Fixtures

- **admin_user** (ADMIN), **courier_user** (COURIER), **client_user** (CLIENT_B2C)
- **products**: water (price=20_000, returnable=tara), tara (price=50_000)
- **warehouse_inventory**, **courier_inventory**, **client_inventory**
- **courier_account**, **client_account**

---

## 4. Integration Tests

### TEST-01: test_delivery_fulfillment.py

**Полный цикл доставки**: загрузка курьера -> создание заказа -> assign -> in_transit -> arrived -> delivered

Проверяет финальные балансы:

- Courier water: 10 - 2 = 8
- Client water: 0 + 2 = 2
- Courier tara: 0 + 2 = 2 (returned)
- Courier account: +40_000 (cash collected)
- Revenue account: -40_000

### TEST-02: test_warehouse_pickup.py

**Самовывоз со склада**: создание warehouse sale -> complete-pickup

### TEST-03: test_walkin_sale.py

**Анонимная продажа**: warehouse sale без clientId -> LOSS_WRITE_OFF очищает walk-in inventory

### TEST-04: test_courier_shift_close.py

**Закрытие смены**: возврат товаров + инкассация + деактивация inventory

### test_order_fsm.py (4 теста)

- Reject assign non-courier user
- Reject assign courier without inventory
- Reject skipping to delivered
- Reject reassign after in_transit

### test_backoffice_user_roles.py (2 теста)

- Create staff user and login
- Promote passwordless client to courier requires password

### test_backoffice_staff_list.py

Filter by roles query params

### test_backoffice_staff_delete.py

DELETE user + identity from DB

### test_backoffice_transfer_create.py (2 теста)

Transfer response includes product.id, product.name

### test_backoffice_warehouse_create.py

Warehouse response includes nested user object

---

## 5. Unit Tests

### test_auth_service.py (7 тестов)

- Staff login returns token with scopes
- Client login rejects staff accounts
- Courier login returns courier token with scopes
- Courier login rejects non-courier staff
- Masks invalid hash as invalid credentials
- Client login rejects staff accounts
- Rejects walkin account

### test_catalog_dto.py (4 теста) -- ARCH-03

- DTO is frozen (immutable)
- DTO has **slots**
- DTO field count = 9
- Converter copies attributes dict

### test_catalog_public.py (7 тестов) -- ARCH-02

- `__all__` определён и содержит ровно {CatalogService, ProductDTO, ProductType}
- CatalogService importable
- ProductDTO importable
- ProductType importable
- ProductRepository NOT exported
- CatalogUnitOfWork NOT exported
- Exceptions NOT exported (ProductNotFoundError, InvalidReturnableItemError)

### test_bootstrap_alembic.py (7 тестов)

**Внимание:** тест импортирует `scripts.bootstrap_alembic`, но файл `scripts/bootstrap_alembic.py` отсутствует в репозитории. Тесты **не пройдут** до создания этого модуля.

- Fresh DB = None
- Already initialized (existing revision) = None
- Tables without triggers = INIT_REVISION
- Tables with triggers = HEAD_REVISION
- Legacy revision without triggers -> purge + INIT_REVISION
- Legacy revision with triggers -> purge + HEAD_REVISION
- Partially initialized schema = None

### test_courier_api.py (3 теста)

- Login route uses phone+password
- Orders list returns tasks for current courier
- Orders list rejects non-courier role (403 COURIER_ONLY)

### test_courier_orders_auth.py (2 параметризованных функции × 5 маршрутов = 10 тест-кейсов)

- `test_courier_mutation_routes_accept_orders_deliver_scope` — 5 маршрутов (in-transit, arrived, delivered, deliver legacy, status) проходят с ORDERS_DELIVER scope
- `test_courier_mutation_routes_reject_missing_orders_deliver_scope` — те же 5 маршрутов отклоняются с ORDERS_READ scope (403 INSUFFICIENT_PERMISSIONS)

---

## 6. Конфигурация

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
pythonpath = ["."]
```

**DB Strategy**: Per-test transaction с rollback. PG triggers активны.

---

## 7. Покрытие и пробелы

### Покрыто

- Delivery lifecycle (full E2E)
- Warehouse pickup flow
- Walk-in sales with writeoff
- Shift close reconciliation
- Order FSM validation
- User management & roles
- Auth service logic
- Architecture constraints (frozen DTOs, public facade)
- Permission checking (parametrized)

### Пробелы

- Client-facing API не покрыта (src.application.client)
- Card payment method не протестирован (только CASH)
- Concurrent/race condition тесты отсутствуют
- Architecture dependency tests (pytest-archon в deps, но не используется)
- Нет load тестов (locust в deps, но не используется)
- Мало negative path тестов (validation errors)
- Catalog/product logic sparse coverage
