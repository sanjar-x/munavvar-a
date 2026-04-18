# 📋 Senior Code Review: HOD Platform (полная кодовая база)

**Ветка:** `main` @ `89308fc` · **Путь:** `/home/sanjar/Desktop/munavvar-a`
**Методология:** 5 параллельных explore-агентов (finances, inventory, security, arch+api+tests, perf+debt) + точечная верификация находок.

---

## 1. Executive Summary

Архитектура — **сильная**: DDD-границы соблюдены, direction `API → App → Modules → Infra` нигде не нарушен, HTTPException в сервисах отсутствует, append-only леджеры защищены PG-триггерами. Покрытие базовых security-инвариантов (JWT, bcrypt, IDOR в client/courier, SecretStr) на хорошем уровне, SQL-инъекций в raw SQL нет.

Однако есть **3 блокера для продакшена**:

1. 🔴 **ILIKE-инъекция `%`/`_`** в `inventory.repositories.search_inventories` (в finances такой же поиск уже корректно экранирован — налицо регрессия).
2. 🔴 **Идемпотентность платежей отсутствует** — двойной POST `/transactions` и `/cashbox/accept-payment` создаёт дубли; на уровне БД нет UNIQUE-ключа.
3. 🔴 **Отсутствует CHECK-ограничение на неотрицательность баланса** в `accounts.balance` и `inventory_balances.quantity` — инвариант держится только на триггере (single point of failure при отключённом/пересозданном триггере).

Дополнительно: сломано 2 теста (один — тривиальный trailing-slash, второй — отсутствующий эндпоинт `/shifts/close` = недоделанная фича), массовый пропуск `lazy="raise"` на 30+ relationships открывает тихие N+1 на дашбордах, роль `ACCOUNTANT` получила `INVENTORY_READ` сверх необходимого, курьерский `/vehicle-stock` защищён неверным scope (`CATALOG_READ` вместо `INVENTORY_READ`).

Rate-limiting не настроен вовсе — для публичного `/auth/login` это реальный риск brute-force.

---

## 2. 🔴 Critical findings (блокеры мержа)

### C1 — ILIKE-инъекция wildcards в поиске инвентарей
**Файл:** `src/modules/inventory/repositories.py:147-162` (метод `search_inventories`, строка **154**)
```python
query = select(self.model).where(
    self.model.name.ilike(f"%{search_query}%"),
    ...
)
```
**Риск:** `q='_'` или `q='%'` превращает поиск в «всё» и частично эквивалентен IDOR (видны имена чужих складов/машин). Классический паттерн — информационная утечка, иногда — ускоренный перебор.
**Сравнение:** В `src/modules/finances/search.py:57-60` тот же подход **уже защищён** (`escape %, _, \\`). Это — регрессия, а не архитектурный пробел.
**Фикс:** скопировать `ilike_pattern` из `finances/search.py` в общий модуль (`common/search.py`) и переиспользовать:
```python
from src.common.search import ilike_pattern
self.model.name.ilike(ilike_pattern(q), escape="\\")
```
**Усилия:** S (≤30 мин).

---

### C2 — Отсутствует idempotency_key на финансовых операциях
**Файлы:**
- `src/modules/finances/schemas.py` (класс `TransactionCreate`, ~строки 86-105 — поле отсутствует)
- `src/modules/finances/services.py:600-641` (метод `create_transaction`)
- `src/api/v1/backoffice/finances.py:380` (POST `/transactions`)
- `src/api/v1/backoffice/finances.py:514` (POST `/cashbox/accept-payment`)

**Риск:** retry клиента/сети/прокси → **двойной платёж**. На уровне БД нет `UNIQUE(client_id, idempotency_key)`, на уровне приложения — тоже. Триггер защищает только от отрицательного баланса, не от дублирующего `INSERT`.
**Фикс:**
1. Добавить в `Transaction` модель поле `idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)`.
2. `UniqueConstraint("created_by", "idempotency_key", name="uq_transaction_idemp")`, WHERE `idempotency_key IS NOT NULL` (partial unique).
3. В `TransactionCreate` / `PaymentCreate` — обязательное поле `idempotency_key: uuid.UUID`.
4. В сервисе — на `IntegrityError` от этого ключа **возвращать существующую транзакцию**, а не `ConflictError`.

