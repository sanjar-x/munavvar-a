# API Layer - Полная документация

## 1. Структура и Архитектура

### 1.1 Общая организация маршрутов (Routers Organization)

API разделена на 4 основных роутера, встроенных на префиксе `/api/v1`:

| Роутер         | Префикс     | Назначение                   | Роли пользователей                      |
| -------------- | ----------- | ---------------------------- | --------------------------------------- |
| auth_router    | /auth       | Аутентификация и регистрация | Public, All                             |
| backoffice     | /backoffice | Админ-панель и управление    | ADMIN, ACCOUNTANT, STOREKEEPER, CASHIER |
| client_router  | /client     | Клиентский API (B2C/B2B)     | CLIENT_B2C, CLIENT_B2B                  |
| courier_router | /courier    | Курьерский API               | COURIER                                 |

**Путь к конфигурации:** `src/api/v1/__init__.py`

---

## 2. Middleware Stack и порядок выполнения

```
REQUEST
  |
[Слой 1 - RequestIDMiddleware]  <-- САМЫЙ ВНЕШНИЙ (выполняется ПЕРВЫМ)
  - Очистка контекста structlog (clear_contextvars)
  - Генерация или получение X-Request-ID
  - Сохранение request_id в контексте проекта
  - Биндинг в structlog.contextvars
  - Добавление заголовка X-Request-ID к ответу

  |
[Слой 2 - AccessLoggerMiddleware]
  - Извлечение IP клиента (X-Forwarded-For или client.host)
  - Биндинг ip, method, path в structlog
  - Исключение путей: /health, /metrics, /docs, /openapi.json, /favicon.ico
  - Замер времени выполнения запроса (perf_counter)
  - Логирование HTTP Access с статусом и duration_ms
  - Добавление заголовка x-process-time к ответу

  |
[Слой 3 - CORSMiddleware]
  - allow_origins: из settings.CORS_ORIGINS
  - allow_credentials: true
  - allow_methods: "*"
  - allow_headers: "*"

  |
МАРШРУТИЗАЦИЯ И ОБРАБОТКА ЗАПРОСА
  |
EXCEPTION HANDLERS
  |
RESPONSE
```

### RequestIDMiddleware

**Файл:** `src/api/middlewares/request_id.py`

- Тип: ASGI Middleware (высокопроизводительный)
- На самом внешнем слое (выполняется первым)

### AccessLoggerMiddleware

**Файл:** `src/api/middlewares/logger.py`

- Тип: ASGI Middleware (высокопроизводительный гибридный)
- Динамический выбор лог-уровня: ERROR >= 500, WARNING 400-499, INFO < 400

---

## 3. Exception Handlers

**Файл:** `src/api/exceptions/handlers.py`

### Иерархия исключений

```
Exception
  +-- AppException (базовый класс для всех бизнес-ошибок)
  |   +-- NotFoundError (404)
  |   +-- BadRequestError (400)
  |   +-- UnauthorizedError (401)
  |   +-- ForbiddenError (403)
  |   +-- ConflictError (409)
  |   +-- UnprocessableEntityError (422)
  |   +-- ServiceUnavailableError (503)
  |
  +-- RequestValidationError (422 от Pydantic)
  +-- StarletteHTTPException (стандартные HTTP ошибки)
  +-- Exception (все остальные необработанные)
```

### Зарегистрированные обработчики

| Исключение             | Статус        | JSON Структура                                                                             |
| ---------------------- | ------------- | ------------------------------------------------------------------------------------------ |
| AppException           | Из исключения | `{ "error": { "code", "message", "details" } }`                                            |
| RequestValidationError | 422           | `{ "error": { "code": "VALIDATION_ERROR", "details": [{ "field", "message", "type" }] } }` |
| StarletteHTTPException | Из исключения | `{ "error": { "code": "HTTP_ERROR_{status}", "message", "details" } }`                     |
| Exception              | 500           | `{ "error": { "code": "INTERNAL_SERVER_ERROR", "message", "details" } }`                   |

