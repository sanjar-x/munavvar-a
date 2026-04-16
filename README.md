# HOD — Home & Office Delivery

B2B/B2C платформа управления доставкой бутилированной воды: от приёма заказа до доставки курьером, перемещения товара между складами и финансовой сверки. Построена как DDD модульный монолит на Python/FastAPI/PostgreSQL.

**Ключевой принцип:** двойная бухгалтерия (складской леджер + финансовый леджер) — каждое движение товара и каждая денежная операция прослеживается через двойную запись. Целостность леджеров обеспечивается триггерами PostgreSQL на уровне БД, а не приложения.

---

## Бизнес-домен

### Что делает система

1. **Управление заказами** — полный цикл от корзины до доставки
   - Два типа продаж: доставка курьером (`DELIVERY`) и самовывоз со склада (`WAREHOUSE_PICKUP`)
   - Три способа оплаты: наличные (`CASH`), карта/QR (`CARD`), по договору (`CONTRACT`)
   - Конечный автомат статусов: `NEW` → `ASSIGNED` → `IN_TRANSIT` → `ARRIVED` → `DELIVERED`
   - Самовывоз: `NEW` → `PICKUP_COMPLETED`
   - Отмена: любой статус → `CANCELLED` (с откатом квот по договору)
   - Автоматическая фиксация цен на момент заказа (заморозка)

2. **Складской учёт** — движение товара между точками хранения
   - 5 типов инвентаря: `WAREHOUSE`, `COURIER`, `CLIENT`, `VIRTUAL_VENDOR`, `VIRTUAL_LOSS`
   - 9 типов перемещений с валидацией маршрутов (кто откуда куда может перемещать)
   - Append-only леджер: `StockTransaction` — неизменяемые записи, DELETE/UPDATE заблокированы триггером
   - Материализованные остатки: таблица `InventoryBalance` обновляется триггером атомарно

3. **Финансовый учёт** — двойная запись по всем денежным операциям
   - 9 типов счетов: `REVENUE`, `CASH`, `CARD`, `BANK`, `DISCOUNT`, `CLIENT`, `COURIER`, `EXPENSE`, `ADMIN`
   - Каждая транзакция — перевод с одного счёта на другой (double-entry)
   - Append-only леджер: `Transaction` — неизменяемые записи
   - Баланс счёта обновляется триггером с row-level locking (`FOR UPDATE`)
   - Статусы: `PENDING` → `COMPLETED` / `REJECTED` (верификация бухгалтером)

4. **Система оборотной тары** — отслеживание возвратных бутылей
   - Продукт может ссылаться на возвратную тару (`returnable_item_id`)
   - При создании заказа: автоматическая проверка наличия пустых бутылей у клиента
   - Автооприходование (`INITIAL_BALANCE` из `VIRTUAL_VENDOR`) при дефиците
   - Защита от мошенничества: оприходуется ровно столько, сколько нужно для текущего заказа

5. **Договоры (B2B)** — управление контрактами с юридическими лицами
   - Жизненный цикл: `DRAFT` → `ACTIVE` → `SUSPENDED` / `TERMINATED` / `EXPIRED`
   - Индивидуальный прайс-лист по договору с квотами на количество (`ContractPriceItem`)
   - Автоматический контроль квот: при создании заказа `quantity_used` увеличивается, при отмене — уменьшается
   - Счета-фактуры (`Invoice`) с биллинговыми циклами и статусами оплаты
   - Акт сверки (`Reconciliation`) — сопоставление заказов и платежей за период
   - Append-only аудит-лог переходов статуса (`ContractStatusLog`)
   - Дополнительные соглашения (`ContractAmendment`) для формализации изменений условий
   - Partial unique index: один активный договор на клиента

6. **Ролевая модель** — 8 ролей с granular permissions через JWT scopes
   - `ADMIN`, `ACCOUNTANT`, `STOREKEEPER`, `CASHIER` — бэкофис
   - `COURIER` — мобильное приложение курьера
   - `CLIENT_B2C`, `CLIENT_B2B` — клиентский интерфейс
   - `SYSTEM` — системные операции (виртуальные склады, служебные счета)

### Типичные потоки

**Доставка заказа:**