**Усилия:** M (4-6 ч, включая миграцию и тест).

---

### C3 — Нет CHECK-ограничения на неотрицательность балансов
**Файлы:**
- `src/modules/finances/models.py:32-82` (`Account.balance`, `BIGINT DEFAULT 0`, нет `CheckConstraint`)
- `src/modules/inventory/models.py:252-269` (`Balance.quantity`, `Integer DEFAULT 0`, нет `CheckConstraint`)

**Риск:** целостность держится **только на триггере**. Если при миграции/рефакторинге триггер выпадет (что уже случалось — см. коммит `aa56e10 fix: trigger migration fails with asyncpg due to broken $$ quoting`), любой прямой `UPDATE` или ошибочный код получает возможность оставить отрицательный остаток → финансовая и складская недостача невидима до ручного аудита.
**Фикс:** добавить миграцию `add_balance_check_constraints`:
```python
CheckConstraint("balance >= 0", name="ck_account_balance_non_negative")
CheckConstraint("quantity >= 0", name="ck_inventory_balance_non_negative")
```
Это **belt-and-suspenders** поверх триггера, а не замена.
**Усилия:** S (1 ч).

---

### C4 — Неверный scope на курьерском `/vehicle-stock`
**Файл:** `src/api/v1/courier/inventory.py:20-30` (строка **28**)
```python
Security(get_current_courier, scopes=[Scope.CATALOG_READ])
```
**Риск:** Семантический mismatch — курьер читает **свой склад (inventory)**, не каталог. Любой пользователь со scope `CATALOG_READ` (включая клиента на витрине) формально попадает под матрицу проверки scope для этого endpoint. Реальный доступ ограничен `get_current_courier`, но аудит scope-матрицы в CI даст false-pass.
**Фикс:** `scopes=[Scope.INVENTORY_READ]`.
**Усилия:** S (5 мин).

---

### C5 — `Scope.INVENTORY_READ` выдан `ACCOUNTANT`
**Файл:** `src/core/security/permissions.py:118-126` (в последнем uncommitted diff)
**Риск:** **Opinion, но с данными:** бухгалтер получает доступ к `/backoffice/dashboard/inventory/*` — остатки по SKU, движения, долги по таре. Для учёта расчётов с клиентами этого не требуется (бухгалтер работает с `finances`/`contracts`/`bills`). Это — расширение attack-surface без бизнес-обоснования в commit-сообщении и отсутствие записи в `CHANGELOG_A.md` об изменении матрицы ролей (в changelog добавлена только «Inventory секция», не RBAC).
**Фикс:** если нужен бухгалтеру для сверки — вынести узкий scope `INVENTORY_STATEMENT_READ` или ограничить доступ конкретными endpoint'ами (не вся ветка `/inventory/*`). Если нет — откатить.
**Усилия:** S.

---

## 3. 🟠 High (архитектура/производительность/корректность)

### H1 — Пропуск `lazy="raise"` на 30+ relationship (скрытые N+1)
**Файлы (точечно):**
- `src/modules/catalog/models.py:58-64` — `Product.returnable_item`, `Product.associated_products`
- `src/modules/finances/models.py:63-72, 138-147` — `Account.user`, `Account.outgoing_transactions`, `Account.incoming_transactions`, `Transaction.from_account`, `Transaction.to_account`, `Transaction.verified_by`
- `src/modules/inventory/models.py:61-74, 166-174` — `StockTransfer.from_inventory`, `to_inventory`, `created_by`, `accepted_by`
- `src/modules/orders/models.py:141-157` — `Order.client_inventory`, `Order.warehouse`, `Order.items`
- `src/modules/users/models.py:39, 85, 123-134, 142-155` — `User.identities`, `User.phone_numbers`, `User.accounts`

**Показатель качества:** контракты (`src/modules/contracts/models.py`) сделаны **правильно** — все relations с `lazy="raise"`. Это значит, что команда знает паттерн, но не применяет его системно → тихие деградации на дашбордах.
**Риск:** каждый хит на `/backoffice/finances` с 100 транзакциями → до 300 отдельных `SELECT` на `from_account`/`to_account`/`verified_by`, если в конкретном репо забыли `selectinload`.
**Фикс:** повсюду добавить `lazy="raise"`; на сломавшихся эндпоинтах — явный `selectinload(...)`/`joinedload(...)`. Обёрнуть изменение в отдельный PR c прогоном интеграционных тестов — они поймают недостающие eager-loads.
**Усилия:** M (2-3 ч + fix упавших тестов).