---

## 4. Аутентификация и Авторизация

### JWT и OAuth2 Конфигурация

**Файл:** `src/modules/auth/dependencies.py`

#### Двухуровневая валидация

**Уровень 1: get_token_payload (FAST PATH - БЕЗ БД)**

- Декодирование JWT
- Проверка наличия user_id ("sub")
- Проверка наличия требуемых scopes в токене

**Уровень 2: get_current_user (SLOW PATH - С БД)**

- Получение user_id из payload
- Запрос пользователя из БД
- Проверка is_active

#### OAuth2 Scheme

```python
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    scopes=swagger_scopes
)
```

### Система разрешений (Scopes/Permissions)

**Файл:** `src/core/security/permissions.py`

#### Scopes (полный список)

| Домен     | Scopes                                                                                              |
| --------- | --------------------------------------------------------------------------------------------------- |
| Users     | users:read, users:write, profile:read, profile:write                                                |
| Catalog   | catalog:read, catalog:write                                                                         |
| Orders    | orders:read, orders:create, orders:edit, orders:deliver, orders:cancel                              |
| Inventory | inventory:read, inventory:write, logistics:supply, logistics:transfer, routes:read, transports:read |
| Finances  | finances:read, finances:write, payments:create, bills:read                                          |
| System    | settings:read, settings:write, system:exec                                                          |

#### Маппинг ролей к scopes

Все роли (кроме SYSTEM) наследуют `BASE_SCOPES = [profile:read, profile:write, catalog:read]`.

| Роль        | Дополнительные scopes (сверх BASE_SCOPES)                                                                                              |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| SYSTEM      | system:exec (только этот, BASE_SCOPES не включены)                                                                                     |
| ADMIN       | users:read/write, catalog:write, orders:read/edit/cancel, inventory:read/write, transports:read, logistics:supply/transfer, routes:read, finances:read/write, settings:read/write |
| ACCOUNTANT  | users:read, finances:read/write, bills:read                                                                                            |
| STOREKEEPER | transports:read, inventory:read/write, logistics:supply/transfer                                                                       |
| CASHIER     | orders:read/create, inventory:read, payments:create                                                                                    |
| COURIER     | orders:read/deliver, routes:read, payments:create                                                                                      |
| CLIENT_B2C  | orders:read/create/cancel                                                                                                              |
| CLIENT_B2B  | orders:read/create/cancel, bills:read                                                                                                  |

**Примечания:**
- ADMIN не имеет `orders:create`, `bills:read`, `payments:create` — они не нужны: создание заказов от лица клиента идёт через `ORDERS_EDIT`.
- ADMIN не имеет `system:exec` — это исключительно технический scope для фоновых задач.

---

## 5. Полный каталог маршрутов (Endpoints)

### 5.1 AUTH ROUTER `/api/v1/auth`

| Метод | Путь      | Функция       | Статус | Auth                                      |
| ----- | --------- | ------------- | ------ | ----------------------------------------- |
| POST  | /register | register_user | 201    | None (Public) — тело: `UserCreate` schema |
| POST  | /login    | login         | 200    | OAuth2 PasswordRequestForm (staff)        |

### 5.2 BACKOFFICE ROUTER `/api/v1/backoffice`

#### Profile `/backoffice/profile`

| Метод | Путь | Функция | Статус | Scopes       |
| ----- | ---- | ------- | ------ | ------------ |
| GET   | /me  | get_me  | 200    | PROFILE_READ |

#### Users `/backoffice/users`

| Метод  | Путь             | Функция         | Статус | Scopes      |
| ------ | ---------------- | --------------- | ------ | ----------- |
| POST   | /                | create_user     | 201    | USERS_WRITE |
| GET    | /                | get_staff_users | 200    | USERS_READ  |
| GET    | /{id}            | get_user        | 200    | USERS_READ  |
| PATCH  | /{user_id}       | update_user     | 200    | USERS_WRITE |
| POST   | /{user_id}/block | block_user      | 204    | USERS_WRITE |
| DELETE | /{user_id}       | delete_user     | 204    | USERS_WRITE |

