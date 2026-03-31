# Domain Modules - Полная документация

## Обзор модулей

```
src/modules/
+-- auth/       # Аутентификация (JWT, login)
+-- users/      # Пользователи и Identity
+-- catalog/    # Товары и каталог
+-- orders/     # Заказы и позиции
+-- inventory/  # Склады, накладные, леджер движений
+-- finances/   # Счета и финансовый леджер
```

---

## 1. Модуль AUTH

### Schemas

- `LocalLogin` -- вход по phone + password
- `TokenResponse` -- JWT access_token + token_type

### Services: AuthService

- `local_login(data: LocalLogin) -> TokenResponse` -- вход сотрудников
- `courier_login(data: LocalLogin) -> TokenResponse` -- вход курьеров
- `client_login(phone: str) -> TokenResponse` -- упрощённый вход клиентов (без пароля)
- `_build_token_response(user)` -- создание JWT с role scopes
- `_authenticate_local_user(data)` -- проверка phone + password

### Dependencies

- `get_token_payload(security_scopes, token)` -- валидация JWT без БД (fast path)
- `get_current_user(payload, user_service)` -- получение юзера из БД (slow path)
- `get_current_courier(current_user)` -- проверка role=COURIER
- `get_auth_service(user_service)` -- фабрика сервиса

---

## 2. Модуль USERS

### Models

**User**: id, username, role (Enum Role), is_active

- Relationships: identities, accounts, inventories, client_orders, courier_orders
- Property: `phone` -> provider_identity_id первого identity

**Identity**: user_id (FK), provider (Enum AuthProvider), provider_identity_id, password_hash

- Constraint: UNIQUE(provider, provider_identity_id)

### Enums

- **Role**: SYSTEM, ADMIN, ACCOUNTANT, STOREKEEPER, CASHIER, COURIER, CLIENT_B2C, CLIENT_B2B
- **AuthProvider**: LOCAL, GOOGLE, TELEGRAM, APPLE

### Repositories

**UserRepository**:

- `add(obj_data) -> User` -- переопределён: фильтрует только допустимые колонки через `_insertable_keys`
- `add_with_role(role, **kwargs) -> User`
- `add_courier(**kwargs) -> User`, `add_cashier(**kwargs) -> User`, `add_storekeeper(**kwargs) -> User`, `add_accountant(**kwargs) -> User`
- `get(id, active_only, with_for_update) -> User | None` -- переопределён: eagerly loads identities
- `get_by_id(id) -> User | None`
- `get_with_identity(provider, provider_identity_id) -> tuple[User, Identity] | None`
- `get_system_user() -> User`
- `get_courier(id) -> User | None`, `get_cashier(id) -> User | None`, `get_storekeeper(id) -> User | None`, `get_accountant(id) -> User | None`
- `get_client_by_id(id) -> User | None`, `get_client_with_details(client_id) -> User | None`
- `get_staff_with_details(skip, limit, roles, search?) -> tuple[int, Sequence[User]]`
- `get_couriers_with_details(skip, limit, search?) -> tuple[int, Sequence[User]]`
- `get_courier_with_details(courier_id) -> User | None` -- с заказами, товарами позиций
- `get_clients_with_details(skip, limit, search?) -> tuple[int, Sequence[User]]`
- `update(id, obj_data, active_only) -> User` -- переопределён: фильтрует через `_updatable_keys`, поднимает `UserUpdateConflictError` при IntegrityError
- `archive(id) -> bool`, `delete(id) -> bool` -- переопределены; `delete` поднимает `UserDeleteConflictError` при IntegrityError

**IdentityRepository**:

- `add_local(user_id, provider_identity_id, password_hash?) -> Identity`
- `get_local_by_id(provider_identity_id) -> Identity | None`
- `get_local_by_user(user_id) -> Identity` -- поднимает исключение если не найдено
- `get_local_by_user_or_none(user_id) -> Identity | None`
- `get_by_id_and_provider(provider_identity_id, provider) -> Identity | None`
- `get_by_user_and_provider(user_id, provider) -> Identity` -- поднимает исключение если не найдено

### Services: UserService