---

### H2 — Cross-module import моделей в репозиториях/dashboard_queries
**Файлы:**
- `src/modules/finances/repositories.py:13, 22` — импорт `Contract`, `Order`
- `src/modules/finances/dashboard_queries.py:34-37` — импорт `Order`, `User`, `OrderStatus`
- `src/modules/inventory/dashboard_queries.py:14-39` — импорт `Product`, `Order`, `User`
- `src/modules/users/dashboard_queries.py:10-28` — импорт `Product`, Finance, Inventory, Order моделей
- `src/modules/inventory/services.py:14` — импорт **`CatalogService`** (service-to-service, минует UoW)
- `src/modules/orders/services.py:11-13, 20` — импорт `contracts.enums`, `contracts.models`, `contracts.exceptions`

**Риск (Opinion):** модули перестают быть заменяемыми. `dashboard_queries` — это по сути **read-model/application layer**, маскирующийся под module-internal. Когда завтра finances захотят шардировать в отдельную БД — все эти JOIN'ы с `orders.models.Order` взорвутся.
**Фикс:**
- Перенести `*/dashboard_queries.py` в `src/application/dashboards/` (это чтение по нескольким доменам — самый чистый use case для application-слоя).
- `inventory.services` не должен импортировать `CatalogService`: либо передавать резолвер-функцию через конструктор, либо вызывать через application-оркестратор.
- `orders.services` → `contracts`: пограничный кейс. Как минимум — использовать только публичные interfaces из `contracts.public` (если нет — создать).

**Усилия:** L (1-2 дня, отдельный рефакторинг PR).

---

### H3 — Последовательные `await` в циклах
**Файлы:**
- `src/modules/contracts/services.py:331-334` — `for oid in reserved_ids: await self.uow.orders.update(oid, ...)` (отмена резервов квоты)
- `src/modules/contracts/services.py:830, 850` — batch-джоба по `candidates` контрактов, внутри — `_cancel_inflight_orders` (вложенный N+1 по заказам)
- `src/modules/finances/services.py:727-736` — вложенные циклы по `courier_accounts` и `today_txns`

**Риск:** при росте контрактной базы до 500+ активных batch-джоба по истечению квот будет работать минуты, блокируя scheduler. Сейчас не видно — потому что объёмов нет.
**Фикс:** Для ORM-`UPDATE` — использовать `bulk_update_mappings` или один `UPDATE ... WHERE id IN (:ids)`. Для независимых операций — `asyncio.gather(..., return_exceptions=True)` с разумным `Semaphore` (10-20).
**Усилия:** S-M.

---

### H4 — Rate limiting полностью отсутствует
**Файлы проверены:** `src/api/server.py`, `src/api/middlewares/` — нет `slowapi`/`fastapi-limiter`/кастомной middleware.
**Риск:** `/auth/login` открыт для brute-force (bcrypt — дорого, но реалистично). Массовая энумерация клиентов через `/clients?skip=...`. DoS через дашборд-эндпоинты с `limit=100`.
**Фикс:** `slowapi` + Redis (который уже в конфиге, но не используется — см. `CLAUDE.md:64`). Минимум:
- `/auth/*` — 10 req/min/IP
- Writes (`POST /transactions`, `/orders`) — 60 req/min/user
- Reads — 300 req/min/user

**Усилия:** M (0.5-1 день, заодно активирует Redis из `.env`).

---

### H5 — `IntegrityError` → всегда generic `ConflictError`
**Файл:** `src/infrastructure/database/uow.py:43-55`
```python
except IntegrityError as e:
    await self.rollback()
    raise ConflictError(
        message="Конфликт! ...",
        error_code="DB_INTEGRITY_ERROR",
    ) from e
```
**Риск:** клиент/UI не различает:
- нарушение UNIQUE (надо показать «уже существует»);
- нарушение CHECK (например, `balance < 0` → «недостаточно средств»);
- нарушение FK (программная ошибка, надо alerting);
- race condition на advisory lock.