#### Clients `/backoffice/clients`

| Метод | Путь                              | Функция                 | Статус | Scopes      |
| ----- | --------------------------------- | ----------------------- | ------ | ----------- |
| POST  | /onboard                          | onboard_client          | 201    | USERS_WRITE |
| POST  | /                                 | create_client           | 201    | USERS_WRITE |
| POST  | /{client_id}/inventories          | create_client_inventory | 201    | USERS_WRITE |
| GET   | /                                 | get_clients             | 200    | USERS_WRITE |
| GET   | /{client_id}                      | get_client              | 200    | USERS_WRITE |
| PATCH | /{client_id}                      | update_client           | 200    | USERS_WRITE |
| POST  | /{client_id}/inventory/capitalize | capitalize_client_tara  | 200    | USERS_WRITE |
| POST  | /{user_id}/block                  | block_user              | 204    | USERS_WRITE |

#### Couriers `/backoffice/couriers`

| Метод | Путь                | Функция        | Статус | Scopes      |
| ----- | ------------------- | -------------- | ------ | ----------- |
| POST  | /                   | create_courier | 201    | USERS_WRITE |
| GET   | /                   | get_couriers   | 200    | USERS_READ  |
| GET   | /{courier_id}       | get_courier    | 200    | USERS_READ  |
| PATCH | /{courier_id}       | update_courier | 200    | USERS_WRITE |
| POST  | /{courier_id}/block | block_courier  | 204    | USERS_WRITE |

#### Orders `/backoffice/orders`

| Метод  | Путь                            | Функция                   | Статус | Scopes      |
| ------ | ------------------------------- | ------------------------- | ------ | ----------- |
| GET    | /                               | search_orders             | 200    | ORDERS_READ |
| POST   | /check-tara                     | check_tara_availability   | 200    | ORDERS_READ |
| POST   | /                               | create_order              | 201    | ORDERS_EDIT |
| POST   | /warehouse-sale                 | create_warehouse_sale     | 201    | ORDERS_EDIT |
| POST   | /warehouse-sale/capitalize-tara | capitalize_tara_for_sale  | 201    | ORDERS_EDIT |
| PATCH  | /{orderId}/complete-pickup      | complete_pickup           | 200    | ORDERS_EDIT |
| GET    | /{orderId}                      | get_order_details         | 200    | ORDERS_READ |
| POST   | /{orderId}/items                | add_product_to_order      | 200    | ORDERS_EDIT |
| DELETE | /{orderId}/items/{productId}    | remove_product_from_order | 200    | ORDERS_EDIT |
| PATCH  | /{orderId}/assign               | assign_courier            | 200    | ORDERS_EDIT |
| PATCH  | /{orderId}/status               | update_order_status       | 200    | ORDERS_EDIT |
| PATCH  | /{orderId}/in-transit           | mark_order_in_transit     | 200    | ORDERS_EDIT |
| PATCH  | /{orderId}/arrived              | mark_order_arrived        | 200    | ORDERS_EDIT |
| PATCH  | /{orderId}/delivered            | mark_order_delivered      | 200    | ORDERS_EDIT |
| GET    | /client/{clientId}/history      | get_client_history        | 200    | ORDERS_READ |
| GET    | /courier/{courierId}/tasks      | get_courier_tasks         | 200    | ORDERS_READ |

`add_product_to_order` и `remove_product_from_order` не принимают `requesting_user_id` (администратор не ограничен по владению заказом).

#### Catalog `/backoffice/catalog`

| Метод  | Путь          | Функция         | Статус | Scopes        |
| ------ | ------------- | --------------- | ------ | ------------- |
| GET    | /             | get_catalog     | 200    | CATALOG_READ  |
| POST   | /             | create_product  | 201    | CATALOG_WRITE |
| PATCH  | /{product_id} | update_product  | 200    | CATALOG_WRITE |
| DELETE | /{product_id} | archive_product | 204    | CATALOG_WRITE |