Наследует `BaseService[User, UserAdminCreate, UserUnitOfWork]`.

- `register_client(schema: UserClientCreate) -> User` -- User + Identity + Account (CLIENT) + Inventory (CLIENT) + опциональная стартовая тара (INITIAL_BALANCE из VIRTUAL_VENDOR)
- `register_local_user(schema: UserAdminCreate) -> User` -- User + Identity; если роль COURIER — также создаёт Account (COURIER)
- `update(id, schema: UserAdminUpdate) -> User` -- обновление пользователя с возможностью создания/обновления локального Identity; при назначении STAFF-роли требует телефон и пароль
- `delete_staff(id) -> None` -- физическое удаление (DELETE); поднимает `UserDeleteConflictError` при FK-ограничениях
- `get_system_user() -> User`
- `get_courier(id) -> User | None`
- `get_couriers(skip, limit, search?) -> dict` -- возвращает `{"total_count": int, "couriers": list}`
- `get_staff(skip, limit, search?, roles?) -> dict` -- возвращает `{"total_count": int, "users": list}`
- `get_user_local_identity(identity_id: str) -> tuple[User, Identity] | None`
- `_ensure_courier_account(user) -> bool` -- создаёт Account(COURIER) если его ещё нет

### Queries: UsersDashboardQuery

Принимает `AsyncSession` напрямую (не через UoW). Два оптимизированных запроса на метод (пагинация + агрегация).

- `get_clients(skip, limit) -> UsersDashboardResponse` -- баланс CLIENT-счёта + остатки тары (только CONTAINER) из ledger
- `get_couriers(skip, limit) -> UsersDashboardResponse` -- баланс COURIER-счёта + складские остатки; вычитает воду из тары (пустые бутыли = физические - занятые водой)

### UoW: UserUnitOfWork

Repositories: users (UserRepository), identities (IdentityRepository), accounts (AccountRepository), inventories (InventoryRepository), transfers (StockTransferRepository), transfer_items (StockTransferItemRepository), transactions (StockTransactionRepository)

**Note:** `UserUnitOfWork` does NOT include a `FinancialTransactionRepository`. The `transactions` field maps to `StockTransactionRepository` from the inventory module. Accounts (`AccountRepository`) подключён для создания COURIER-счетов при регистрации.

### Exceptions

- `UserNotFoundError` (404), `UserAlreadyExistsError` (409), `InvalidCredentialsError` (401)
- `UserInactiveError` (401), `UserForbiddenError` (403)
- `StaffPasswordRequiredError` (422)
- `UserUpdateConflictError` (409), `UserDeleteConflictError` (409)
- `UserServiceUnavailableError` (503)

---

## 3. Модуль CATALOG

### Models

**Product**: type (Enum ProductType), name, price (BIGINT >= 0), attributes (JSONB), returnable_item_id (self-FK)

- `returnable_item` -- ссылка на пустую бутыль
- Constraint: CK price >= 0, GIN-индекс на attributes

### Enums

- **ProductType**: WATER = "water", CONTAINER = "container", EQUIPMENT = "equipment"

### UoW: CatalogUnitOfWork

Repositories: products (ProductRepository)

### Repositories: ProductRepository

- `get_product(product_id) -> Product | None`
- `get_multi_by_ids(product_ids) -> Sequence[Product]` -- с eagerly loaded returnable_item
- `get_catalog_by_type(product_type, skip, limit) -> Sequence[Product]`
- `get_by_json_attribute(key, value, skip, limit) -> Sequence[Product]`

### DTO: ProductDTO (frozen dataclass)

Fields: id, returnable_item_id, type, name, price, attributes, is_active, created_at, updated_at

### Services: CatalogService

Наследует `BaseService[Product, ProductCreate, CatalogUnitOfWork, ProductDTO]`.

- `get_catalog(skip, limit, product_type) -> Sequence[ProductDTO]`
- `get_by_ids(product_ids) -> Sequence[ProductDTO]`
- `search_by_attribute(key, value, skip, limit) -> Sequence[ProductDTO]`
- `add_product(dto: ProductCreate) -> ProductDTO` -- с бизнес-валидацией: WATER обязан иметь returnable_item_id; только WATER может иметь returnable_item_id; returnable_item должен существовать и быть CONTAINER
- Унаследованы: `get()`, `get_multi()`, `update()`, `archive()`, `delete()`