Сейчас всё это — одинаковый 409 без details. Бизнес-логика, которую **я же рекомендую в C2** (idempotency), полагается на differentiated error.
**Фикс:** парсить `e.orig.diag.constraint_name` (asyncpg) и мапить в конкретные subclasses `ConflictError` (`DuplicateKeyError`, `CheckConstraintError`). Добавить `details={"constraint": name}`.
**Усилия:** M (2-3 ч).

---

### H6 — Устаревший SQLAlchemy beta в зависимостях
**Файл:** `pyproject.toml` — `sqlalchemy[asyncio]>=2.1.0b1`
**Риск:** beta может быть несовместима с `asyncpg` новейших версий; любой `pip install` тянет plovaruyuschuyu бета-версию без pinning. Уже был инцидент с `$$` quoting (`aa56e10`) и split statements (`1f17793`) — оба характерны для edge-кейсов драйвера/ORM.
**Фикс:** pin `>=2.0.36,<2.1` или `>=2.0.41,<2.2` (stable).
**Усилия:** S (pin + прогон всех интеграционных тестов).

---

## 4. 🟡 Medium (корректность / консистентность)

### M1 — `/shifts/close` endpoint отсутствует, тест ожидает 200
**Файлы:** тест `tests/integration/test_courier_shift_close.py:105` шлёт `POST /api/v1/backoffice/shifts/close`. В `src/api/v1/backoffice/__init__.py` нет `shifts_router`. Видимо, файл `src/api/v1/backoffice/shifts.py` существует (матч в `__pycache__`), но не подключён. См. раздел 6.

### M2 — Trailing-slash 307 на `/backoffice/users`
Роутер `src/api/v1/backoffice/users.py:45` регистрирует `GET "/"`, префикс `/users` → путь `/users/`. Тест `tests/integration/test_backoffice_staff_list.py:38` шлёт `/users`. Детали — раздел 6.

### M3 — `Transaction.reason` — возможное усечение
**Файл:** `src/modules/finances/services.py:701-702` — конкатенация `f"{txn.reason} | Отклонено: {reason}"` в поле `String(255)`. При длинном исходном reason → последний пользовательский комментарий уйдёт в `... | Отклон...`, а не ошибка, а обрезание на стороне БД зависит от dialect (PG бросит `value too long`). Фикс: явный trim или — лучше — вынести журнал отмен в отдельную таблицу `transaction_status_log` (audit trail, append-only).

### M4 — Широкий `except Exception:` в финансах
**Файл:** `src/modules/finances/services.py:87-90, 97-101, 130-133` — маскируется `DetachedInstanceError`/LazyLoad → silent `None`. Заменить на узкие исключения SQLAlchemy ИЛИ (лучше) гарантировать eager-load и убрать try/except.

### M5 — Сплит `add_many` в `create_transfer` может оставить orphan-items
**Файл:** `src/modules/inventory/services.py:537-539` — `transfer_items` вставляются до `stock_transactions`. При триггер-exception на втором add_many `rollback` спасает (одна транзакция Python-стороне), но **только потому, что UoW не закоммичен между ними**. Если кто-то в будущем разнесёт это по разным UoW/сохранит частичный коммит — будут orphan transfer_items. Добавить `ON DELETE CASCADE` от `stock_transfers` к `stock_transfer_items` и/или объединить два `add_many` в один insert.

### M6 — Deep-OFFSET pagination на `/backoffice/transfers`, `/finances`, `/contracts`
Все listing'и используют `OFFSET`. При `page=500, size=100` PostgreSQL честно просканирует 50k строк. Пока объёмов нет — не проблема; при росте — keyset-курсор (`created_at, id` → уже индексирован в `c3f8a9d4e2b1`).

### M7 — `TransactionResponse` / `TransactionDetail` — дубликат схем
**Файл:** `src/modules/finances/schemas.py` (указано в `research/INVENTORY_SEARCH_FILTERS_FRD.md`/`FINANCES_SEARCH_FILTERS_FRD.md`). FRD обещает `@deprecated` — в коде не выставлено. OpenAPI выдаёт два почти идентичных типа. Плановый unify в следующей итерации.

### M8 — Redis сконфигурирован, не используется
`CLAUDE.md:64` честно признаётся. Либо подключать (для rate-limit из **H4** — идеальный кейс), либо убрать из конфига.

