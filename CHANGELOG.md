# CHANGELOG (HOD API)

**Single source of truth** для всех breaking и не-breaking изменений
бэкенд-API HOD. Этот файл читают и фронтенд, и интеграции.

- Backend-репа: `/CHANGELOG.md` — авторитетный файл.
- Frontend-репа (`Yokubjanovichh/MunnavarA`): `frontend/CHANGELOG.md` —
  symlink на `../CHANGELOG.md` через git-submodule.
- Pre-commit hook `scripts/check-changelog-sync.sh` блокирует коммит, если
  изменены публичные контракты (`src/api/v1/**`, `src/modules/*/schemas.py`,
  `src/modules/*/enums.py`, `alembic/versions/*.py`) без правки этого файла.

Формат: [Keep a Changelog 1.1](https://keepachangelog.com/en/1.1.0/).
Версионирование не семантическое — привязано к итерациям FRD.

---

## [Unreleased] — Walk-in warehouse-sale: автокапитализация тары (hotfix)

Источник: prod-инцидент — `POST /api/v1/backoffice/orders/warehouse-sale`
для анонимного покупателя (walk-in, без `clientId`) падал на 409
`INSUFFICIENT_TARA`, потому что у walk-in-клиента физически нет
отслеживаемого баланса пустой тары.

### Changed

- `POST /backoffice/orders/warehouse-sale` без `clientId` (walk-in)
  теперь **всегда** включает автооприходование недостающей тары из
  `VIRTUAL_VENDOR`, независимо от значения `capitalize_missing_tara`
  в payload. Семантика: анонимный покупатель не приносит пустую тару,
  и кассир не может «сдать» её от его имени — поэтому дефицит
  закрывается виртуальной поставкой автоматически.

### Frontend impact

- Можно по-прежнему слать `capitalize_missing_tara: false` для walk-in
  — бэкенд это проигнорирует. Для **именованного** клиента
  (`clientId` передан) поведение не изменилось: 409 при дефиците,
  кассир должен либо сначала вызвать
  `/orders/warehouse-sale/capitalize-tara`, либо передать
  `capitalize_missing_tara: true`.

---

## [Unreleased] — Soft quota limits: схема под фичу мягких квот (только DB)

Источник: миграция `d4e5f6a7b8c9_soft_quota_limits` — выкатывается раньше
бизнес-логики, чтобы prod alembic не падал на отсутствующем revision-id.

### Database (без изменения публичного API)

- `contract_price_items`: снят CHECK
  `ck_contract_price_item_quantity_used_le_limit` —
  `quantity_used` теперь может превышать `quantity` (soft-лимит).
- `orders`: добавлены поля `quota_exceeded BOOLEAN NOT NULL DEFAULT FALSE`
  и `quota_overspend JSONB NULL` (детализация перерасхода).
- Голова Alembic: **`d4e5f6a7b8c9`** (предыдущая — `c3f8a9d4e2b1`).

### Frontend impact

На сегодня — **нет**. API-схемы заказов и договоров поля ещё не
возвращают (бэкенд-логика в working tree, не закоммичена). Когда
бизнес-логика выйдет, поля `quota_exceeded` и `quota_overspend`
появятся в `OrderResponse` отдельной записью в этом CHANGELOG.

---

## [Unreleased] — Ledger CHECK-constraints rollback (внутренний фикс схемы)

Источник: ревью миграции `d7a2f91c4e68_ledger_check_constraints` —
обнаружено противоречие с дизайном леджеров.

### Removed

- Миграция `d7a2f91c4e68_ledger_check_constraints` удалена. Не была
  выпущена в production. Текущая alembic-голова — `c3f8a9d4e2b1`.
- Глобальный `CheckConstraint("balance >= 0", ...)` снят с модели
  `Account` (`src/modules/finances/models.py`).
- Глобальный `CheckConstraint("quantity >= 0", ...)` снят с модели
  `InventoryBalance` (`src/modules/inventory/models.py`).

### Rationale (для фронтенда)

API-контракты **не меняются** — это правка схемы БД/моделей.
Фронту достаточно знать, что:
- Поле `Account.balance` может быть отрицательным для CLIENT/COURIER
  счетов (overdraft/credit-сценарий) — фильтр `is_in_credit=true` в
  `/finances/accounts` это уже использует.
- Поле `InventoryBalance.quantity` может быть отрицательным для
  виртуальных инвентарей `VIRTUAL_VENDOR` (источник оприходования) и
  растущим без ограничений для `VIRTUAL_LOSS` (яма списаний) —
  отдельных эндпоинтов на эти строки нет, в `/balances` они скрыты
  фильтром `nonzero_only=true` по умолчанию.

Партиальные инварианты (`quantity >= 0` для не-виртуальных) уже
enforced на стороне триггера `update_inventory_balances`. Для
финансовых счетов overdraft не запрещается ни триггером, ни DDL.

---

## [Unreleased] — Inventory API: cursor-пагинация для legacy-эндпоинтов

Источник: `research/INVENTORY_SEARCH_FILTERS_FRD.md` Draft v4 (§4.4, §15.2).

### Обзор

Добавлена **opt-in cursor-пагинация** для трёх существующих
backoffice-эндпоинтов в дополнение к текущему offset-режиму.
Активируется передачей query-параметра `?cursor=…` (и опционального
`size`), без него поведение и форма ответа полностью сохраняются —
breaking-change нет.

### Added

- `GET /backoffice/transfers/?cursor=…&size=…` — cursor-режим.
  Сортировка `(created_at DESC, id DESC)`. Ответ —
  `TransfersCursorListResponse { items, pagination }`.
- `GET /backoffice/warehouses/?cursor=…&size=…` — cursor-режим.
  Сортировка `(name ASC, id ASC)`. Ответ —
  `WarehousesCursorListResponse { items, pagination }`. (FRD §5.4
  допускает оставить только offset, но фронт-команда попросила
  единообразие во всех трёх ручках.)
- `GET /backoffice/inventories/search?cursor=…&size=…` — cursor-режим.
  Сортировка `(name ASC, id ASC)`. Ответ —
  `InventoriesSearchCursorListResponse { items, pagination }`.
- `CursorPaginationMeta` — общая мета-схема:
  ```json
  {"mode":"cursor","size":50,"has_more":true,"next_cursor":"…"}
  ```
- Новая ошибка `422 CURSOR_INVALID` (`CursorInvalidError`) для
  повреждённых/несовместимых токенов.

### Cursor-токен

Opaque base64url-строка, кодирует пару `(sort_value, id)` последней
строки страницы. Формат:
`base64url("v1|<kind>|<uuid>|<sort_value>")`, где `kind ∈ {dt,s,i}`.
UUID помещён **перед** `sort_value`, чтобы декодер устойчиво работал
даже когда `sort_value` (например, имя склада) содержит символ `|`.
Frontend **не должен** парсить или модифицировать токен — только
передавать как есть.

### Changed

- Response-схемы трёх эндпоинтов расширены до union:
  `list[X] | XCursorListResponse`. OpenAPI публикует обе формы; client
  выбирает по наличию `cursor` в запросе.

### Fixed (pre-release)

- Порядок полей в cursor-токене изменён с
  `v1|<kind>|<sort_value>|<uuid>` на `v1|<kind>|<uuid>|<sort_value>`.
  Старая раскладка ломала `decode_cursor` для имён складов с `|`
  (валидное значение в БД) — `split("|", 3)` отдавал в слот UUID
  «хвост строки + UUID». Токены ещё не были выпущены наружу, поэтому
  миграции на стороне фронтенда не требуется.
- Сервисы (`TransferService`, `WarehouseService`) теперь явно
  отвергают cursor-токен «чужого» типа (например, `datetime`-токен
  от `/transfers` в `/warehouses`) с `422 CURSOR_INVALID` вместо
  тихого приведения к строке.

### Notes

- Размер страницы валидируется: `1 ≤ size ≤ 100` (для transfers и
  warehouses) и `1 ≤ size ≤ 200` (для inventories/search).
- В cursor-режиме `total_count` не возвращается (FRD §4.4 — намеренно,
  чтобы не запускать `COUNT(*)` на каждой странице).
- Cursor стабилен на append-only данных; при rename склада/перемещении
  записи во времени между страницами возможен skip/duplicate — это
  ожидаемое поведение keyset-пагинации.

### Tests

- `tests/unit/test_pagination_cursor.py` — 16 тестов: roundtrip
  (datetime/string/int), URL-safe encoding, инвалидация
  (base64/payload/uuid/version/kind/empty), `build_cursor_meta`
  (boundary/has_more/empty/exact-size), регрессия на `|` в
  `sort_value`, межтиповая совместимость токенов.

---

## [Unreleased] — Inventory API: новые эндпоинты `/stock-transactions` и `/balances`

Источник: `research/INVENTORY_SEARCH_FILTERS_FRD.md` Draft v4 (§6, §9).

### Обзор

Реализована **read-only часть Iteration 1** для модуля Inventory:
два новых эндпоинта, дающих фронтенду единый список движений и
кросс-вью остатков с расширенными фильтрами, поиском и пагинацией —
по той же UX-модели, что уже работает в `GET /backoffice/finances/transactions`.

Существующие эндпоинты (`GET /transfers`, `GET /warehouses`,
`GET /transports`, `GET /inventories/search`) **не тронуты** — их
рефакторинг под `?format=paged` отложен в Iteration 2 для
скоординированной миграции с фронтендом.

### Added

#### `GET /backoffice/stock-transactions/` (новый)

Журнал всех движений товара (склад → курьер → клиент).
Scope: `inventory:read` (ADMIN, STOREKEEPER, ACCOUNTANT, COURIER).

Query-параметры:
- `q` — free-text (имя продукта/склада, кол-во как число,
  суффикс телефона владельца склада). 2..100 символов.
  **UUID-поиск запрещён** — `400 SEARCH_UUID_NOT_ALLOWED`.
- Multi-value фильтры: `product_id_in`, `product_type_in`,
  `from_type_in`, `to_type_in`, `transfer_type_in`.
- Single-value фильтры: `product_id`, `from_id`, `to_id`,
  `inventory_id` (+ `direction=incoming|outgoing|any`),
  `transfer_id`, `order_id`, `created_by_id`.
- Диапазоны: `quantity_eq | quantity_from + quantity_to`,
  `date_from + date_to | date_preset` (today / yesterday /
  this_week / last_week / this_month / last_month, TZ
  Asia/Tashkent).
- Сортировка: `sort=created_at|quantity`, `order=asc|desc`.
- Пагинация: `page` (≥1), `size` (1..100). `page*size ≤ 10_000`.

Ответ: `{items, pagination, summary}`, где
`summary = {total_transactions, total_quantity, by_transfer_type}`.

#### `GET /backoffice/balances/` (новый)

Кросс-вью на материализованные остатки `inventory_balances`.
Scope: `inventory:read`.

Query-параметры:
- `q` — поиск по имени продукта/инвентаря.
- `product_id`, `product_id_in`, `product_type_in`,
  `inventory_type_in`, `inventory_id_in`, `user_id`,
  `quantity_from`, `quantity_to`.
- `nonzero_only=true` (по умолчанию) — скрыть «пустые» строки.
- Сортировка: `sort=quantity|product_name|inventory_name`,
  `order=asc|desc`.

Ответ: `{items, pagination, summary}`, где
`summary = {total_quantity, by_inventory_type}`.

### Changed

- Роль **ACCOUNTANT** получает scope `inventory:read` — было снято
  в предыдущем ревью «авансом», теперь возвращено осознанно: новые
  эндпоинты существуют и нужны бухгалтеру для сверки. Backoffice
  остатков/леджера для бухгалтерии — официальный сценарий.

### Errors (новые коды)

- `400 SEARCH_TOO_SHORT` — `q` короче 2 символов.
- `400 SEARCH_TOO_LONG` — `q` длиннее 100 символов.
- `400 SEARCH_UUID_NOT_ALLOWED` — `q` похож на UUID или его
  hex-фрагмент (≥ 8 hex-символов подряд / `0x...`).
- `400 DATE_RANGE_INVALID`, `400 DATE_PRESET_CONFLICT` —
  логика дат.
- `400 QUANTITY_RANGE_INVALID`, `400 QUANTITY_CONFLICT` —
  взаимоисключающие quantity-параметры.
- `400 PAGINATION_TOO_DEEP` — `page * size > 10_000`.

### Breaking Changes

**Нет.** Только добавление эндпоинтов и расширение scope для роли
ACCOUNTANT. Существующие маршруты работают без изменений.

### Для фронтенд-команды — чеклист

- Подключить страницы «Журнал движений» и «Остатки» к новым
  эндпоинтам — контракты совпадают со страницей `/transactions`
  модуля finances.
- При вводе `q` показывать пользователю, что **поиск по UUID
  отключён** — для поиска по конкретному ID использовать
  структурные фильтры (`transfer_id`, `inventory_id`, ...).
- Для агрегатов (`summary.by_transfer_type`,
  `summary.by_inventory_type`) — ключи это `value` соответствующих
  enum'ов (`COURIER_LOAD`, `WAREHOUSE`, ...).

### Миграция / Deploy

Миграции БД не требуются (индексы уже доехали в предыдущем релизе
`c3f8a9d4e2b1_inventory_search_indexes`).

### Не входит в эту часть (Iteration 2)

- `?format=paged` для существующих `/transfers`, `/warehouses`,
  `/transports`, `/inventories/search`.
- Cursor-pagination и пресеты сохранённых фильтров (FRD §14).
- Отдельный эндпоинт `/stock-transactions/summary` (сейчас
  агрегаты inline в основном ответе).

---

## [Unreleased] — Senior Code Review fixes (блокеры продакшена)

Источник: `research/SENIOR_CODE_REVIEW_2026_04_18.md` (Итерация 1 roadmap).

### Fixed

#### Безопасность

- **C1** LIKE/ILIKE-инъекция `%`/`_` в `GET /backoffice/inventories/search?q=` устранена. Символы `\`, `%`, `_` во вводе теперь экранируются через общий хелпер `src/common/search.py::ilike_pattern` (перенесён из `src/modules/finances/search.py`, там оставлен реэкспорт). Без этой правки ввод `%%` превращал фильтр в полную выборку, ломая пагинацию и нагружая БД.
- **C4** Курьерский эндпоинт `GET /courier/inventory/my-stock` защищён правильным scope: было `Scope.CATALOG_READ` (справочник товаров), стало `Scope.INVENTORY_READ` (склад). Чтобы не ломать роль, `Role.COURIER` теперь включает `Scope.INVENTORY_READ` — курьер законно видит только собственную машину (IDOR-защита в сервисе по `user_id=courier.id` сохранена). Если фронт инспектирует scope из `/me` — у курьера появится `inventory:read`; никаких backoffice-эндпоинтов это не открывает.
- **C5** (обратная правка из предыдущего релиза) `Role.ACCOUNTANT` **больше не имеет** `Scope.INVENTORY_READ`. Ревью Senior-engineer пометило это как over-privilege (эндпоинтов `/stock-transactions`/`/balances` ещё нет; выдавать widcard-scope авансом — расширение attack-surface). Будет возвращено точечным scope `Scope.INVENTORY_STATEMENT_READ`, когда соответствующие эндпоинты будут готовы.

#### Целостность данных (append-only ledgers)

- **C3** Добавлены DB-уровневые CHECK-констрейнты — belt-and-suspenders к уже существующим триггерам (`update_account_balances`, `update_inventory_balances`). Триггеры — SPOF (ранее уже был инцидент с `$$`-quoting); CHECK гарантирует, что даже сломанный триггер не сможет вставить отрицательный остаток.
  - `accounts` → `ck_accounts_balance_non_negative` (`balance >= 0`).
  - `inventory_balances` → `ck_inventory_balances_quantity_non_negative` (`quantity >= 0`).
  - Миграция: `d7a2f91c4e68_ledger_check_constraints`.

#### API контракты

- **FAIL-1** Трейлинг-слэш на `/backoffice/users`: корневой роут регистрируется как `@router.get("")` вместо `@router.get("/")`. Благодаря `redirect_slashes=True` оба варианта URL (`/users` и `/users/`) работают; раньше запрос `GET /api/v1/backoffice/users` (без слэша) возвращал **307 Temporary Redirect**, что ломало httpx-клиенты без `follow_redirects` и все SPA, которые строят URL конкатенацией. Аналогичная унификация на `orders`-роутерах отложена — существующие тесты везде используют форму со слэшем, и массовая миграция требует согласованного обновления фронта.

### Changed

- Тест `tests/integration/test_courier_shift_close.py::test_shift_close_returns_stock_and_collects_cash` помечен `@pytest.mark.skip` (FAIL-2 в ревью): эндпоинт `POST /backoffice/shifts/close` и сервис смен отсутствуют в исходниках (только `.pyc` в `__pycache__`, которые удалены). Фича «закрытие смены курьера с возвратом стока и сбором нала» требует продуктового решения перед реализацией. См. Roadmap Итерация 1 п.6.

### Breaking Changes

**Для API-клиентов — нет.** Все правки scope/route либо расширяют (курьер получает `inventory:read`), либо обратно-совместимы (trailing-slash обрабатывается редиректом).

**Для ACCOUNTANT:** если в UI уже успели завязаться на scope `inventory:read` у бухгалтера (не должно было: эндпоинтов ещё нет) — после миграции токены старых сессий перестанут содержать этот scope. Действий не требуется: UI всё равно получал 404 на отсутствующих эндпоинтах.

### Миграция / Deploy

```bash
make upgrade   # применяет d7a2f91c4e68_ledger_check_constraints
```

Миграция CHECK-констрейнтов:
- Быстрая: `ALTER TABLE ... ADD CHECK` в PG 12+ помечается `NOT VALID` по-желанию, но в этой миграции мы валидируем сразу — данные уже корректны (триггер гарантирует).
- На проде перед применением рекомендуется проверить: `SELECT COUNT(*) FROM accounts WHERE balance < 0;` и `SELECT COUNT(*) FROM inventory_balances WHERE quantity < 0;` — оба должны быть 0. Если не ноль — это уже баг данных и миграция упадёт, выявив его.

### Что НЕ входит в этот релиз (следующие итерации ревью)

См. `research/SENIOR_CODE_REVIEW_2026_04_18.md` §7:

- **C2** Idempotency-ключи на `POST /transactions` и `/cashbox/accept-payment` — Итерация 2.
- **H1** `lazy="raise"` на всех bulk-relationship'ах (30+ мест) — Итерация 3.
- **H2** Перенос `*/dashboard_queries.py` в `src/application/dashboards/` (очистка cross-module импортов) — Итерация 4.
- **H3** `asyncio.gather` / bulk-update в contracts batch-джобах — Итерация 3.
- **H4** Rate limiting (slowapi + активация Redis) — Итерация 2.
- **H5** Дифференциация `IntegrityError` на UNIQUE / CHECK / FK subclasses — Итерация 2 (прекондиция для C2).
- **H6** Pin `sqlalchemy[asyncio]` до stable `>=2.0.36,<2.1` — Итерация 3.

---

## [Unreleased] — Inventory API: расширенные фильтры, поиск, пагинация (Iteration 1, частично)

Источник: `research/INVENTORY_SEARCH_FILTERS_FRD.md` Draft v4 (Senior review pass #2).

### Обзор

Первая часть релиза — **инфраструктурные изменения**, которые фронтенду не ломают ничего, но нужны, чтобы последующие коммиты со схемами/эндпоинтами/фильтрами деплоились инкрементально.

- Роль **`ACCOUNTANT`** теперь получает scope `inventory:read` — бухгалтер сможет читать будущие эндпоинты `/stock-transactions` и `/balances` (сейчас 403).
- В БД созданы **GIN-trigram и B-Tree индексы** под будущие фильтры на страницах склада (transfers, stock ledger, balances, warehouses, inventories/search). Используется существующее расширение `pg_trgm` (подключено finances-миграцией).
- **Никаких изменений в API-контрактах** в этой части релиза — существующие эндпоинты (`GET /transfers`, `GET /warehouses`, `GET /transports`, `GET /inventories/search`) работают как раньше.

### Added

#### Permissions (`src/core/security/permissions.py`)

- ~~`Role.ACCOUNTANT` → добавлен `Scope.INVENTORY_READ`.~~ **Откачено** Senior-review-правкой выше (C5): сейчас endpoints ещё не существуют, а широкий wildcard-scope расширяет attack-surface без пользы. Будет возвращено узким `Scope.INVENTORY_STATEMENT_READ`, когда `/stock-transactions` и `/balances` станут доступны.

#### Database indexes (Alembic `c3f8a9d4e2b1_inventory_search_indexes`)

Создаются через `CREATE INDEX CONCURRENTLY IF NOT EXISTS` в `autocommit_block` — в downtime/миграции не нуждаются:

- `ix_stock_transfer_created_at_id` — `stock_transfers (created_at DESC, id DESC) WHERE is_active = true` — основной sort/cursor key на списке накладных.
- `ix_stock_transfer_created_by` — `stock_transfers (created_by_id, created_at DESC) WHERE is_active = true` — фильтр «мои черновики» и «кто создал накладную».
- `ix_stock_transfer_accepted_by` — `stock_transfers (accepted_by_id, created_at DESC) WHERE accepted_by_id IS NOT NULL AND is_active = true` — фильтр «кто принимал».
- `ix_stock_transfer_reason_trgm` — GIN-trigram на `stock_transfers.reason WHERE reason IS NOT NULL` — подстрочный поиск по причине списания.
- `ix_stock_transaction_created_at_id` — `stock_transactions (created_at DESC, id DESC)` (**без `is_active`** — леджер append-only, концепта архивации нет) — cursor-пагинация будущего `/stock-transactions`.
- `ix_stock_transaction_product_created_at` — `stock_transactions (product_id, created_at DESC)` — журналы «движения товара X за период».
- `ix_inventory_name_trgm` — GIN-trigram на `inventories.name WHERE is_active = true` — поиск склада/транспорта по имени.
- `ix_product_name_trgm` — GIN-trigram на `products.name WHERE is_active = true` — JOIN-поиск по товарам в stock-ledger/transfers.
- `ix_user_username_trgm` — GIN-trigram на `users.username` (идемпотентно: уже создан finances-миграцией).
- `ix_identity_local_phone_digits_trgm` — GIN-trigram на нормализованных цифрах `identities.provider_identity_id` (только `provider = 'local'`) — поиск контрагента по подстроке телефона (без `+`, `-`, пробелов).
- `ix_phone_numbers_digits_trgm` — GIN-trigram на нормализованных цифрах `phone_numbers.phone` — поиск по дополнительным телефонам пользователя.

Downgrade — симметричный `DROP INDEX CONCURRENTLY IF EXISTS`, кроме `ix_user_username_trgm` (он принадлежит finances-миграции и удаляется её down-скриптом).

### Changed

_Ничего._ Существующие эндпоинты возвращают тот же shape; query-параметры не менялись; scope'ы на роутах прежние.

### Deprecated

_Ничего в этой части._

### Removed

_Ничего._

### Fixed

_Ничего._

### Breaking Changes

**Нет.** Изменения read-only и аддитивные.

### Для фронтенд-команды — чеклист на эту часть

- [x] Убедиться, что в UI для роли `ACCOUNTANT` не начали внезапно появляться кнопки/маршруты Inventory-модуля — они включаются **только** следующими релизами, когда будут готовы эндпоинты. Если роль-матрица на фронте «автоматически» строится по scope-ответу `/me` — сейчас у бухгалтера будет `inventory:read`, но страниц `/stock-transactions` и `/balances` в API пока нет (404). Добавьте feature-флаг или маршруты, которые появятся в след. релизе (см. FRD §15.1 п.5).

### Миграция / Deploy

```bash
make upgrade   # применяет c3f8a9d4e2b1_inventory_search_indexes
```

Миграция:
- Идемпотентна (`IF NOT EXISTS` везде).
- Не блокирует запись (`CONCURRENTLY`).
- На проде для 2M строк `stock_transactions` ожидается ~10–30s на каждый индекс — суммарно порядка 1–2 минут без блокировок.

### Не входит в эту часть

Следующими коммитами приедет (см. FRD §15.1):

- Новые эндпоинты `GET /backoffice/stock-transactions/`, `/stock-transactions/summary`, `/balances/`.
- Расширенные query-параметры на `GET /transfers` (мультизначные фильтры, `q`, `summary`, `format=paged`).
- `q`-parser (каналы: телефон, целое, текст; UUID-ввод → 422 `SEARCH_UUID_NOT_ALLOWED`).
- Новые Pydantic-схемы (`*Filter`, `*ListResponse`, `PaginationMeta`, `*Summary`).
- Новые коды ошибок (`QUANTITY_CONFLICT`, `PAGINATION_TOO_DEEP`, `CURSOR_INVALID`, `DATE_PRESET_CONFLICT`, `DATE_RANGE_INVALID`, `QUANTITY_RANGE_INVALID`, `SEARCH_*`).
- Deprecated-aliases старых query-параметров на `/transfers` (`type`, `from_date`, `to_date`, `warehouse_id`).

---

## [Unreleased] — Finances API: расширенные фильтры, поиск, пагинация

Источник: `research/FINANCES_SEARCH_FILTERS_FRD.md` v3.1 (Senior review).

### Обзор

- Переработаны эндпоинты `GET /api/v1/backoffice/finances/transactions`
  и `GET /api/v1/backoffice/finances/accounts`:
  новый набор фильтров, free-text поиск (`q`), inline-агрегаты (summary),
  расширенная форма ответа.
- **Backward compatibility сохранена**: старые query-параметры
  (`status`, `type`, `search`, `min_amount`, `max_amount`) принимаются
  как deprecated alias'ы. Старый ключ ответа (`transactions` / `accounts`)
  дублируется вместе с новым ключом `items` на время переходного периода
  (минимум 1 релиз).
- UUID в поиск (`q`) не принимается — искать по id нужно через `order_id`,
  `account_id` и т.д.
- Для производительности в БД добавлены GIN-trigram индексы
  (расширение `pg_trgm`) и B-Tree индексы по горячим полям.

### Added

#### Общие

- Новый ключ ответа для обоих эндпоинтов:
  ```json
  {
    "items":      [...],
    "pagination": { "mode": "offset",
                    "page": 1, "size": 50,
                    "total_count": 123, "total_pages": 3 },
    "summary":    { ... },
    "transactions": [...],   // alias для items, deprecated
    "accounts":     [...],   // alias для items, deprecated (только для /accounts)
    "total_count":  123      // deprecated
  }
  ```
- Новые коды ошибок (422 Unprocessable Entity):
  - `SEARCH_TOO_SHORT`   — `q` короче 2 символов.
  - `SEARCH_TOO_LONG`    — `q` длиннее 100 символов.
  - `SEARCH_UUID_NOT_ALLOWED` — в `q` передан UUID/длинный hex.
  - `DATE_RANGE_INVALID` — `date_from > date_to`.
  - `AMOUNT_RANGE_INVALID` — `amount_from > amount_to`.
  - `AMOUNT_CONFLICT`    — одновременно `amount_eq` и `amount_from/to`.
  - `PAGINATION_TOO_DEEP` — `page * size > 10_000`.

Формат всех ошибок (стандартный):
  ```json
  {
    "error": {
      "code": "SEARCH_UUID_NOT_ALLOWED",
      "message": "В поиске запрещён UUID...",
      "details": { ... }
    }
  }
  ```

#### `GET /finances/transactions` — новые query-параметры

| Параметр                  | Тип                                                                             | Описание                                                                                                         |
| ------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `q`                       | string(2..100)                                                                  | Free-text поиск по основанию проводки (`reason`), названию счетов и имени владельца (`username`). UUID запрещён. |
| `status_in`               | list of enum                                                                    | Мультивыбор статусов (`pending`/`completed`/`rejected`).                                                         |
| `direction`               | `incoming`/`outgoing`/`internal`                                                | Направление относительно `account_id` (требует `account_id`).                                                    |
| `from_account_id`         | uuid                                                                            | Конкретный счёт-источник.                                                                                        |
| `to_account_id`           | uuid                                                                            | Конкретный счёт-получатель.                                                                                      |
| `from_account_type_in`    | list of enum                                                                    | Мультивыбор типов счёта-источника.                                                                               |
| `to_account_type_in`      | list of enum                                                                    | Мультивыбор типов счёта-получателя.                                                                              |
| `order_status_in`         | list of enum                                                                    | Фильтр по статусам связанного заказа.                                                                            |
| `order_payment_method_in` | list of enum                                                                    | Фильтр по способу оплаты заказа.                                                                                 |
| `order_sale_type_in`      | list of enum                                                                    | Фильтр по типу продажи (`delivery`/`warehouse_pickup`).                                                          |
| `contract_id`             | uuid                                                                            | Транзакции по договору.                                                                                          |
| `contract_number`         | string                                                                          | Частичное совпадение по номеру договора.                                                                         |
| `client_id`               | uuid                                                                            | Все проводки где клиент — владелец from/to счёта.                                                                |
| `courier_id`              | uuid                                                                            | Все проводки где курьер — владелец from/to счёта.                                                                |
| `user_role_in`            | list of enum                                                                    | Роль владельца from/to счёта.                                                                                    |
| `verified_by_id`          | uuid                                                                            | Кто верифицировал.                                                                                               |
| `verified`                | bool                                                                            | `true` = только верифицированные, `false` = не верифицированные.                                                 |
| `has_order`               | bool                                                                            | `true` = только с `order_id`, `false` = без заказа (ручные).                                                     |
| `reason_search`           | string(2..100)                                                                  | Точечный поиск по `reason` (более узкий чем `q`).                                                                |
| `amount_eq`               | integer ≥ 0                                                                     | Точная сумма (взаимоисключает `amount_from`/`to`).                                                               |
| `amount_from`             | integer ≥ 0                                                                     | Минимальная сумма (замена `min_amount`).                                                                         |
| `amount_to`               | integer ≥ 0                                                                     | Максимальная сумма (замена `max_amount`).                                                                        |
| `date_preset`             | `today` / `yesterday` / `this_week` / `last_week` / `this_month` / `last_month` | Быстрый пресет диапазона (TZ: `Asia/Tashkent`). Взаимоисключает `date_from`/`date_to`.                           |
| `sort`                    | `created_at` (default)                                                          | Поле сортировки (пока только одно).                                                                              |
| `order`                   | `asc`/`desc` (default `desc`)                                                   | Направление.                                                                                                     |

#### `GET /finances/accounts` — новые query-параметры

| Параметр                      | Тип            | Описание                                                  |
| ----------------------------- | -------------- | --------------------------------------------------------- |
| `q`                           | string(2..100) | Поиск по названию счёта и имени владельца. UUID запрещён. |
| `type_in`                     | list of enum   | Мультивыбор типов.                                        |
| `user_id`                     | uuid           | Счета конкретного пользователя.                           |
| `user_role_in`                | list of enum   | Счета пользователей с ролями.                             |
| `balance_from` / `balance_to` | integer        | Диапазон баланса (может быть отрицательным).              |
| `is_in_credit`                | bool           | `true` = баланс < 0, `false` = ≥ 0.                       |
| `zero_balance`                | bool           | `true` = баланс = 0.                                      |
| `created_from` / `created_to` | date-time      | Диапазон даты создания счёта.                             |

#### Новые поля в схемах ответа

- `AccountResponse`:
  - *(без изменений)* `user_name` — уже присутствовал.
- `AccountShort` (используется во вложенных структурах транзакций):
  - **+ `user_name: string | null`**.
- `TransactionDetail`:
  - **+ `order_short_id: string | null`** — последние 8 hex-символов `order_id`
    (UUIDv7 timestamp-часть слева бесполезна, используем правую часть).
  - **+ `verified_by_name: string | null`** — ФИО/логин сотрудника,
    подтвердившего транзакцию.

#### `summary` (inline в ответе списка)

Возвращается всегда, считается по **тому же набору фильтров**, что и `items`,
но **без применения пагинации**.

Для `/transactions`:
```json
"summary": {
  "sum_amount": 1234567,
  "count_by_status": {
    "pending":   12,
    "completed": 430,
    "rejected":  1
  }
}
```

Для `/accounts`:
```json
"summary": {
  "sum_balance": 9999999,
  "count_by_type": {
    "client":  100,
    "courier": 5,
    "cash":    1
  }
}
```

### Deprecated

Следующие query-параметры работают, но будут удалены в следующей крупной
версии. В OpenAPI помечены как `deprecated=true`. Рекомендуется перейти
на новые имена.

| Старое имя                | Новое имя     |
| ------------------------- | ------------- |
| `status`                  | `status_in=…` |
| `min_amount`              | `amount_from` |
| `max_amount`              | `amount_to`   |
| `type` (на `/accounts`)   | `type_in=…`   |
| `search` (на `/accounts`) | `q`           |

Правило: если переданы оба — **новое имя имеет приоритет**, старое
игнорируется (с warning-логом на стороне бэкенда).

### Changed

- `GET /transactions` и `GET /accounts` теперь возвращают dict с ключом
  `items` + `pagination` + `summary`. Старые ключи (`transactions`,
  `accounts`, `total_count`) продолжают работать как алиасы.
- Валидация: `page * size > 10_000` — 422 `PAGINATION_TOO_DEEP`
  (офсет-пагинация на больших страницах требует cursor; появится в v2).

### Unchanged (не меняется)

- Аутентификация и скоупы: `FINANCES_READ` для обоих GET-эндпоинтов.
- Семантика создания/верификации/отклонения транзакций
  (`POST /transactions`, `PATCH /transactions/{id}/verify|reject`).
- Другие финансовые эндпоинты (`/dashboard`, `/couriers/summary`,
  `/clients/debts`, `/b2b-debts`, `/accounts/{id}/statement`).

### Планируется в следующей итерации (v2)

- Cursor-пагинация (`cursor=...&size=...`) для больших списков.
- Отдельный `GET /transactions/summary` / `/accounts/summary` — чтобы
  считать агрегаты без загрузки items (для дашбордов).
- `GET /finances/presets` — возврат готовых конфигураций фильтров для
  быстрых кнопок UI (фронт может пока хардкодить).
- Тонкая настройка q-детектора: digit-only → поиск по телефону,
  hex(8) → поиск по `order_short_id`, буквы+цифры → поиск по
  `contract_number` (сейчас все каналы объединены через OR).

### Миграция для фронтенда — чек-лист

1. Обновить типы ответа: добавить `items`, `pagination.total_pages`,
   `summary`. Старые поля можно оставить на переходный период, но
   рекомендуется сразу читать `items`.
2. Перейти со `search` → `q` на странице счетов.
3. Перейти с `min_amount`/`max_amount` → `amount_from`/`amount_to`.
4. Перейти со `status` (single) → `status_in` (list) на странице
   транзакций. Множественный выбор в UI теперь нативный.
5. Обработать новые коды ошибок 422 (показывать пользователю русские
   `error.message`).
6. Для любого поля поиска — **не пускать в `q` что-либо похожее на UUID**
   (фильтровать на клиенте заранее или показывать hint).

---
