# Application Layer & Core - Полная документация

## Обзор

Application layer оркестрирует кросс-доменные операции, объединяя репозитории из разных модулей в единые транзакции.

```
src/application/
+-- client/        # Управление клиентами (кросс-доменное)
+-- courier/       # Управление курьерами (кросс-доменное)
+-- inventories/   # UoW и схемы для складов/машин (сервис пустой)
+-- order/         # Схемы и UoW для заказов (сервис отсутствует)
```

---

## 1. Client Management

### ClientService (`src/application/client/service.py`)

**Зависимости**: ClientUnitOfWork, CatalogService

#### create_client(data: ClientCreate) -> ClientResponse

1. Проверка дубликата phone в identities (`get_local_by_id`)
2. Создание User (CLIENT_B2C или CLIENT_B2B)
3. Создание Identity (LOCAL) через `add_local`
4. Создание Account (CLIENT) через `create_client_account`
5. Опционально: создание Inventory (CLIENT) через `create_client_inventory`, если передан `address_name`
6. Commit → вызов `get_client` для возврата полного ответа

#### create_client_inventory(client_id: uuid.UUID, data: InventoryCreate) -> ClientResponse

Добавление нового адреса доставки (Inventory type=CLIENT). Проверяет существование клиента перед добавлением.

#### get_clients(skip: int, limit: int, search: str | None = None) -> dict[str, Any]

Пагинированный список клиентов. Возвращает `{"total_count": int, "clients": list[dict]}`. Каждый элемент содержит: id, username, role, phone, is_active, orders (count), created_at.

#### get_client(client_id: uuid.UUID) -> ClientResponse

Карточка клиента с inventories (с balances), client_orders, account, phone. Использует `get_client_with_details`, `get_local_by_user`, `get_client_account`.

#### onboard_client_with_balance(data: ClientOnboardingRequest, creator_id: uuid.UUID) -> ClientResponse

**Единое окно онбординга** (самый сложный сценарий):

1. Проверка дубликата телефона (Identity)
2. Создание User (Role из `data.role`)
3. Создание Identity (LOCAL)
4. Создание финансового счета (`create_client_account`)
5. Создание склада клиента (`create_client_inventory`) — обязательно, не опционально
6. Опциональное оприходование начальных остатков тары: если `initial_balance_quantity > 0` и `initial_balance_product_id` — создает Transfer (VIRTUAL_VENDOR → CLIENT, type=INITIAL_BALANCE, status=COMPLETED), TransferItem, StockTransaction
7. Опциональный первый заказ: если `data.order` — получает цены через `catalog_service.get_by_ids`, создает Order + OrderItems; raises `ProductsUnavailableError` при отсутствии товаров
8. Commit всех операций в одной транзакции → возврат `get_client`

### ClientUnitOfWork (`src/application/client/uow.py`)

Интерфейс `IClientUnitOfWork` + реализация `ClientUnitOfWork`.

| Репозиторий        | Тип                          | Модуль    | Назначение            |
| ------------------ | ---------------------------- | --------- | --------------------- |
| products           | ProductRepository            | catalog   | Валидация товаров     |
| identities         | IdentityRepository           | users     | Проверка phone        |
| users              | UserRepository               | users     | CRUD пользователей    |
| accounts           | AccountRepository            | finances  | Финансовые счета      |
| transactions       | TransactionRepository        | finances  | Финансовые транзакции |
| inventories        | InventoryRepository          | inventory | Локации               |
| transfers          | StockTransferRepository      | inventory | Накладные             |
| transfer_items     | StockTransferItemRepository  | inventory | Строки накладных      |
| stock_transactions | StockTransactionRepository   | inventory | Леджер                |
| orders             | OrderRepository              | orders    | Заказы                |
| order_items        | OrderItemRepository          | orders    | Позиции заказов       |

### Client Dependencies (`src/application/client/dependencies.py`)

- `get_client_uow() -> IClientUnitOfWork` — фабрика для `ClientUnitOfWork`
- `get_client_service(uow, catalog_service) -> ClientService` — инжектирует `ClientUnitOfWork` и `CatalogService`

### Client Schemas (`src/application/client/schemas.py`)

**Вспомогательные enum:**
- `ClientRole(StrEnum)` — `CLIENT_B2C`, `CLIENT_B2B`