### M9 — `REDISPORT` default mismatch
`.env.example:20` → `8000`, `src/core/config.py:59` → `6379`. Путает новичков.

### M10 — Курьер-инвентарь: `get_current_courier` возвращает User, а не Courier-subclass
**Opinion:** в нескольких местах используется `User` как generic — нет доменного типа `CourierProfile`. Это не баг, но усложняет scope-audits (см. **C4**).

---

## 5. 🟢 Low (списком, без деталей)

- `src/modules/auth/dependencies.py:70` — `except ValueError, TypeError:` (без скобок). Технически **валидно** в Python 3.14 (парсится как tuple), но **путает читателя** и breaks на Py≤3.13. Переписать на `except (ValueError, TypeError):`. *Отдельно: sub-агент security ошибочно пометил это как Critical — это не SyntaxError в Py3.14.*
- AFTER-триггер на `transactions`/`stock_transactions` (агент finances отметил как High). На деле — корректно: `RAISE EXCEPTION` из AFTER-триггера **откатывает** транзакцию так же, как из BEFORE; разница лишь в том, что PG успевает выполнить INSERT/UPDATE до отката. Для append-only этого достаточно, можно оставить как Low/opinion.
- Нет `@deprecated`-меток на старых query-params (finances используют — остальным бы тоже).
- `research/*.md` FRD-документы расходятся с актуальным кодом (например, обещанный deprecate `TransactionResponse`). Добавить `research/IMPLEMENTATION_STATUS.md`.
- `src/api/v1/backoffice/transport.py` — `# TODO: Add specific TRANSPORT_READ permission if exists` — один висячий TODO.
- Нет тестов на попытку `UPDATE transactions` / `UPDATE stock_transactions` → **ledger invariant не покрыт тестом** (инвариант держится, но регрессию не поймаем).
- Нет audit-лога на verify/reject transaction (структурно — правильно делать middleware, а не в сервисе).
- Deadlock-риск на параллельных transfer'ах (двойной lock: `Inventory.FOR UPDATE` + триггерный `accounts FOR UPDATE`). Opinion — под нагрузкой проверить.
- CORS: в dev допускает wildcard без warning'а. Добавить `log.warning`.
- `bcrypt` через `pwdlib` — fine, но Argon2id на новых UX предпочтительнее (opinion).
- `tests/` — 21 файл, ~5k строк. `@pytest.mark.skip`/`xfail` **нет** (хорошо). Но нет smoke для migrations up→down→up.

---

## 6. Pre-existing test failures — root cause и fix

### FAIL-1 · `test_backoffice_staff_list.py::test_get_staff_users_filters_by_roles` → 307

**Root cause:**
- Роутер: `src/api/v1/backoffice/users.py:46` — `@users_router.get("/", ...)`.
- Подключение: `src/api/v1/backoffice/__init__.py:31` — `include_router(users_router, prefix="/users", ...)` → финальный путь `GET /api/v1/backoffice/users/`.
- Тест: `tests/integration/test_backoffice_staff_list.py:38` — `await client.get("/api/v1/backoffice/users", ...)` (без слэша).
- FastAPI с дефолтным `redirect_slashes=True` возвращает **307 Temporary Redirect** на `/users/`. httpx-клиент в тесте не следует redirect → ассерт 200 валится.

**Fix (в порядке предпочтения):**
1. **Минимальный (тест):** добавить `/` в строке 38 теста — `"/api/v1/backoffice/users/"`. Затраты: 1 символ, риск регрессии нулевой.
2. **Системный (роутер):** заменить `@users_router.get("/")` на `@users_router.get("")`. Тогда работают **оба** пути (без и со слэшем). Однако нужно пройтись по **всем** роутерам и привести к единому стилю (`src/api/v1/backoffice/users.py`, `clients.py`, и т.п. — уже проверить стоит).
3. **Не рекомендуется:** `FastAPI(redirect_slashes=False)` — ломает совместимость с любыми существующими клиентами, отправляющими запросы без слэша.

**Рекомендация:** применить п.2 на весь `backoffice` — уже сейчас API-контракт в части slash'ей не единообразен.

---

### FAIL-2 · `test_courier_shift_close.py::test_shift_close_returns_stock_and_collects_cash` → 404