```
Клиент создаёт заказ → Проверка тары → Автооприходование дефицита
→ Админ назначает курьера → Курьер загружает товар (WAREHOUSE → COURIER)
→ Курьер в пути → Курьер на месте → Доставлено (COURIER → CLIENT)
→ Клиент возвращает пустые бутыли (CLIENT → COURIER)
→ Курьер сдаёт оплату → Бухгалтер верифицирует транзакцию
```

**Самовывоз:**

```
Клиент приходит на склад → Возврат тары (CLIENT → WAREHOUSE)
→ Создание заказа → Продажа со склада (WAREHOUSE → CLIENT)
→ Оплата на месте → Верификация
```

**Заказ по договору (B2B):**

```
Админ создаёт договор (DRAFT) → Активация (ACTIVE)
→ Клиент создаёт заказ с payment_method=CONTRACT
→ Проверка квот по прайс-листу → Резервирование quantity_used
→ Доставка → Формирование счёта-фактуры за период
→ Выставление → Оплата → Акт сверки
```

---

## Технологический стек

| Слой              | Технологии                                 |
| ----------------- | ------------------------------------------ |
| Runtime           | Python 3.14+, CPython                      |
| Web Framework     | FastAPI ≥0.132 (async, ASGI/Uvicorn)       |
| ORM               | SQLAlchemy ≥2.1 (async mode, asyncpg)      |
| База данных       | PostgreSQL 18 (триггеры, PL/pgSQL)         |
| Миграции          | Alembic                                    |
| Валидация         | Pydantic v2                                |
| Аутентификация    | JWT (PyJWT, HS256), Argon2/Bcrypt (pwdlib) |
| Логирование       | structlog (JSON в проде, консоль в dev)    |
| Пакетный менеджер | uv (Astral)                                |
| Линтер/форматтер  | Ruff ≥0.15 (line-length: 79)               |
| Тесты             | pytest + pytest-asyncio + httpx            |
| Деплой            | Railway (Dockerfile)                       |

---

## Архитектура

```
src/
  api/                    # HTTP-слой: роутеры, middleware, обработка ошибок
    v1/
      auth/               # Логин, регистрация (бэкофис)
      backoffice/         # Админка: полное управление всеми доменами
        dashboard/        # Аналитика: заказы, финансы, склад, курьеры
      client/             # Клиентский API: заказы, каталог, профиль, договоры
      courier/            # API курьера: задания, статусы доставки, профиль
  application/            # Оркестрация кросс-доменных процессов
    client/               # Онбординг клиента (User + Identity + Account + Inventory)
    courier/              # Онбординг курьера (User + Identity + Account + Transport)
    inventories/          # Склады, транспорт, перемещения, оприходование тары
    order/                # Создание заказов с автооприходованием
  modules/                # Доменные модули (DDD bounded contexts)
    auth/                 # Аутентификация
    catalog/              # Каталог продуктов (WATER, CONTAINER, EQUIPMENT)
    contracts/            # Договоры B2B, прайс-листы, счета-фактуры
    orders/               # Жизненный цикл заказа, FSM, логика тары
    inventory/            # Складской леджер, перемещения, остатки
    finances/             # Финансовый леджер, счета, транзакции
    users/                # Пользователи, роли, идентификации
  common/                 # Базовые абстракции: Repository, Service, UoW
  infrastructure/         # БД: engine, session, BaseModel, триггеры (SQL)
  core/                   # Конфигурация, безопасность, JWT, RBAC, логирование
```

### Слои и направление зависимостей

**API → Application → Modules → Common/Infrastructure**

| Слой             | Назначение                                                    |
| ---------------- | ------------------------------------------------------------- |
| `api/`           | HTTP-роутинг, валидация запросов, авторизация, сериализация   |
| `application/`   | Кросс-доменная оркестрация через составные UoW                |
| `modules/`       | Бизнес-логика одного домена, владеет своими моделями          |
| `common/`        | `BaseRepository`, `BaseService`, `IUnitOfWork`                |
| `infrastructure/`| SQLAlchemy engine/session, `BaseModel`, `BaseSQLAlchemyUoW`   |
| `core/`          | Конфигурация, JWT, RBAC, structlog, иерархия исключений       |