### Public API

Exports: CatalogService, ProductDTO, ProductType

### Exceptions

- `ProductNotFoundError`, `InvalidReturnableItemError`

---

## 4. Модуль ORDERS

### Models

**Order**: client_id (FK User), client_inventory_id (FK Inventory), courier_id (FK User | null), payment_method, status = NEW, total_amount (BIGINT), capitalization_applied = false, sale_type: SaleType = DELIVERY, warehouse_id (FK Inventory | null)

- Relationships: client, client_inventory, courier, items, stock_transfers, transactions

**OrderItem**: order_id (FK CASCADE), product_id (FK RESTRICT), quantity (> 0), unit_price (BIGINT >= 0)

- Property: `total -> quantity * unit_price`

### Enums

- **OrderStatus**: NEW, ASSIGNED, IN_TRANSIT, ARRIVED, DELIVERED, PICKUP_COMPLETED, CANCELLED
- **PaymentMethod**: CASH, CARD, CONTRACT
- **SaleType**: DELIVERY, WAREHOUSE_PICKUP

### State Machine (FSM)

**DELIVERY transitions** (via `_DELIVERY_ALLOWED_TRANSITIONS`):

```
NEW -> CANCELLED
ASSIGNED -> IN_TRANSIT | CANCELLED
IN_TRANSIT -> ARRIVED | CANCELLED
ARRIVED -> DELIVERED | CANCELLED
```

**Note:** `NEW -> ASSIGNED` выполняется через `assign_courier()`, а не через таблицу FSM-переходов. `PICKUP_COMPLETED` нельзя выставить через `update_status()` вручную — только через `complete_pickup()`.

**PICKUP transitions** (via `_PICKUP_ALLOWED_TRANSITIONS`):

```
NEW -> CANCELLED
```

`NEW -> PICKUP_COMPLETED` выполняется только через `complete_pickup()`, не через `update_status()`.

### Repositories

**OrderRepository**:

- `get_client_orders(client_id, skip, limit) -> Sequence[Order]`
- `get_active_courier_orders(courier_id) -> Sequence[Order]` -- ASSIGNED, IN_TRANSIT, ARRIVED
- `get_with_details(order_id, with_for_update?) -> Order | None`
- `search_orders(skip, limit, statuses?, payment_methods?, courier_id?, client_id?, ...)` -- универсальный поиск
- `update_status(order_id, new_status) -> Order | None`

**OrderItemRepository**:

- `get_by_order_and_product(order_id, product_id)`
- `delete_by_order_and_product(order_id, product_id)`
- `update_quantity(order_item_id, new_quantity)`

### Services: BaseOrderService

Наследует `BaseService[Order, OrderCreate, BaseOrderUnitOfWork]`. Требует `CatalogService` в конструкторе.