**Root cause:**
- Тест (строка 105): `POST /api/v1/backoffice/shifts/close` с payload `{courier_id, returned_inventory, cash_collected}`.
- В `src/api/v1/backoffice/__init__.py` — **нет** `shifts_router`. Файл `src/api/v1/backoffice/shifts.py` обнаружен только в `__pycache__` → исходник удалён, но `.pyc` остался. Аналогично сервис `src/modules/inventory/shift_service.py` — только `.pyc`.
- Это **не тривиальный trailing-slash**, а **обрезанная/недомёрженная фича**: «закрытие смены курьера с возвратом стока и сбором нала». Тест остался; код смены — нет.

**Fix — по ситуации:**
- **Если фича запланирована (бизнес-кейс):** реализовать её целиком. Понадобится:
  - `src/api/v1/backoffice/shifts.py` с `POST /close` (scope `INVENTORY_WRITE` + `FINANCES_WRITE`).
  - `src/application/shift/` — оркестратор: создать `StockTransfer` (возврат с машины курьера в склад) + `Transaction` (сдача нала в кассу) одной транзакцией.
  - Регистрация в `__init__.py`.
  - Unit тесты на rollback при несоответствии возвращённого стока.
- **Если фича отменена/перенесена:** удалить тест и устаревший `.pyc` (`find . -name '*.pyc' -path '*shift*' -delete`), добавить запись в CHANGELOG.
- **Промежуточный вариант (спринт):** пометить тест `@pytest.mark.skip(reason="/shifts/close endpoint pending — see ticket #XXX")`, завести тикет.

**Рекомендация:** узнать у продукта — живёт ли фича. Pragmatic skip до принятия решения.

---

## 7. Приоритезированный roadmap

Topological order: сначала данные и безопасность, потом производительность, потом debt.

### Итерация 1 — «Стоп-кран продакшена» (1-2 дня)
1. **C1** ILIKE-экранирование в inventory search (30 мин).
2. **C4** Исправить scope на courier `/vehicle-stock` (5 мин).
3. **C5** Пересмотреть scope `INVENTORY_READ` у `ACCOUNTANT` (либо откат, либо узкий scope).
4. **C3** Миграция с `CheckConstraint balance >= 0` для accounts+inventory_balances (1 ч).
5. **FAIL-1** trailing-slash fix (5 мин + унификация по всему backoffice).
6. **FAIL-2** Решение по `/shifts/close`: implement/skip/delete.

### Итерация 2 — «Надёжность денег» (3-5 дней)
7. **C2** Idempotency-ключи на платежах и связанные изменения UoW.
8. **H5** Дифференциация `IntegrityError` → конкретные subclasses (нужна для C2 → делать после).
9. **H4** Rate limiting (`slowapi` + активация Redis из конфига — M8).
10. Добавить тесты на **ledger-инвариант** (UPDATE/DELETE на transactions → ConflictError) — не дороже 2 ч.

### Итерация 3 — «Производительность» (2-3 дня)
11. **H1** `lazy="raise"` повсеместно + исправление упавших тестов на отсутствие eager-load.
12. **H3** `asyncio.gather` / bulk-update в contracts batch-джобах.
13. **H6** Pin SQLAlchemy до stable.

### Итерация 4 — «Чистка и архитектурный рефакторинг» (1-2 недели)
14. **H2** Перенос `dashboard_queries.py` в `src/application/dashboards/`, удаление прямых импортов моделей других модулей из `repositories.py`.
15. **M7** Deprecate `TransactionResponse`, унификация схем.
16. **M3** Вынести историю отмен Transaction в отдельную append-only таблицу.
17. **M6** Keyset-pagination на горячие listing'и (transfers, transactions).
18. **M8/M9** Redis: активировать для rate-limit + починить `.env.example`.
19. **Low:** `except (ValueError, TypeError):` со скобками (auth/dependencies.py:70), TODO в transport.py, CORS warning в dev, `research/IMPLEMENTATION_STATUS.md`.

---

**Вердикт:** Кодовая база на уровне «твёрдой альфы, близкой к beta». Фундамент (DDD-границы, триггерный append-only, SQL-безопасность, IDOR) — **сделан хорошо**. Для продакшена нужен 1-2-дневный sprint по блокерам C1-C5 + FAIL-1/FAIL-2. Всё остальное — плановый tech debt, управляемый.___BEGIN___COMMAND_DONE_MARKER___0