### Паттерны

- **Repository** — CRUD-обёртка над SQLAlchemy, generic по типу модели (`BaseRepository[ModelType]`)
- **Unit of Work** — транзакционная граница, композиция репозиториев на одной сессии
- **Service Layer** — бизнес-логика, возвращает domain model objects; сериализация на уровне роутера
- **CQRS-lite** — `queries.py` для read-only операций (отдельно от write-сервисов)
- **Domain Exceptions** — иерархия `AppException` с кодами ошибок и русскими сообщениями
- **Dependency Injection** — `Depends` цепочка: `get_{entity}_uow()` → `get_{entity}_service(uow)` → handler

### Целостность данных

| Механизм                                 | Что защищает                                                         |
| ---------------------------------------- | -------------------------------------------------------------------- |
| PG триггер `update_account_balances()`   | Атомарное обновление баланса счёта при INSERT/UPDATE транзакции      |
| PG триггер `update_inventory_balances()` | Атомарное обновление складских остатков при INSERT stock_transaction |
| Блокировка DELETE на леджерах            | Невозможно удалить записи из `transactions` и `stock_transactions`   |
| `ondelete="RESTRICT"`                    | Критические FK не допускают каскадного удаления                      |
| `lazy="raise"`                           | Защита от N+1 запросов на bulk-рисковых связях                       |
| `CheckConstraint`                        | Валидация на уровне БД (price ≥ 0, quantity > 0)                     |
| Partial unique index                     | Один активный договор на клиента                                     |
| Валидация маршрутов                      | Каждый тип перемещения имеет допустимые пары (from_type, to_type)    |

---

## Быстрый старт

### Предварительные требования