- `create_order(client_id, dto: OrderCreate) -> Order` -- Checkout: цены, проверка тары, авто-оприходование (INITIAL_BALANCE из VIRTUAL_VENDOR), сохранение snapshot цен
- `create_warehouse_sale(dto: WarehouseSaleCreate, client_id: UUID | None, created_by_id: UUID) -> Order` -- продажа со склада (WAREHOUSE_PICKUP); если client_id=None — используется WALKIN_USER_ID
- `complete_pickup(order_id, completed_by_id) -> Order` -- NEW → PICKUP_COMPLETED, создает WAREHOUSE_SALE + WAREHOUSE_TARA_RETURN + финансовые проводки
- `get_order_with_details(order_id, requesting_user_id?) -> Order` -- глубокая загрузка с IDOR-проверкой
- `add_product_to_order(order_id, product_id, quantity, requesting_user_id?) -> Order`
- `remove_product_from_order(order_id, product_id, requesting_user_id?) -> Order`
- `assign_courier(order_id, courier_id) -> Order`
- `update_status(order_id, new_status, actual_items?, requesting_user_id?) -> Order`
- `search_orders(skip, limit, statuses?, payment_methods?, courier_id?, client_id?, client_inventory_id?, sale_type: str | None, date_from?, date_to?, min_amount?, max_amount?) -> list[Order]` -- **ВНИМАНИЕ**: `sale_type` типизирован как `str | None`, а не `SaleType | None` (несоответствие типа)
- `get_client_history(client_id, skip, limit) -> Sequence[Order]`
- `get_courier_tasks(courier_id) -> Sequence[Order]`
- `check_tara_availability(dto: TaraCheckRequest) -> dict` -- возвращает `{"can_order": bool, "shortages": list}` (не типизированный DTO)
- `_ensure_status_transition_allowed(order, new_status)` -- валидация FSM (classmethod)
- `_get_allowed_statuses(sale_type, current_status) -> list[OrderStatus]` -- classmethod
- `_create_stock_transfer(from_id, to_id, transfer_type, items, created_by_id, accepted_by_id?, order_id?, reason?) -> StockTransfer` -- вспомогательный: создаёт StockTransfer + StockTransferItem + StockTransaction за один вызов
- `_build_returnable_items(order_items) -> list[dict]` -- staticmethod; агрегирует тару (CONTAINER) по доставленной воде
- `_handle_order_fulfillment(order, actual_items_dto?)` -- создаёт все складские и финансовые проводки при DELIVERED
- `_handle_warehouse_pickup(order, completed_by_id)` -- создаёт все складские и финансовые проводки при PICKUP_COMPLETED
- `_process_financial_settlement(order)` -- финансовое закрытие доставки (Revenue→Client, Client→Courier/Card)
- `_process_pickup_settlement(order)` -- финансовое закрытие самовывоза (Revenue→Client, Client→Cash)

### UoW: BaseOrderUnitOfWork

Repositories: orders, order_items, users, inventories, transfers (StockTransferRepository), transfer_items (StockTransferItemRepository), transactions (StockTransactionRepository), accounts (AccountRepository), financial_transactions (FinancialTransactionRepository)

**Note:** `transactions` = StockTransactionRepository (inventory ledger), `financial_transactions` = TransactionRepository (financial ledger). Both live in `src/modules/orders/uow.py`.

### Exceptions

- `OrderNotFoundError` (404), `InvalidOrderStatusError` (409), `OrderAccessDeniedError` (403)
- `EmptyCartError` (400) -- наследует `BadRequestError`, **не** `ConflictError`
- `ProductsUnavailableError` (409), `CourierAssignmentError` (409)
- `InsufficientTaraError` (409), `ClientInventoryNotFoundError` (404)
- `DeliveryQuantityExceededError` (409), `CannotRemoveLastItemError` (409), `InvalidPickupOperationError` (409)
- `CatalogServiceUnavailableError` (503)

---

## 5. Модуль INVENTORY

### Models

**Inventory**: user_id (FK RESTRICT), type (Enum InventoryType), name

- Constraint: UNIQUE(user_id, COURIER, is_active=true) -- один активный транспорт на курьера

**StockTransfer** (Накладная): from_id, to_id, created_by_id, accepted_by_id, order_id, reason, route_sheet_id, type, status = DRAFT

- Constraint: CK from_id != to_id, UNIQUE(id, from_id, to_id)

**StockTransferItem** (Строка накладной): transfer_id (CASCADE), product_id (RESTRICT), quantity (> 0)

**Balance** (Материализованные остатки): inventory_id (CASCADE), product_id (CASCADE), quantity

- Constraint: UNIQUE(inventory_id, product_id) `uq_inventory_product_balance`
- Constraint: CK `quantity >= 0` (`ck_inventory_balances_quantity_non_negative`) — объявлен в ORM-модели; **отсутствует в первоначальной миграции** — требует отдельного ALTER TABLE
- Обновляется ТОЛЬКО триггером БД

**StockTransaction** (Строгий леджер): product_id, transfer_id, from_id, to_id, quantity (> 0)