#### Warehouses `/backoffice/warehouses`

| Метод | Путь            | Функция                      | Статус | Scopes          |
| ----- | --------------- | ---------------------------- | ------ | --------------- |
| GET   | /               | get_warehouses_with_balances | 200    | INVENTORY_READ  |
| POST  | /               | create_warehouse             | 201    | INVENTORY_WRITE |
| GET   | /{warehouse_id} | get_warehouse_detail         | 200    | INVENTORY_READ  |

#### Transports `/backoffice/transports`

| Метод  | Путь              | Функция              | Статус | Scopes          |
| ------ | ----------------- | -------------------- | ------ | --------------- |
| GET    | /                 | get_transports       | 200    | TRANSPORTS_READ |
| POST   | /                 | create_transport     | 201    | INVENTORY_WRITE |
| GET    | /{transport_id}   | get_transport_detail | 200    | TRANSPORTS_READ |
| PATCH  | /{transport_id}   | update_transport     | 200    | INVENTORY_WRITE |
| DELETE | /{transport_id}   | delete_transport     | 204    | INVENTORY_WRITE |

GET-эндпоинты используют `TRANSPORTS_READ`, write-операции (POST/PATCH/DELETE) — `INVENTORY_WRITE`.

#### Transfers `/backoffice/transfers`

| Метод | Путь | Функция         | Статус | Scopes             |
| ----- | ---- | --------------- | ------ | ------------------ |
| GET   | /    | get_transfers   | 200    | LOGISTICS_TRANSFER |
| POST  | /    | create_transfer | 201    | LOGISTICS_TRANSFER |

#### Shifts `/backoffice/shifts`

| Метод | Путь   | Функция     | Статус | Scopes          |
| ----- | ------ | ----------- | ------ | --------------- |
| POST  | /close | close_shift | 200    | INVENTORY_WRITE |

#### System `/backoffice/system`

| Метод | Путь  | Функция       | Статус | Scopes      |
| ----- | ----- | ------------- | ------ | ----------- |
| POST  | /seed | seed_database | 200    | USERS_WRITE |

### 5.3 CLIENT ROUTER `/api/v1/client`

| Метод  | Путь                                  | Функция                   | Статус | Scopes        |
| ------ | ------------------------------------- | ------------------------- | ------ | ------------- |
| POST   | /login                                | login                     | 200    | None (Public) |
| GET    | /profile/me                           | get_me                    | 200    | PROFILE_READ  |
| GET    | /catalog                              | get_catalog               | 200    | CATALOG_READ  |
| POST   | /orders/check-tara                    | check_tara_availability   | 200    | ORDERS_READ   |
| POST   | /orders                               | create_order              | 201    | ORDERS_CREATE |
| GET    | /orders/{order_id}                    | get_order_details         | 200    | ORDERS_READ   |
| POST   | /orders/{order_id}/items              | add_product_to_order      | 200    | ORDERS_CREATE |
| DELETE | /orders/{order_id}/items/{product_id} | remove_product_from_order | 200    | ORDERS_CREATE |
| GET    | /orders/history                       | get_tasks                 | 200    | ORDERS_READ   |

**Важно:** `create_order`, `add_product_to_order` и `remove_product_from_order` используют `ORDERS_CREATE` (не `ORDERS_EDIT`). Клиентский `add/remove` передают `requesting_user_id=client.id` в сервис — проверка владения заказом на уровне сервиса.

**Client login:** принимает только `phone: str` query-параметр (без пароля), вызывает `auth_service.client_login(phone)` — упрощённый вход для клиентов.

**Note:** Client inventory router (`/client/inventory`) пуст — эндпоинт `/capitalize-deficit` удалён из соображений защиты от фрода. Авто-оприходование дефицита тары происходит внутри транзакции создания заказа через флаг `capitalize_missing_tara: true` в `POST /orders`.

### 5.4 COURIER ROUTER `/api/v1/courier`