- Python ≥3.14
- [uv](https://docs.astral.sh/uv/) (пакетный менеджер)
- Docker + Docker Compose (для PostgreSQL)
- Make (опционально, для Makefile-команд)

### Установка и запуск

```bash
# 1. Установить зависимости
uv sync

# 2. Скопировать .env и заполнить
cp .env.example .env

# 3. Поднять PostgreSQL в Docker
docker compose -f deploy/compose.db.yml up -d

# 4. Применить миграции
make upgrade

# 5. Запустить dev-сервер (hot reload)
make dev
```

### Основные команды

```bash
make dev             # Dev-сервер (hot reload)
make test            # Все тесты
make lint            # Проверка линтером (без исправлений)
make format          # Линтер + форматтер (auto-fix)
make upgrade         # Применить миграции
make downgrade       # Откатить последнюю миграцию
make migrate m="msg" # Создать новую миграцию
make up              # Поднять Docker-контейнеры
make down            # Остановить Docker-контейнеры
```

### Переменные окружения

| Переменная           | Обязательная | Описание                           | По умолчанию |
| -------------------- | ------------ | ---------------------------------- | ------------ |
| `SECRET_KEY`         | ✅            | Ключ подписи JWT (≥32 символа)     | —            |
| `PGHOST`             | ✅            | Хост PostgreSQL                    | —            |
| `PGPORT`             | ✅            | Порт PostgreSQL                    | —            |
| `PGUSER`             | ✅            | Пользователь БД                   | —            |
| `PGPASSWORD`         | ✅            | Пароль БД                         | —            |
| `PGDATABASE`         | ✅            | Имя базы данных                   | —            |
| `ENVIRONMENT`        |              | `dev` / `test` / `prod`            | `dev`        |
| `DEBUG`              |              | SQL echo + console renderer        | `False`      |
| `ACCESS_TOKEN_EXPIRE_MINUTES` |     | Время жизни JWT (минуты)           | `10080` (7д) |
| `CORS_ORIGINS`       |              | Разрешённые origins через запятую  | `[]`         |
| `ADMIN_PHONE`        |              | Телефон начального администратора  | —            |
| `ADMIN_PASSWORD`     |              | Пароль начального администратора   | —            |

---

## API

Четыре аудитории, четыре набора эндпоинтов:

### `/api/v1/auth/` — Аутентификация (бэкофис)

| Метод  | Путь          | Описание            |
| ------ | ------------- | ------------------- |
| `POST` | `/login/`     | Логин сотрудника    |
| `POST` | `/register/`  | Регистрация         |

### `/api/v1/backoffice/` — Админка

Полное управление всеми доменами. Доступ для ролей: `ADMIN`, `ACCOUNTANT`, `STOREKEEPER`, `CASHIER`.

| Группа         | Prefix           | Операции                                                            |
| -------------- | ---------------- | ------------------------------------------------------------------- |
| Profile        | `/profile`       | Просмотр собственного профиля                                       |
| Users          | `/users`         | CRUD сотрудников, блокировка, идентификации                         |
| Clients        | `/clients`       | Онбординг клиентов (B2C/B2B), списки, блокировка                   |
| Couriers       | `/couriers`      | Онбординг курьеров, транспорт, блокировка                           |
| Catalog        | `/catalog`       | CRUD продуктов, цены, архивация                                     |
| Orders         | `/orders`        | Создание, FSM-переходы, назначение курьера, отмена                  |
| Contracts      | `/contracts`     | Договоры B2B: CRUD, прайс-листы, счета, акты сверки, доп.соглашения|
| Warehouses     | `/warehouses`    | CRUD складов                                                        |
| Inventories    | `/inventories`   | Просмотр остатков                                                   |
| Transfers      | `/transfers`     | Перемещения между складами                                          |
| Transports     | `/transports`    | Транспортные средства курьеров                                      |
| Finances       | `/finances`      | Счета, транзакции, верификация, dashboard                           |
| Dashboard      | `/dashboard`     | Аналитика: заказы, финансы, склад, курьеры                          |
| System         | `/system`        | Сидирование тестовых данных                                         |

### `/api/v1/client/` — Клиентский API

| Группа     | Prefix           | Операции                                                |
| ---------- | ---------------- | ------------------------------------------------------- |
| Auth       | `/login`         | Логин клиента                                           |
| Profile    | `/profile`       | Просмотр профиля                                        |
| Catalog    | `/catalog`       | Просмотр каталога                                       |
| Orders     | `/orders`        | Создание заказов, история, проверка тары, отмена         |
| Inventory  | `/inventory`     | Остатки тары клиента                                    |
| Finances   | `/finances`      | Финансовая информация                                   |
| Contracts  | —                | Просмотр своих договоров, прайс-листов, счетов-фактур   |

### `/api/v1/courier/` — API курьера

| Группа     | Prefix           | Операции                                                |
| ---------- | ---------------- | ------------------------------------------------------- |
| Auth       | `/login`         | Логин курьера                                           |
| Profile    | `/profile`       | Просмотр профиля                                        |
| Catalog    | `/catalog`       | Просмотр каталога                                       |
| Orders     | `/orders`        | Задания, FSM-переходы, доставка, возврат тары            |
| Inventory  | `/inventory`     | Остатки на транспорте                                   |
| Finances   | `/finances`      | Финансовая информация                                   |

**Авторизация:** JWT с embedded scopes, проверка через `Security(get_current_user, scopes=[...])`.

**Документация:** `GET /docs` (Swagger UI), `GET /redoc` (ReDoc).

---

## Тестирование

```bash
make test                                        # Все тесты
uv run pytest tests/unit/ -v                     # Только unit-тесты
uv run pytest tests/integration/ -v              # Только интеграционные
uv run pytest tests/unit/test_contracts.py -v    # Один файл
uv run pytest tests/unit/test_contracts.py::test_name  # Один тест
```

Стратегия: rollback-per-test — каждый тест получает соединение с внешней транзакцией, которая откатывается после теста. Auth-хедеры создаются через хелпер `make_auth_headers(user_id, role)`.

---

## Деплой

**Платформа:** [Railway](https://railway.app/) (Dockerfile-based)

```
deploy/
  docker/
    Dockerfile.railway    # python:3.14-slim-trixie + uv
  compose.db.yml          # PostgreSQL для локальной разработки
  compose.dev.yml         # Полный dev-стек (FastAPI + PostgreSQL)
```

Entrypoint (`scripts/entrypoint.sh`): миграции → запуск сервера.

```bash
# Production startup:
alembic upgrade head → fastapi run src/main.py
```