- Composite FK(transfer_id, from_id, to_id) -> stock_transfers(id, from_id, to_id) ondelete=CASCADE (`fk_stock_transaction_strict_route`)
- from_id и to_id также имеют отдельные FK на inventories ondelete=RESTRICT
- Append-only (UPDATE/DELETE запрещены триггером)

### Enums

- **InventoryType**: WAREHOUSE, COURIER, CLIENT, VIRTUAL_LOSS, VIRTUAL_VENDOR
- **TransferType**: COURIER_LOAD, COURIER_RETURN, CLIENT_DELIVERY, CLIENT_RETURN, LOSS_WRITE_OFF, INVENTORY_FINDING, INITIAL_BALANCE, WAREHOUSE_SALE, WAREHOUSE_TARA_RETURN
- **TransferStatus**: DRAFT, COMPLETED, CANCELLED

### Valid Routes (маршруты для TransferType)

```
COURIER_LOAD:         WAREHOUSE -> COURIER
COURIER_RETURN:       COURIER -> WAREHOUSE
CLIENT_DELIVERY:      COURIER -> CLIENT
CLIENT_RETURN:        CLIENT -> COURIER
LOSS_WRITE_OFF:       WAREHOUSE|COURIER|CLIENT -> VIRTUAL_LOSS
INVENTORY_FINDING:    VIRTUAL_VENDOR -> WAREHOUSE|COURIER
INITIAL_BALANCE:      VIRTUAL_VENDOR -> CLIENT|WAREHOUSE|COURIER
WAREHOUSE_SALE:       WAREHOUSE -> CLIENT
WAREHOUSE_TARA_RETURN: CLIENT -> WAREHOUSE
```

### UoW: InventoryUnitOfWork

Repositories: inventories, transfers, transfer_items, transactions (StockTransactionRepository), accounts (AccountRepository), financial_transactions (FinancialTransactionRepository)

### Services

**TransportService**: CRUD для машин курьеров (Inventory type=COURIER). Методы: `create_transport`, `get_transports`, `get_transport_with_balances`, `update_transport`, `delete_transport`. `update_transport` защищает от `CourierAlreadyAssignedError`.

**WarehouseService**: CRUD для складов (Inventory type=WAREHOUSE). Методы: `create_warehouse`, `get_warehouses`, `get_warehouse_with_balances`, `get_warehouses_with_balances`.

**StockTransferService**: `create_transfer(created_by_id, schema: CreateTransferRequest) -> StockTransfer` -- единый метод создания и проведения накладной (single-step COMPLETED); автоподстановка виртуальных складов; проверка маршрутов и остатков. `search_transfers(...)`.

**CapitalizeTaraService**: `capitalize_tara(dto: CapitalizeTaraRequest, created_by_id) -> dict` -- оприходование тары администратором (без лимитов). `capitalize_deficit(dto: CapitalizeDeficitRequest, client_id) -> dict` -- оприходование дефицита клиентом (с защитой от фрода).

**ShiftService**: `close_shift(request: CloseShiftRequest) -> bool` -- 1) сверка остатков (InventoryReconciliationError при расхождении); 2) COURIER_RETURN → главный склад; 3) инкассация (Courier Account → System Cash); 4) деактивация инвентаря курьера.

### Exceptions

- `VirtualInventoryConfigurationError` (500) -- системный виртуальный склад не создан при инициализации
- `InventoryNotFoundError` (404), `TransferNotFoundError` (404)
- `RouteLoopError` (400), `EmptyTransferError` (422), `InvalidQuantityError` (422)
- `InsufficientStockError` (409), `InvalidTransferStatusError` (409), `TransferTypeMismatchError` (409)
- `InventoryTypeMismatchError` (409), `ProductMismatchInTransitError` (409)
- `CourierAlreadyAssignedError` (409), `CourierRouteMismatchError` (409)
- `StrictLedgerViolationError` (403), `ReversalNotAllowedError` (403)
- `TaraCapitalizationLimitExceededError` (409)
- `InventoryReconciliationError` (409) -- рассинхрон остатков при закрытии смены; содержит `product_id`, `system_quantity`, `returned_quantity`

---