**Input:**
- `ClientCreate` — username, phone, role (ClientRole, default=CLIENT_B2C), address_name (опционально)
- `InventoryCreate` — name
- `InventoryUpdate` — name (опционально)
- `ClientUpdate` — username, phone, role (опционально; role ограничен `Literal[Role.CLIENT_B2C, Role.CLIENT_B2B]`)
- `ClientOnboardingRequest` — username, phone, address_name, role (ClientRole), initial_balance_product_id (uuid | None), initial_balance_quantity (int, ge=0), order (OnboardingOrderSchema | None)
- `OnboardingOrderItemSchema` — product_id, quantity
- `OnboardingOrderSchema` — items (list[OnboardingOrderItemSchema]), payment_method

**Вложенные DTO (для ответов):**
- `Account` — name, balance (from_attributes=True)
- `Product` — type (ProductType), name, price, attributes
- `Balance` — quantity, product (Product)
- `Inventory` — id, type (InventoryType), name, balances (list[Balance])
- `ClientInventory` — id, type (InventoryType), name (без balances)
- `Courier` — username
- `Item` — quantity, unit_price, product (Product); computed_field `subtotal`
- `Order` — payment_method, status, total_amount, client_inventory (ClientInventory), courier (Courier | None), items (list[Item]), created_at

**Output:**
- `ClientResponse` — id, username, phone (str | None), account (Account | None), inventories (list[Inventory]), client_orders (list[Order]); validate_assignment=True
- `Client` — id, role (ClientRole), username, phone, is_active, orders (int), created_at
- `ClientsResponse` — total_count, clients (list[Client])

### Client Exceptions (`src/application/client/exceptions.py`)

- `ClientNotFoundError(client_id)` — 404, `CLIENT_NOT_FOUND`
- `ClientAlreadyExistsError(phone)` — 409, `CLIENT_ALREADY_EXISTS`
- `ClientInactiveError(phone?, client_id?)` — 401, `CLIENT_INACTIVE`
- `ClientAddressNotFoundError(inventory_id)` — 404, `CLIENT_ADDRESS_NOT_FOUND`

---

## 2. Courier Management

### CourierService (`src/application/courier/service.py`)

**Зависимости**: CourierUnitOfWork (без CatalogService)

#### create_courier(data: CourierCreate) -> dict[str, Any]

1. Проверка дубликата phone (`get_local_by_id`)
2. Создание User (Role.COURIER, is_active=True)
3. flush сессии
4. Хеширование пароля (`get_password_hash`)
5. Создание Identity через `uow.identities.add(...)` с полями provider, provider_identity_id, password_hash
6. Создание Account (`create_courier_account`)
7. Commit → возврат `get_courier`
8. Обработка `IntegrityError` на уникальный constraint `uq_identities_provider_identity_id` → `CourierAlreadyExistsError`

**Примечание:** В отличие от ClientService, Identity создается напрямую через `add(...)`, а не через специализированный `add_local`.

#### create_courier_inventory(courier_id: uuid.UUID, data: InventoryCreate) -> dict[str, Any]

Создание машины (Inventory type=COURIER). Обрабатывает `IntegrityError` на constraint `uq_user_single_courier_inventory` → `ConflictError("COURIER_INVENTORY_ALREADY_EXISTS")`.

#### get_couriers(skip: int, limit: int, search: str | None = None) -> dict[str, Any]

Список курьеров. Возвращает `{"total_count": int, "couriers": list[dict]}`. Каждый dict содержит: id, username, phone, account, inventory, is_active, orders (count), created_at.

#### get_courier(courier_id: uuid.UUID) -> dict[str, Any]

Полная карточка курьера. Возвращает dict с: id, username, phone, is_active, account, inventory, orders (список объектов заказов).

### CourierUnitOfWork (`src/application/courier/uow.py`)

Интерфейс `ICourierUnitOfWork` + реализация `CourierUnitOfWork`.

| Репозиторий        | Тип                        | Модуль    |
| ------------------ | -------------------------- | --------- |
| products           | ProductRepository          | catalog   |
| identities         | IdentityRepository         | users     |
| users              | UserRepository             | users     |
| accounts           | AccountRepository          | finances  |
| transactions       | TransactionRepository      | finances  |
| inventories        | InventoryRepository        | inventory |
| stock_transactions | StockTransactionRepository | inventory |
| orders             | OrderRepository            | orders    |

**Примечание:** В отличие от `ClientUnitOfWork`, отсутствуют `transfers`, `transfer_items`, `order_items`.

### Courier Dependencies (`src/application/courier/dependencies.py`)

- `get_courier_uow() -> CourierUnitOfWork` — фабрика для `CourierUnitOfWork`
- `get_courier_service(uow) -> CourierService` — инжектирует `CourierUnitOfWork`