| Метод | Путь                          | Функция               | Статус | Scopes         | OpenAPI |
| ----- | ----------------------------- | --------------------- | ------ | -------------- | ------- |
| POST  | /login                        | login                 | 200    | None (Public)  | видим   |
| GET   | /profile/me                   | get_me                | 200    | PROFILE_READ   | видим   |
| GET   | /catalog                      | get_catalog           | 200    | CATALOG_READ   | видим   |
| GET   | /orders                       | get_tasks             | 200    | ORDERS_READ    | видим   |
| GET   | /orders/tasks                 | get_tasks (alias)     | 200    | ORDERS_READ    | скрыт   |
| GET   | /orders/{order_id}            | get_order_details     | 200    | ORDERS_READ    | видим   |
| PATCH | /orders/{order_id}/in-transit | mark_order_in_transit | 200    | ORDERS_DELIVER | видим   |
| PATCH | /orders/{order_id}/arrived    | mark_order_arrived    | 200    | ORDERS_DELIVER | видим   |
| PATCH | /orders/{order_id}/delivered  | deliver_order         | 200    | ORDERS_DELIVER | видим   |
| POST  | /orders/{order_id}/deliver    | deliver_order_legacy  | 200    | ORDERS_DELIVER | скрыт   |
| PATCH | /orders/{order_id}/status     | update_order_status   | 200    | ORDERS_DELIVER | видим   |

**Courier login:** принимает `LocalLogin` (phone + password), вызывает `auth_service.courier_login(data)`.

Все курьерские status-мутации передают `requesting_user_id=courier.id` — сервис проверяет, что курьер работает со своим заказом.

---

## 6. Файловая структура API слоя

```
src/api/
+-- server.py                          # Конфигурация FastAPI, middlewares, handlers
+-- exceptions/
|   +-- handlers.py                    # Все exception handlers
+-- middlewares/
|   +-- logger.py                      # AccessLoggerMiddleware
|   +-- request_id.py                  # RequestIDMiddleware
+-- v1/
    +-- __init__.py                    # api_v1_router
    +-- auth/
    |   +-- login.py                   # Staff login
    |   +-- register.py                # Client signup
    +-- backoffice/
    |   +-- profile.py
    |   +-- users.py
    |   +-- clients.py
    |   +-- couriers.py
    |   +-- orders.py
    |   +-- catalog.py
    |   +-- warehouses.py
    |   +-- transport.py
    |   +-- transfers.py
    |   +-- shifts.py
    |   +-- system.py
    |   +-- finances.py                # (пуст)
    +-- client/
    |   +-- login.py
    |   +-- profile.py
    |   +-- catalog.py
    |   +-- orders.py
    |   +-- inventory.py               # (пуст)
    +-- courier/
        +-- login.py
        +-- profile.py
        +-- catalog.py
        +-- orders.py
```

---

## 7. Особенности

- `/courier/orders/tasks` -- legacy alias для `/courier/orders`, скрыт из OpenAPI schema (`include_in_schema=False`)
- `/courier/orders/{order_id}/deliver` (POST) -- legacy alias для PATCH `/delivered`, скрыт из OpenAPI schema
- Pagination: skip/limit (большинство list-эндпоинтов) и page/size (couriers, transports, transfers)
- Все scopes жёстко привязаны к ролям в `ROLE_SCOPES` (`src/core/security/permissions.py`)
- `GET /health` публичный (не требует авторизации)
- `backoffice/__init__.py` дважды регистрирует `system_router` (дублирующий `include_router` — существующий баг в коде)
- Клиентский login (`POST /client/login`) принимает только `phone` query-параметром (без пароля), курьерский (`POST /courier/login`) принимает тело `LocalLogin` (phone + password)
- `GET /backoffice/users` возвращает `UserResponseList` (обёртка с пагинацией), а не `list[UserResponse]`
- `GET /backoffice/couriers` и `GET /backoffice/clients` аналогично возвращают `CouriersResponse` / `ClientsResponse`
