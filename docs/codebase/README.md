# HOD — Home & Office Delivery

B2B/B2C платформа управления доставкой бутилированной воды: от приёма заказа до доставки курьером, перемещения товара между складами и финансовой сверки. Построена как DDD модульный монолит на Python/FastAPI/PostgreSQL.

**Ключевой принцип:** двойная бухгалтерия (складской леджер + финансовый леджер) — каждое движение товара и каждая денежная операция прослеживается через двойную запись. Целостность леджеров обеспечивается триггерами PostgreSQL на уровне БД, а не приложения.

---

## Бизнес-домен

### Что делает система

1. **Управление заказами** — полный цикл от корзины до доставки
   - Два типа продаж: доставка курьером (`DELIVERY`) и самовывоз со склада (`WAREHOUSE_PICKUP`)
   - Конечный автомат статусов: `NEW` -> `ASSIGNED` -> `IN_TRANSIT` -> `ARRIVED` -> `DELIVERED`
   - Самовывоз: `NEW` -> `PICKUP_COMPLETED`
   - Автоматическая фиксация цен на момент заказа (заморозка)

2. **Складской учёт** — движение товара между точками хранения
   - 5 типов инвентаря: `WAREHOUSE`, `COURIER`, `CLIENT`, `VIRTUAL_VENDOR`, `VIRTUAL_LOSS`
   - 9 типов перемещений с валидацией маршрутов (кто откуда куда может перемещать)
   - Append-only леджер: `StockTransaction` — неизменяемые записи, DELETE/UPDATE заблокированы триггером
   - Материализованные остатки: таблица `InventoryBalance` обновляется триггером атомарно

3. **Финансовый учёт** — двойная запись по всем денежным операциям
   - 7 типов счетов: `REVENUE`, `CASH`, `CARD`, `BANK`, `DISCOUNT`, `CLIENT`, `COURIER`
   - Каждая транзакция — перевод с одного счёта на другой (double-entry)
   - Append-only леджер: `Transaction` — неизменяемые записи
   - Баланс счёта обновляется триггером с row-level locking (`FOR UPDATE`)
   - Статусы: `PENDING` -> `COMPLETED` / `REJECTED` (верификация бухгалтером)

4. **Система оборотной тары** — отслеживание возвратных бутылей
   - Продукт может ссылаться на возвратную тару (`returnable_item_id`)
   - При создании заказа: автоматическая проверка наличия пустых бутылей у клиента
   - Автооприходование (`INITIAL_BALANCE` из `VIRTUAL_VENDOR`) при дефиците
   - Защита от мошенничества: оприходуется ровно столько, сколько нужно для текущего заказа

5. **Ролевая модель** — 8 ролей с granular permissions через JWT scopes
   - `ADMIN`, `ACCOUNTANT`, `STOREKEEPER`, `CASHIER` — бэкофис
   - `COURIER` — мобильное приложение курьера
   - `CLIENT_B2C`, `CLIENT_B2B` — клиентский интерфейс
   - `SYSTEM` — системные операции (виртуальные склады, служебные счета)

### Типичные потоки

**Доставка заказа:**

```
Клиент создаёт заказ -> Проверка тары -> Автооприходование дефицита
-> Админ назначает курьера -> Курьер загружает товар (WAREHOUSE -> COURIER)
-> Курьер в пути -> Курьер на месте -> Доставлено (COURIER -> CLIENT)
-> Клиент возвращает пустые бутыли (CLIENT -> COURIER)
-> Курьер сдаёт оплату -> Бухгалтер верифицирует транзакцию
```

**Самовывоз:**

```
Клиент приходит на склад -> Возврат тары (CLIENT -> WAREHOUSE)
-> Создание заказа -> Продажа со склада (WAREHOUSE -> CLIENT)
-> Оплата на месте -> Верификация
```

---

## Технологический стек

| Слой              | Технологии                                 |
| ----------------- | ------------------------------------------ |
| Runtime           | Python 3.14+, CPython                      |
| Web Framework     | FastAPI (async, ASGI/Uvicorn)              |
| ORM               | SQLAlchemy 2.x (async mode, asyncpg)       |
| База данных       | PostgreSQL 18 (триггеры, PL/pgSQL)         |
| Миграции          | Alembic                                    |
| Валидация         | Pydantic v2                                |
| Аутентификация    | JWT (PyJWT, HS256), Bcrypt (pwdlib[argon2,bcrypt], активен только Bcrypt) |
| Логирование       | structlog (JSON в проде, консоль в dev)    |
| Пакетный менеджер | uv (Astral)                                |
| Линтер/форматтер  | Ruff (line-length: 79)                     |
| Тесты             | pytest + pytest-asyncio + httpx            |
| Frontend          | React 19 + Redux Toolkit + Vite            |
| Деплой            | Railway (backend), Vercel (frontend)       |