### Courier Schemas (`src/application/courier/schemas.py`)

**Input:**
- `CourierCreate` — username, phone, password
- `CourierUpdate` — username, phone, password, is_active (все опциональны)

**Вспомогательные DTO:**
- `AccountShortDTO` — id, name, balance (from_attributes=True)
- `InventoryShortDTO` — id, name
- `CourierInventoryWithBalancesDTO(InventoryShortDTO)` — добавляет balances (list[Any])

**Output:**
- `Courier` — id, username, phone (str | None), account (AccountShortDTO | None), inventory (InventoryShortDTO | None), is_active, orders (int), created_at
- `CouriersResponse` — total_count, couriers (list[Courier])
- `CourierResponse` — id, username, phone, is_active, account (AccountShortDTO | None), inventory (CourierInventoryWithBalancesDTO | None), orders (list[Any])

**Важно:** `CourierCreate` импортируется из `src/application/inventories/schemas.py` для `InventoryCreate` в `create_courier_inventory`.

### Courier Exceptions (`src/application/courier/exceptions.py`)

- `CourierNotFoundError(courier_id)` — 404, `COURIER_NOT_FOUND`
- `CourierAlreadyExistsError(phone)` — 409, `COURIER_ALREADY_EXISTS`
- `CourierInactiveError(phone?, courier_id?)` — 401, `COURIER_INACTIVE`
- `CourierInventoryNotFoundError(inventory_id)` — 404, `COURIER_INVENTORY_NOT_FOUND`
- `CourierHasBalancesError(message?)` — 400, `COURIER_HAS_BALANCES`

---

## 3. Order Management

**Статус:** `src/application/order/` содержит только `schemas.py` и `uow.py`. Файлы `service.py`, `dependencies.py`, `exceptions.py` **отсутствуют** — бизнес-логика заказов реализована в `src/modules/orders/services.py` (`BaseOrderService`) и оркестрируется через `BaseOrderUnitOfWork`.

### OrderUnitOfWork (`src/application/order/uow.py`)

Интерфейс `IOrderUnitOfWork` + реализация `OrderUnitOfWork`.

| Репозиторий        | Тип                        | Модуль    |
| ------------------ | -------------------------- | --------- |
| products           | ProductRepository          | catalog   |
| accounts           | AccountRepository          | finances  |
| transactions       | TransactionRepository      | finances  |
| inventories        | InventoryRepository        | inventory |
| stock_transactions | StockTransactionRepository | inventory |
| stock_transfers    | StockTransferRepository    | inventory |
| order_items        | OrderItemRepository        | orders    |
| orders             | OrderRepository            | orders    |
| users              | UserRepository             | users     |

**Отличие от `BaseOrderUnitOfWork` (modules/orders/uow.py):** `OrderUnitOfWork` не содержит `transfer_items` и `financial_transactions`. API роуты используют `BaseOrderUnitOfWork` через `BaseOrderService`.

### Order Schemas (`src/application/order/schemas.py`)

**Вложенные DTO:**
- `OrderItemCreate` — product_id, quantity (gt=0)
- `MissingTaraDTO` — product_id (str), name, missing_quantity

**Input:**
- `CartValidateRequest` — inventory_id, items (list[OrderItemCreate], min_length=1)
- `OrderCreate` — inventory_id, payment_method, items (min_length=1), is_initial_tara (bool, default=False)
- `OrderDeliveryCompleteRequest` — actual_returned_tara (dict[uuid.UUID, int], default={})

**Output:**
- `CartValidationResponse` — is_valid, needs_initial_tara, missing_items (list[MissingTaraDTO]), message (str | None)
- `OrderResponse` — id, client_id, client_inventory_id, payment_method, status (str), total_amount (float); from_attributes=True

**Важно:** Схемы в `src/application/order/schemas.py` носят черновой/вспомогательный характер. Фактически в API используются схемы из `src/modules/orders/schemas.py`.

---

## 4. Inventories Management

**Статус:** `src/application/inventories/service.py` **пустой** — бизнес-логика складов реализована в `src/modules/inventory/`. Файл `exceptions.py` также пустой.

### InventoryUnitOfWork (`src/application/inventories/uow.py`)

Интерфейс `IInventoryUnitOfWork` + реализация `InventoryUnitOfWork`.

| Репозиторий        | Тип                        | Модуль    |
| ------------------ | -------------------------- | --------- |
| inventories        | InventoryRepository        | inventory |
| stock_transactions | StockTransactionRepository | inventory |
| products           | ProductRepository          | catalog   |
| users              | UserRepository             | users     |