## 6. Модуль FINANCES

### Models

**Account**: user_id (FK RESTRICT), type (Enum AccountType), name, balance (BIGINT) = 0

- Balance обновляется ТОЛЬКО триггером БД

**Transaction** (Финансовый леджер): from_id, to_id, order_id, verified_by_id, amount (> 0), status = PENDING, reason

- Append-only (DELETE запрещен, UPDATE ограничен триггером)
- Constraint: CK amount > 0, CK from_id != to_id

### Enums

- **AccountType**: REVENUE, CASH, CARD, BANK, DISCOUNT, CLIENT, COURIER
- **TransactionStatus**: PENDING, COMPLETED, REJECTED

### UoW: FinancesUnitOfWork

Repositories: accounts (AccountRepository), transactions (TransactionRepository)

### Repositories

**AccountRepository**:

- `create(user_id, account_type, name) -> Account`
- `create_client_account(client_id, client_name) -> Account`
- `create_courier_account(courier_id, courier_name) -> Account`
- `create_system_accounts(system_user_id) -> list[Account]` -- REVENUE, CASH, CARD, BANK (4 системных счёта)
- `get_user_account_by_type(user_id, account_type) -> Account | None`
- `get_system_account(account_type) -> Account | None`
- `get_system_revenue_account() -> Account | None`
- `get_system_cash_account() -> Account | None`
- `get_system_card_account() -> Account | None`
- `get_system_bank_account() -> Account | None`
- `get_courier_account(courier_id) -> Account | None`
- `get_client_account(client_id) -> Account | None`

**TransactionRepository**:

- `get_for_update(transaction_id) -> Transaction | None`
- `change_status(transaction_id, new_status, verified_by_id?) -> Transaction | None`
- `get_by_order(order_id) -> Sequence[Transaction]`
- `get_account_history(account_id, limit, offset) -> Sequence[Transaction]`

### Exceptions

- `AccountNotFoundError`, `TransactionNotFoundError`
- `InsufficientFundsError`, `InvalidTransactionAmountError`
- `SelfTransferError`, `InvalidTransactionStatusError`

---

## Сводная таблица моделей

| Модель            | Модуль    | Ключевые поля                                          | FK Strategy        |
| ----------------- | --------- | ------------------------------------------------------ | ------------------ |
| User              | users     | username, role                                         | --                 |
| Identity          | users     | provider, provider_identity_id, password_hash          | CASCADE к User     |
| Product           | catalog   | type, name, price, attributes, returnable_item_id      | RESTRICT self-ref  |
| Order             | orders    | client_id, courier_id, status, total_amount, sale_type | RESTRICT/SET NULL  |
| OrderItem         | orders    | product_id, quantity, unit_price                       | CASCADE к Order    |
| Inventory         | inventory | user_id, type, name                                    | RESTRICT к User    |
| StockTransfer     | inventory | from_id, to_id, type, status, order_id                 | RESTRICT           |
| StockTransferItem | inventory | transfer_id, product_id, quantity                      | CASCADE к Transfer |
| Balance           | inventory | inventory_id, product_id, quantity                     | CASCADE            |
| StockTransaction  | inventory | product_id, from_id, to_id, quantity                   | CASCADE (composite FK на transfer), RESTRICT (from/to на inventories) |
| Account           | finances  | user_id, type, balance                                 | RESTRICT к User    |
| Transaction       | finances  | from_id, to_id, amount, status, reason                 | RESTRICT           |

---

## Ключевые бизнес-правила

1. **Тара (Tara Exchange)**: вода требует пустую бутыль (returnable_item_id)
2. **Заказы**: snapshot цен, проверка тары, авто-оприходование дефицита
3. **Накладные**: State Machine с валидными маршрутами, строгий Event Sourcing
4. **Смена курьера**: 3-этапная (сверка -> возврат -> инкассация)
5. **Виртуальные склады**: VIRTUAL_VENDOR (источник) и VIRTUAL_LOSS (яма)
6. **Балансы**: материализованные в Balance/Account, обновляются триггерами
7. **WALKIN**: системный пользователь для анонимных покупок (не может входить)