---

## Архитектура

```
src/
  api/                  # HTTP-слой: роутеры, middleware, обработка ошибок
    v1/
      auth/             # Логин, регистрация
      backoffice/       # Админка: заказы, перемещения, финансы, каталог, пользователи
      client/           # Клиентский API: заказы, каталог, профиль
      courier/          # API курьера: задания, статусы доставки
  application/          # Оркестрация кросс-доменных процессов
    client/             # Онбординг клиента (User + Identity + Account + Inventory)
    courier/            # Онбординг курьера (User + Identity + Account + Transport)
    inventories/        # Склады, транспорт, перемещения, оприходование тары
    order/              # Создание заказов с автооприходованием
  modules/              # Доменные модули (DDD bounded contexts)
    auth/               # Аутентификация
    catalog/            # Каталог продуктов (WATER, CONTAINER, EQUIPMENT)
    orders/             # Жизненный цикл заказа, FSM, логика тары
    inventory/          # Складской леджер, перемещения, остатки
    finances/           # Финансовый леджер, счета, транзакции
    users/              # Пользователи, роли, идентификации
  common/               # Базовые абстракции: Repository, Service, UoW
  infrastructure/       # БД: engine, session, BaseModel, триггеры (SQL)
  core/                 # Конфигурация, безопасность, JWT, RBAC, логирование
```

### Паттерны

- **Repository** — CRUD-обёртка над SQLAlchemy, generic по типу модели
- **Unit of Work** — транзакционная граница, композиция репозиториев на одной сессии
- **Service Layer** — бизнес-логика, возвращает frozen DTO, никогда ORM-объекты наружу
- **CQRS-lite** — `queries.py` для read-only операций (отдельно от write-сервисов)
- **Domain Exceptions** — иерархия `AppException` с кодами ошибок и русскими сообщениями

### Целостность данных

| Механизм                                 | Что защищает                                                         |
| ---------------------------------------- | -------------------------------------------------------------------- |
| PG триггер `update_account_balances()`   | Атомарное обновление баланса счёта при INSERT/UPDATE транзакции      |
| PG триггер `update_inventory_balances()` | Атомарное обновление складских остатков при INSERT stock_transaction |
| Блокировка DELETE на леджерах            | Невозможно удалить записи из `transactions` и `stock_transactions`   |
| `ondelete="RESTRICT"`                    | Критические FK не допускают каскадного удаления                      |
| `lazy="raise"`                           | Защита от N+1 запросов на bulk-рисковых связях                       |
| CheckConstraint                          | Валидация на уровне БД (price >= 0, quantity > 0)                    |
| Валидация маршрутов                      | Каждый тип перемещения имеет допустимые пары (from_type, to_type)    |

---

## Быстрый старт

```bash
# Зависимости
uv sync

# БД (PostgreSQL в Docker)
docker compose -f deploy/compose.db.yml up -d

# Миграции
make upgrade

# Запуск dev-сервера
make dev
# или
uv run fastapi dev src/main.py

# Тесты
make test

# Frontend
cd frontend && npm install && npm run dev
```

### Переменные окружения

| Переменная                                               | Описание                    |
| -------------------------------------------------------- | --------------------------- |
| `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` | Подключение к PostgreSQL    |
| `SECRET_KEY`                                             | Ключ подписи JWT            |
| `ENVIRONMENT`                                            | `dev` / `test` / `prod`     |
| `DEBUG`                                                  | SQL echo + console renderer |
| `ADMIN_PHONE`, `ADMIN_PASSWORD`                          | Начальный админ             |
| `CORS_ORIGINS`                                           | Разрешённые origins         |

---

## API

Три аудитории, три набора эндпоинтов:

- **`/api/v1/backoffice/`** — полное управление (заказы, перемещения, финансы, каталог, пользователи)
- **`/api/v1/client/`** — создание заказов, каталог, профиль, история
- **`/api/v1/courier/`** — задания, переходы статусов доставки, профиль

Авторизация: JWT с embedded scopes, проверка через `Security(get_current_user, scopes=[...])`.

Документация: `GET /docs` (Swagger UI), `GET /redoc` (ReDoc).