### Inventory Dependencies (`src/application/inventories/dependencies.py`)

- `get_inventory_uow() -> IInventoryUnitOfWork` — фабрика для `InventoryUnitOfWork`

### Inventory Schemas (`src/application/inventories/schemas.py`)

- `InventoryCreate` — name, type (InventoryType, default=CLIENT), user_id (UUID)
- `InventoryUpdate` — name (str | None), user_id (uuid | None)

**Примечание:** `InventoryCreate` из этого модуля используется в `CourierService.create_courier_inventory`.

---

## 5. Core Layer

### Settings (`src/core/config.py`)

```
PROJECT_NAME, VERSION, ENVIRONMENT (dev/test/prod), DEBUG
SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES (7 days)
PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
REDISHOST, REDISPORT, REDISUSER, REDISPASSWORD
CORS_ORIGINS, SYSTEM_USER_ID, ADMIN_PHONE, ADMIN_PASSWORD
```

### JWT Security (`src/core/security/jwt.py`)

- `create_access_token(payload_data, expires_delta?) -> str` -- HS256, claims: exp, iat, jti
- `decode_access_token(token) -> dict` -- raises UnauthorizedError

### Password Security (`src/core/security/password.py`)

- `get_password_hash(password) -> str` -- Bcrypt (через `pwdlib` с `BcryptHasher`)
- `verify_password(plain, hashed) -> bool`

> **Примечание:** В README упоминается Argon2, но фактически используется только Bcrypt (`BcryptHasher`). Argon2 в зависимостях присутствует (`pwdlib[argon2,bcrypt]`), но в коде не активирован.

### Base Exceptions (`src/core/exceptions.py`)

```
AppException (message, status_code, error_code, details)
+-- NotFoundError (404)
+-- BadRequestError (400)
+-- UnauthorizedError (401)
+-- ForbiddenError (403)
+-- ConflictError (409)
+-- UnprocessableEntityError (422)
+-- ServiceUnavailableError (503)
```

### Database Init (`src/core/init.py`)

`init_data()` создает при старте:

1. SYSTEM_USER (Role.SYSTEM)
2. Системные счета (REVENUE, CASH, CARD, BANK)
3. Виртуальные склады (VIRTUAL_VENDOR, VIRTUAL_LOSS)
4. WALK-IN пользователь для анонимных покупок
5. Admin (если ADMIN_PHONE и ADMIN_PASSWORD заданы)

### Seeder (`src/core/seeder.py`)

`seed_all()` -- тестовые данные: товары, склады, пользователи, заказы

### Logging (`src/core/logger.py`)

- JSON в prod, консоль с цветом в dev
- structlog с contextvars (request_id, IP, method, path)

---

## 6. Common Layer

### IUnitOfWork (`src/common/uow.py`)

```python
__aenter__, __aexit__, flush(), commit(), rollback()
```

### BaseRepository[ModelType] (`src/common/repository.py`)

```python
get(), get_by(), get_multi(), add(), add_many(),
update(), archive(), delete(), count()
```

### BaseService[ModelType, CreateSchemaType, UoWType, DTOType] (`src/common/service.py`)

```python
get(), get_multi(), add(), update(), archive(), delete()
```

### BaseSQLAlchemyUoW (`src/infrastructure/database/uow.py`)

- Async context manager
- commit() с перехватом IntegrityError -> ConflictError
- Автоматический rollback при исключении

### BaseModel (`src/infrastructure/database/base.py`)

- id: UUIDv7, is_active: bool, created_at, updated_at
- Автогенерация `__tablename__`

---

## Диаграмма зависимостей

```
ClientService
+-- ClientUnitOfWork (11 репозиториев)
+-- CatalogService -> CatalogUnitOfWork

CourierService
+-- CourierUnitOfWork (8 репозиториев)

OrderUnitOfWork (application/order/uow.py)
+-- 9 репозиториев (используется в связанных сценариях)

BaseOrderService (src/modules/orders/services.py)
+-- BaseOrderUnitOfWork (src/modules/orders/uow.py)
+-- CatalogService

InventoryUnitOfWork (application/inventories/uow.py)
+-- 4 репозитория (используется в API складов)
```

---

## Ключевые паттерны

1. **Unit of Work**: Одна транзакция для всех кросс-доменных операций
2. **Repository**: Базовый CRUD + специализированные методы
3. **Dependency Injection**: FastAPI Depends() для UoW и сервисов
4. **Soft Delete**: is_active флаг, archive() метод
5. **Event Sourcing**: Append-only леджеры для финансов и инвентаря
