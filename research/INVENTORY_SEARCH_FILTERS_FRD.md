# FRD — Фильтрация, поиск и пагинация в модуле «Склад / Инвентарь»

**Документ:** Functional Requirements Document
**Скоуп:** Backoffice Inventory module (`src/modules/inventory`) — страницы `Warehouses`, `Transports`, `Transfers`, `Stock Ledger`, `Inventories`, `Balances`
**Статус:** Draft v4 (senior-review pass #2 — каждое утверждение перепроверено по коду main)
**Связанные артефакты:**
- `research/FINANCES_SEARCH_FILTERS_FRD.md` — общий стиль/контракт (копируются соглашения §3)
- `research/dashboard_inventory.md`, `research/DASHBOARD_BRD.md`
- `src/modules/inventory/{models,schemas,repositories,services,enums,exceptions,uow,dependencies}.py`
- `src/modules/catalog/models.py` (`Product.name`, `Product.type`, `Product.attributes`; **`sku` в модели отсутствует** — см. §13 Q9)
- `src/modules/users/models.py` — `User.username` + `Identity(provider='local').provider_identity_id` (хранит телефон) + `PhoneNumber.phone` (доп. номера); таблицы `users.username` / `identities.provider_identity_id` / `phone_numbers.phone` **не индексированы под поиск** (только unique/FK-индексы)
- `src/api/v1/backoffice/{warehouses,transport,transfers,inventories}.py`
- `src/core/security/permissions.py`
- `alembic/versions/b2c4e8f1a7d3_finances_search_indexes.py` — существующий шаблон Alembic-миграции для `pg_trgm` индексов (наследуем стиль `autocommit_block` + `WHERE is_active = true`)

### TL;DR

Пять страниц склада (`/warehouses`, `/transports`, `/transfers`, **`/stock-transactions`** [новый], `/inventories/search`) получают полный набор **мультизначных фильтров + `q`** для человеческого поиска (название склада/машины, имя ответственного, телефон, название товара, причина списания). Пагинация — **offset** с `total_count` + `summary`; на самой горячей странице (журнал накладных) — дополнительно **cursor** для глубины и экспорта. **Поиск по UUID и любым его производным (включая «короткий ID» — хвост/префикс/hex-срез UUID) в продукте отсутствует полностью**: `q` никогда не принимает идентификаторы, а UI проставляет UUID структурными фильтрами (`warehouse_id`, `courier_id`, `product_id`, `order_id`, `route_sheet_id`) из выпадашек/автокомплита — пользователь не вводит и не копирует идентификаторы. Все изменения — backward-совместимы: существующие одиночные параметры остаются как deprecated aliases на один мажор.

### Сверка с кодом (опорные факты)

| Допущение                                                | Проверка в коде                                | Вывод                                                                                                                                                                                                                                                                                                                |
| -------------------------------------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `StockTransfer` имеет человеческий номер накладной       | `inventory/models.py` (класс `StockTransfer`)  | **Нет.** Человеческого номера накладной нет, и FRD его **не вводит** (UUID-поиск в продукте отсутствует полностью — см. §3). Пользователь находит накладную через фильтры по контрагенту/дате/типу/складу, а не по идентификатору.                                                                                   |
| `StockTransfer.status` / `type` индексированы колоночно  | `inventory/models.py` (`index=True` на колонках) | Да.                                                                                                                                                                                                                                                                                                                  |
| `StockTransfer.from_id` / `to_id` индексированы          | `inventory/models.py`                          | Да.                                                                                                                                                                                                                                                                                                                  |
| `StockTransfer.order_id` / `route_sheet_id` индексированы | `inventory/models.py`                          | Да, оба nullable.                                                                                                                                                                                                                                                                                                     |
| `StockTransfer.created_by_id` / `accepted_by_id`         | `inventory/models.py`                          | **Не индексированы колоночно.** §10.3 добавит индексы.                                                                                                                                                                                                                                                                |
| `StockTransfer.reason`                                   | `inventory/models.py`                          | `Mapped[str \| None]`, без индекса. §10.3 — trigram GIN с `WHERE reason IS NOT NULL`.                                                                                                                                                                                                                                |
| Композитный FK `(transfer_id, from_id, to_id)` на леджере | `inventory/models.py` — `StockTransaction.__table_args__`, `ForeignKeyConstraint` `fk_stock_transaction_strict_route` → `stock_transfers(id, from_id, to_id)` | Строгий инвариант: проводка леджера не может отклониться от маршрута своей накладной. FRD-фильтры `transfer_id` + `from_id`/`to_id` на `/stock-transactions` всегда согласованы по этому FK (§6.1).                                                                                                                   |
| `StockTransaction` строго append-only                    | `inventory/repositories.py` (`archive`/`restore`/`delete` → `NotImplementedError`) + PG-триггеры | На `/stock-transactions` поля `is_active` / «архивные» не существует; cursor-пагинация по `(created_at, id)` даёт стабильный порядок без дрейфа.                                                                                                                                                                     |
| Есть ли эндпоинт на `StockTransaction`                   | `grep StockTransaction src/api/v1` → **пусто** | **Нет.** FRD предлагает новый `GET /backoffice/stock-transactions` (§6).                                                                                                                                                                                                                                             |
| `Balance` (`inventory_balances`) — материализованная таблица | `inventory/models.py` + триггер `trigger_update_inventory_balances` (функция `update_inventory_balances`) в `src/infrastructure/database/scripts/update_inventory_balances.sql` | Обновляется PG-триггером `AFTER INSERT` на `stock_transactions` (UPDATE/DELETE там кидают exception). **Дополнительно** триггер гарантирует `quantity >= 0` для всех non-virtual инвентарей (`VIRTUAL_VENDOR`/`VIRTUAL_LOSS` — исключение). Следовательно `GET /balances` читает уже согласованные данные без on-the-fly пересчёта; `has_stock`/`low_stock` строятся на `balance.quantity > 0` без гонок (§13 Q7).                                                                                                                                                               |
| `StockTransfer.is_active` в чтении                       | `inventory/repositories.py::search_transfers` | Текущий метод **не фильтрует** по `is_active` — вернёт архивные транзферы, если появятся. На практике `archive()` на `StockTransfer` нигде не вызывается (`grep` по `src/`), колонка зарезервирована. FRD закрепляет default `is_active=true` (§5.2) и добавляет tri-state семантику фильтра. |
| `search_transfers` возвращает total                      | `inventory/repositories.py`                    | **Нет.** Возвращает `Sequence[StockTransfer]` без счётчика. Для offset-ответа `{total_count, total_pages}` (§4.4) потребуется `SELECT COUNT(*)` с теми же WHERE. §12 (слой repositories) явно это включает в scope изменений.                                                                                                                                                                                                                                         |
| `InventoryRepository.search_inventories`                 | `inventory/repositories.py`                    | `ILIKE '%' \|\| q \|\| '%'` по `inventories.name` без индекса и **без экранирования `%` / `_`** → seq-scan + потенциально «поиск-всё» при `q='%'`. §3.6 и §10.3 — trigram + обязательное экранирование wildcards.                                                                                                    |
| `search_transfers`                                       | `inventory/repositories.py` / `inventory/services.py` | Принимает single-value `status`, `transfer_type`, `from_inventory_id`, `to_inventory_id`, `warehouse_id`, `warehouse_owner_id`, `date_from`/`date_to`. Нет `q`, массивов, `created_by_id`, `order_id`, `product_id`, `reason_search`, `quantity`-диапазонов, `summary`. FRD расширяет.                               |
| `GET /backoffice/transfers/` — текущие query-параметры   | `src/api/v1/backoffice/transfers.py`           | `page`, `size`, `type`, `from_date`/`to_date` (**`date`, не `datetime`** — конвертируются в `datetime` start/end-of-day в UTC локальными хелперами), `warehouse_id`. Scope — **`LOGISTICS_TRANSFER`** (used as READ-scope; оставлено as-is — STOREKEEPER/ADMIN его уже имеют). Ответ — `list[TransferResponse]` без обёртки. |
| `STOREKEEPER` scope-фильтр                               | `transfers.py` + `warehouses.py` + `services.py` | Уже реализован: ADMIN видит всё, STOREKEEPER → `warehouse_owner_id = current_admin.id`; на `/warehouses` — `owner_id`. FRD закрепляет инвариант и распространяет на новые эндпоинты (§3.2).                                                                                                                          |
| `get_transports`                                         | `inventory/services.py`                        | Принимает `skip`, `limit`, `user_id`, возвращает `tuple[list[Transport], int]`. В роутере `total` отбрасывается → direct-list. Для `format=paged` (§11.2) достаточно обернуть существующий tuple.                                                                                                                    |
| `get_all_warehouses_with_balances`                       | `inventory/repositories.py`                    | Без фильтрации/пагинации. `owner_id`-скоуп уже есть. §5.4 закрепляет `size`-лимит на будущее.                                                                                                                                                                                                                        |
| `GET /backoffice/inventories/search`                     | `src/api/v1/backoffice/inventories.py`         | `q: str = Query("", ...)` — пустая строка разрешена; фильтр `type: InventoryType \| None`; `limit` 1..200. FRD делает `q` обязательным (2..100) с deprecation-периодом (§11.2).                                                                                                                                      |
| `InventoryType` enum                                     | `inventory/enums.py`                           | `WAREHOUSE`, `COURIER`, `CLIENT`, `VIRTUAL_LOSS`, `VIRTUAL_VENDOR`.                                                                                                                                                                                                                                                  |
| `TransferType` enum                                      | `inventory/enums.py`                           | 9 значений (`COURIER_LOAD`, `COURIER_RETURN`, `CLIENT_DELIVERY`, `CLIENT_RETURN`, `LOSS_WRITE_OFF`, `INVENTORY_FINDING`, `INITIAL_BALANCE`, `WAREHOUSE_SALE`, `WAREHOUSE_TARA_RETURN`).                                                                                                                              |
| `TransferStatus` enum                                    | `inventory/enums.py`                           | `DRAFT`, `COMPLETED`, `CANCELLED`.                                                                                                                                                                                                                                                                                    |
| RBAC — чтение склада                                     | `src/core/security/permissions.py` (`ROLE_SCOPES`) | `INVENTORY_READ` → `ADMIN`, `STOREKEEPER`, `CASHIER`. `TRANSPORTS_READ` → `ADMIN`, `STOREKEEPER`. **`ACCOUNTANT` не имеет `INVENTORY_READ`** — для `/stock-transactions` и `/balances` его необходимо добавить (§13 Q2, §12).                                                                                         |
| `Product.sku` / штрихкод                                 | `src/modules/catalog/models.py` (класс `Product`) | **Отсутствует.** Поля: `name`, `type`, `price`, `attributes (JSONB)`, `returnable_item_id`. Канал «поиск по SKU» в `q` **не реализуется** в MVP (§13 Q9, §15.2).                                                                                                                                                      |
| Телефон пользователя                                     | `src/modules/users/models.py`                  | `Identity(provider='local').provider_identity_id` (основной) + `PhoneNumber.phone` (доп. контактные). Колонок `users.phone` / `users.email` **нет**; `users.username` — ФИО / название компании. Q-канал «телефон» идёт через JOIN двух таблиц (§4.2), индексы — §10.3.                                              |
| `pg_trgm` extension                                      | `alembic/versions/b2c4e8f1a7d3_finances_search_indexes.py` | Включён финансовой миграцией. Миграция inventory повторно создаёт `CREATE EXTENSION IF NOT EXISTS pg_trgm` (идемпотентно) и создаёт индексы через `autocommit_block() + CREATE INDEX CONCURRENTLY IF NOT EXISTS` — тот же стиль, что и у финансов.                                                                   |
| Статусы накладной влияют на остатки                      | `inventory/services.py` + PG-триггеры          | `DRAFT` **не** пишет в `stock_transactions`; `COMPLETED` — пишет; `CANCELLED` — отменяет. UI обязан разделять «активные/черновики/отменённые» — §4.1 `status_in`.                                                                                                                                                    |

---

## 1. Контекст и цели

### 1.1. Бизнес-проблема

Складской оператор (STOREKEEPER / ADMIN) в рабочий день:
- Принимает **накладные**: проводит приёмку от поставщика, оприходует, списывает, проверяет загрузку курьеров. Документов — 30–300 в день.
- Ищет **товар**: «где лежит 19л вода Bonaqua?», «сколько пустой 5л тары на машинах?».
- Контролирует **тару у клиентов**: кто должен, сколько, с какого времени.
- Расследует **потери**: кто списал `LOSS_WRITE_OFF` за вчера, по какой причине.
- Проводит **инвентаризацию**: сравнивает факт с системой, фиксирует `INVENTORY_FINDING` / корректировки.

Кассир (CASHIER) при самовывозе проверяет: «на каком складе есть 19л, ближе всего к клиенту?».

Бухгалтер (ACCOUNTANT) — смотрит журнал леджера (`stock_transactions`), чтобы связать финансовую проводку с физическим движением товара.

Курьер (COURIER) — в своём интерфейсе видит только **свой** транспорт (остатки). В backoffice не участвует.

### 1.2. Боли текущей реализации

1. **`GET /backoffice/transfers`** принимает 4 структурных фильтра и всё. Нет:
   - поиска по контрагенту (курьер, клиент, кладовщик — имя/телефон),
   - поиска по `order_id`, `route_sheet_id`, `product_id`,
   - фильтра по `status` (есть только `type`!),
   - диапазона количеств,
   - q (free-text по товару/причине/короткому ID документа),
   - `summary` — пользователь не видит «сколько единиц прошло за период».
2. **Нет эндпоинта на `stock_transactions`** — чистый леджер недоступен. Журнал движений восстанавливается только обходом всех накладных.
3. **`GET /backoffice/warehouses/`** возвращает **все склады без пагинации и без фильтров по наполнению** — на 50+ складах начнёт тормозить. Нельзя спросить «склады с нулевым остатком 19л», «склады, где есть товар X».
4. **`GET /backoffice/transport/`** — фильтр только по `user_id`. Нет `q`, нет фильтра «только с загрузкой», «перегружен сверх лимита» (на будущее, когда будет лимит).
5. **`GET /backoffice/inventories/search`** использует `ILIKE '%' || q || '%'` на неиндексированной `inventories.name` **без экранирования `%` / `_`** — seq-scan плюс уязвимость «поиск-всё» при вводе `%`. `q` обязателен по смыслу, но `q=""` пропускается без ошибки.
6. **Нет `summary`**: бухгалтер не видит «за выбранный период прошло 1240 полных бутылей и 320 возвратов тары».
7. **Pagination-глубина не ограничена** — на append-only леджере (`stock_transactions`) это взрывает БД через год.

### 1.3. Цели FRD

1. Зафиксировать **полный набор фильтров** на каждой странице склада, закрывающий ≥95% реальных операционных сценариев.
2. Определить **семантику `q`** с правилами нормализации и ранжирования, идентичную правилам FINANCES FRD (чтобы обучение оператора не дублировалось).
3. Ввести **новый эндпоинт** `GET /backoffice/stock-transactions` с фильтрами и summary — закрыть слепую зону «леджер товаров».
4. Ввести **offset + cursor** пагинацию на горячих страницах (`transfers`, `stock-transactions`). На холодных (`warehouses`, `transports`) — offset достаточно.
5. Зафиксировать **индексы** и требования к p95 latency.
6. Сохранить **backward compatibility** для существующих query-параметров (deprecated aliases).
7. Учесть **scope-ограничения** (`STOREKEEPER` → только свои склады) на уровне всех новых фильтров.

### 1.4. Не в скоупе

- UI/UX макеты (дизайн-система и конкретные компоненты — `dashboard_ui.md`).
- Экспорт в XLSX/CSV (отдельный FRD «Inventory Exports»).
- Дашборд-KPI для склада (покрыто в `research/dashboard_inventory.md`).
- Client/Courier self-service страницы (у них отдельный UI-скоуп).
- Изменение модели (новые колонки, нормализация названий) — только индексы.
- Аналитические агрегаты по периодам (movement stats по неделям и т.п.) — в dashboard.
- Client-inventory (тара у клиента) как отдельная страница — покрывается на странице клиента, не здесь.

---

## 2. Персоны и сценарии использования

| Роль                   | Типовой сценарий                                                        | Критичные фильтры                                                               |
| ---------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| ADMIN                  | «Покажи все `LOSS_WRITE_OFF` за сегодня с причиной `брак`»              | `type_in=LOSS_WRITE_OFF`, `date_preset=today`, `reason_search=брак`             |
| ADMIN                  | «Все отменённые накладные кладовщика Иванова за неделю»                 | `status_in=CANCELLED`, `created_by_id`, `date_preset=this_week`                 |
| ADMIN (аудит)          | «Журнал движений 19л воды за месяц между складом Центр и машиной АВ123» | `product_id`, `from_id`, `to_id`, `date_preset=this_month` (stock-transactions) |
| STOREKEEPER            | «Мои накладные в статусе `DRAFT` (надо провести)»                       | `status_in=DRAFT`, scope авто-применяется `warehouse_owner_id=me`               |
| STOREKEEPER            | «Загрузка курьеров сегодня по маршруту `RS-042`»                        | `type_in=COURIER_LOAD`, `route_sheet_id`, `date_preset=today`                   |
| STOREKEEPER            | «Где лежит Bonaqua 19л и сколько?»                                      | Страница `/balances?product_id=...`                                             |
| CASHIER                | «На каком складе есть 19л в наличии?»                                   | `/warehouses?product_id=...&has_balance=true&sort=balance_desc`                 |
| ACCOUNTANT             | «Леджер движений за период для связки с финансовыми проводками»         | `/stock-transactions?date_from&date_to&order_id`                                |
| ADMIN (инвентаризация) | «Все находки и списания этого месяца»                                   | `type_in=INVENTORY_FINDING,LOSS_WRITE_OFF`, `date_preset=this_month`            |

---

## 3. Принципы проектирования

Наследуются из FINANCES FRD §3 (сервер-driven фильтрация, AND-композиция, массивы для OR, shareable URL, tiebreaker по `id`, UTC-даты + `date_preset` в `Asia/Tashkent`, экранирование wildcards). Специфика инвентаря:

0. **Нет поиска по UUID и по его производным.** Свободный ввод `q` **никогда** не матчится против идентификаторов — ни полных UUID, ни их хвоста/префикса/hex-среза, ни коротких «номеров документа». Любой ввод, который выглядит как hex-последовательность ≥ 8 символов, подозрительный на UUID (32 hex подряд, канонический UUID с дефисами, префикс `0x…`) — отклоняется 422 `SEARCH_UUID_NOT_ALLOWED`. UI подставляет UUID **только** структурными фильтрами (`warehouse_id`, `order_id`, `product_id`, `created_by_id`, `route_sheet_id` и т.д.), источник — выпадающие списки/автокомплит по именам. В ответах API не возвращается никакого «короткого ID» для копирования.
1. **Целое количество.** Все `quantity`-фильтры — `int`, `ge=1` для `quantity_from`, `ge=1` для `quantity_to` (нулевое движение невозможно — CHECK `quantity > 0` на `stock_transactions` и `stock_transfer_items`, см. `inventory/models.py`).
2. **Scope-хардening.** `STOREKEEPER` **всегда** получает неявный фильтр «только мои склады». Сервер добавляет его после применения явных фильтров — если пользователь передал чужой `warehouse_id`, сервер не выбрасывает 403, а **возвращает пустой результат** (чтобы не «светить» существование чужих складов в UI; 403 отдаётся только на `GET /{id}`).
3. **Статус ≠ `is_active`.** Для накладных активной называется запись с `status IN (DRAFT, COMPLETED)`; `CANCELLED` отдельно. `is_active=false` на `StockTransfer` — зарезервировано, сейчас не используется.
4. **Леджер строго append-only.** На странице `/stock-transactions` фильтра «архивные» нет — его просто не существует.
5. **`quantity` — всегда положительная.** Знак движения определяется парой `(from_id, to_id)`: если нужна «сумма товара прибывшая на склад» — считается `SUM(quantity) WHERE to_id = :inv`, «убывшая» — `WHERE from_id = :inv`. FRD вводит фильтр `direction` (`incoming`/`outgoing`/`any`) для страницы леджера.
6. **Экранирование wildcards в `q`.** Перед подстановкой в `ILIKE` символы `%`, `_`, `\` в пользовательском вводе **обязательно** экранируются (`sqlalchemy`-эквивалент: `escape='\\'`). Текущий `search_inventories` этого не делает — §8.1 и §10.3 закрывают. Пустой/whitespace-only `q` после нормализации — 422 `SEARCH_TOO_SHORT`.

---

## 4. Страница «Журнал накладных» (Transfers) — `GET /backoffice/transfers`

Это **главная горячая страница** модуля. На неё операторы заходят десятками раз в день.

### 4.1. Структурные фильтры

| Параметр              | Тип                | Описание                                                                                             | Примечания                                                                                                                                                                          |
| --------------------- | ------------------ | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `status_in`           | `TransferStatus[]` | Multi-select: `DRAFT`, `COMPLETED`, `CANCELLED`                                                      | **Новый фильтр**: в текущем API статус вообще не фильтруется. По умолчанию — все три.                                                                                               |
| `type_in`             | `TransferType[]`   | Multi-select: 9 значений enum                                                                        | Заменяет single `type`; deprecated-alias (§8.3)                                                                                                                                     |
| `from_id`             | `uuid`             | Конкретный склад-источник                                                                            | Alias старого `from_inventory_id`                                                                                                                                                   |
| `to_id`               | `uuid`             | Конкретный склад-получатель                                                                          | Alias старого `to_inventory_id`                                                                                                                                                     |
| `from_type_in`        | `InventoryType[]`  | JOIN `inventories` — тип склада-источника                                                            | Пример: «все отгрузки с `WAREHOUSE` куда угодно»                                                                                                                                    |
| `to_type_in`          | `InventoryType[]`  | Аналогично для склада-получателя                                                                     | Пример: «всё, что ушло клиентам» = `to_type_in=CLIENT`                                                                                                                              |
| `warehouse_id`        | `uuid`             | Любая сторона документа — `from_id` или `to_id` равен `warehouse_id`                                 | Для «показать всё, что касалось этого склада». Уже есть.                                                                                                                            |
| `inventory_id_in`     | `uuid[]`           | Множественная версия `warehouse_id` — OR между элементами, ANY-side                                  | Для «мои склады» (STOREKEEPER).                                                                                                                                                     |
| `created_by_id`       | `uuid`             | Кто создал документ                                                                                  | Поле есть в модели, без колоночного индекса — добавляется в §10.3                                                                                                                  |
| `accepted_by_id`      | `uuid`             | Кто принял                                                                                           | Поле есть, nullable, без колоночного индекса — §10.3                                                                                                                                |
| `is_accepted`         | `bool`             | `true` = `accepted_by_id IS NOT NULL`                                                                | Для «висящие неподтверждённые накладные» — критично для STOREKEEPER                                                                                                                 |
| `order_id`            | `uuid`             | Точный заказ (проставляется UI из контекста заказа)                                                  | Уже есть на моделе, индекс есть. В API не фильтруется — **добавляется**                                                                                                             |
| `transfer_id`         | `uuid`             | Точная накладная (используется только для внутренней навигации `/transfers/{id}`, не для списка)     | В списочном эндпоинте игнорируется; оставлен в таблице для полноты                                                                                                                  |
| `route_sheet_id`      | `uuid`             | ID маршрутного листа                                                                                 | Для `COURIER_LOAD`; колоночный индекс уже есть на модели. Проставляется UI из выбранного маршрута, не вводится руками                                                               |
| `has_order`           | `bool`             | `true` = `order_id IS NOT NULL`                                                                      | Разделить «клиентские» документы и «внутренние» (LOAD/RETURN/FIND/WRITE_OFF)                                                                                                        |
| `product_id`          | `uuid`             | EXISTS по `stock_transfer_items.product_id`                                                          | Для «накладные, где фигурирует 19л Bonaqua». JOIN `stock_transfer_items`, индекс там есть.                                                                                          |
| `product_id_in`       | `uuid[]`           | Множественная версия                                                                                 | OR по списку товаров                                                                                                                                                                |
| `quantity_total_from` | `int`              | `SUM(items.quantity) >= N`                                                                           | Через подзапрос с GROUP BY                                                                                                                                                          |
| `quantity_total_to`   | `int`              | `SUM(items.quantity) <= N`                                                                           |                                                                                                                                                                                     |
| `reason_search`       | `string`           | `reason ILIKE '%value%'`                                                                             | Для `LOSS_WRITE_OFF` причин; trigram-индекс §7.2                                                                                                                                    |
| `date_from`           | `datetime`         | `created_at >= date_from`                                                                            | UTC                                                                                                                                                                                 |
| `date_to`             | `datetime`         | `created_at <= date_to`                                                                              | UTC, inclusive (§3.8 FINANCES FRD)                                                                                                                                                  |
| `date_preset`         | `enum`             | `today`, `yesterday`, `this_week`, `last_week`, `this_month`, `last_month`, `last_7d`, `last_30d`    | Взаимоисключающ с `date_from`/`date_to` → 422                                                                                                                                       |
| `warehouse_owner_id`  | `uuid`             | Только для системного использования (админский scope); для STOREKEEPER — подставляется автоматически | Не принимается из UI пользователем (игнорируется с warning если роль — STOREKEEPER)                                                                                                 |

### 4.2. Free-text поиск (`q`)

**Принцип**: `q` принимает **только человекочитаемые данные** — имена, телефоны, текстовые фрагменты (причина, название товара). Идентификаторы (UUID, их хвост/префикс, любые «короткие ID», hex-последовательности ≥ 8 символов) — 422 `SEARCH_UUID_NOT_ALLOWED`. Для выбора конкретной накладной/заказа/склада UI использует структурные UUID-фильтры, заполняемые из выпадашек.

`q: string, min_length=2, max_length=100`.

**Каналы детектора** (OR, не взаимоисключающие):

| #   | Паттерн                                              | Где ищем                                                                                                                                                                                  | Пример                      |
| --- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| 1   | Телефон (`^\+?\d[\d\s\-\(\)]{7,19}$` → чистые цифры) | JOIN `inventories.user → users → identities (provider=local)` и `phone_numbers` — суффикс совпадает, для **обеих сторон** документа (`from_inventory.user`, `to_inventory.user`)          | `+998 90 123…`              |
| 2   | `^[0-9]{1,9}$` целое (≤ 9 цифр, не телефон)          | `SUM(items.quantity) = int(q)` через подзапрос; полезно для «найти накладную на 300 бутылей»                                                                                              | `300`                       |
| 3   | Текст (≥ 2 символов, не попал в 1–2)                 | `inventories.name` (обеих сторон), `users.username` (обоих ответственных), `stock_transfers.reason`, **`products.name`** через JOIN `items → products` — ILIKE с wildcards (trigram §7.2) | `Азизов`, `Bonaqua`, `брак` |

**UUID-detector (pre-check, до каналов)**: любая из форм — 422 `SEARCH_UUID_NOT_ALLOWED`:
- канонический UUID `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`;
- «голый» 32-hex `^[0-9a-f]{32}$`;
- hex-фрагмент `^[0-9a-f]{8,}$` (≥ 8 hex подряд без других символов) — отсекает попытки ввести хвост/префикс UUID;
- `0x…` префикс.

**JOIN'ы подключаются по каналу** — если q не похож на телефон, JOIN `identities/phone_numbers` не делается (экономия). Если q цифровой, но длиной 1 — 422 `SEARCH_TOO_SHORT`.

**UX-требования к фронту:**
- В строке накладной UI показывает: дату/время создания, тип, статус, имя создателя, имена обеих сторон (`from_inventory.name` / `to_inventory.name`), суммарное количество позиций, (для `LOSS_WRITE_OFF`) `reason`. **Идентификатор накладной (UUID) не показывается пользователю и не копируется из интерфейса** — детализация доступна по клику через навигацию.
- Плейсхолдер `q`: «Товар, склад, курьер, клиент, телефон, причина».

### 4.3. Сортировка

| `sort`           | Поле                                   | По умолчанию     |
| ---------------- | -------------------------------------- | ---------------- |
| `created_at`     | `created_at`                           | **default DESC** |
| `status`         | enum order (DRAFT→COMPLETED→CANCELLED) |                  |
| `type`           | enum order (алфавитный)                |                  |
| `quantity_total` | `SUM(items.quantity)`                  |                  |

Формат: `sort=created_at&order=desc`. Tiebreaker — `id DESC`. Недопустимое значение — 422.

### 4.4. Пагинация

Поддерживаются оба режима (аналогично FINANCES §4.4):

- **Offset** (default): `page` (ge=1), `size` (1..100, default 20). `page*size > 10_000` → 422 `PAGINATION_TOO_DEEP`.
- **Cursor**: `cursor` (opaque base64 от `(created_at, id)`), `size` — для «Загрузить ещё» и экспорта.

Ответ (offset):

```json
{
  "items": [ TransferResponse ],
  "pagination": {
    "mode": "offset",
    "page": 1, "size": 20, "total_count": 142, "total_pages": 8
  },
  "summary": {
    "total_count": 142,
    "total_quantity": 4820,
    "count_by_status": { "DRAFT": 4, "COMPLETED": 135, "CANCELLED": 3 },
    "count_by_type": {
      "COURIER_LOAD": 58, "CLIENT_DELIVERY": 60, "LOSS_WRITE_OFF": 6, "...": "..."
    }
  }
}
```

`summary` считается по тем же WHERE, **без** `ORDER BY / LIMIT`. Для cursor-режима не возвращается (ресурсоёмко; по запросу `include_summary=true` — только на первой странице).

### 4.5. Обогащение ответа

`TransferResponse` (`src/modules/inventory/schemas.py`, класс `TransferResponse`) уже неплохо обогащён — `from_inventory`, `to_inventory`, `created_by`, `accepted_by` как вложенные схемы. Добавляем:
- `items_count: int` — количество позиций в документе (cheap: length массива, уже selectinload).
- `total_quantity: int` — `SUM(items.quantity)` (через лёгкий hybrid-property или аннотация в запросе, чтобы не поднимать N+1 при 100 строках).

**`id` (UUID) возвращается**, так как нужен UI для навигации (ссылка на `/transfers/{id}`), но **не отображается как «номер документа»**. Никаких `transfer_short_id` / `order_short_id` в ответе нет — UI не должен показывать идентификаторы пользователю.

### 4.6. Валидация ошибок

Все — через `AppException`-иерархию (`src/core/exceptions.py`), сообщения на русском.

| Правило                                             | Код ошибки                      |
| --------------------------------------------------- | ------------------------------- |
| `date_from > date_to`                               | `DATE_RANGE_INVALID` (422)      |
| `quantity_total_from > quantity_total_to`           | `QUANTITY_RANGE_INVALID` (422)  |
| `date_preset` + `date_from`/`date_to`               | `DATE_PRESET_CONFLICT` (422)    |
| `q.length < 2`                                      | `SEARCH_TOO_SHORT` (422)        |
| `q.length > 100`                                    | `SEARCH_TOO_LONG` (422)         |
| `q` похож на UUID / его фрагмент / hex ≥ 8 подряд   | `SEARCH_UUID_NOT_ALLOWED` (422) |
| `page*size > 10_000`                                | `PAGINATION_TOO_DEEP` (422)     |
| битый/просроченный `cursor`                         | `CURSOR_INVALID` (422)          |

---

## 5. Страница «Склады» (Warehouses) — `GET /backoffice/warehouses/`

### 5.1. Текущее поведение

Эндпоинт возвращает **весь список складов** без пагинации (`WarehouseService.get_warehouses_with_balances` в `src/modules/inventory/services.py` делает один `SELECT` без `LIMIT`). На 10–30 складах это ок, но FRD добавляет пагинацию/фильтры, не ломая обратной совместимости: при отсутствии `page`/`size` сервер возвращает до 100 записей, как сейчас (логируя `warning` о неявной пагинации).

### 5.2. Структурные фильтры

| Параметр                      | Тип      | Описание                                                                                              |
| ----------------------------- | -------- | ----------------------------------------------------------------------------------------------------- |
| `q`                           | `string` | По имени склада + `users.username` ответственного + телефон (каналы из §4.2)                          |
| `user_id`                     | `uuid`   | Материально ответственный (владелец) — auto для STOREKEEPER                                           |
| `is_active`                   | `bool`   | Включать ли архивные (default `true` — только активные; `false` — только архивные; явный `null` — все) |
| `has_product_id`              | `uuid`   | EXISTS подзапрос: на складе есть баланс по товару                                                     |
| `has_product_id_in`           | `uuid[]` | Хотя бы один из товаров                                                                               |
| `stock_below`                 | `int`    | Склады, где суммарный баланс по всем товарам < N (либо по конкретному `has_product_id` если он задан) |
| `stock_above`                 | `int`    | Аналогично «выше»                                                                                     |
| `has_stock`                   | `bool`   | `true` — хотя бы одна позиция с `balance.quantity > 0`                                                |
| `created_from` / `created_to` | `date`   | Когда создан склад                                                                                    |

### 5.3. Сортировка

| `sort`           | Поле                     | По умолчанию    |
| ---------------- | ------------------------ | --------------- |
| `name`           | `inventories.name`       | **ASC default** |
| `created_at`     | `created_at`             | DESC            |
| `total_quantity` | `SUM(balances.quantity)` | DESC            |

Tiebreaker — `id ASC` (для стабильности при равных именах).

### 5.4. Пагинация

Offset-only (`page`, `size` 1..100, default 50). Лимит глубины тот же (page*size ≤ 10 000). Cursor не нужен — складов физически мало.

### 5.5. Контракт ответа

```json
{
  "items": [ WarehouseDetailResponse + { "total_quantity": 1280, "products_count": 12 } ],
  "pagination": { "mode": "offset", "page": 1, "size": 50, "total_count": 14, "total_pages": 1 },
  "summary": {
    "total_warehouses": 14,
    "total_quantity_across_all": 18430,
    "by_product_type": { "WATER": 11200, "CONTAINER": 6800, "EQUIPMENT": 430 }
  }
}
```

`total_quantity` / `products_count` — hybrid properties, считаются в JOIN-aggregation без N+1.

---

## 6. Страница «Журнал движений» (Stock Ledger) — **НОВЫЙ** `GET /backoffice/stock-transactions/`

Закрывает слепую зону: сейчас чистый леджер недоступен через API. Scope — `INVENTORY_READ` (уже имеют ADMIN, STOREKEEPER, CASHIER). Для роли **ACCOUNTANT** `INVENTORY_READ` сейчас **не выдан** — его нужно добавить в `ROLE_SCOPES[Role.ACCOUNTANT]` в `src/core/security/permissions.py` (это Python-код, не Alembic-миграция — scope-mapping не хранится в БД). Правку деплоим вместе с релизом этого FRD (см. §13 Q2, §12, §15.1). Курьерам/клиентам доступ не выдаётся.

### 6.1. Структурные фильтры

| Параметр                | Тип                       | Описание                                                           |
| ----------------------- | ------------------------- | ------------------------------------------------------------------ |
| `product_id`            | `uuid`                    | Движения конкретного товара                                        |
| `product_id_in`         | `uuid[]`                  | Множественный                                                      |
| `product_type_in`       | `ProductType[]`           | JOIN `products.type`: `WATER`, `CONTAINER`, `EQUIPMENT`            |
| `from_id`               | `uuid`                    | Склад-источник                                                     |
| `to_id`                 | `uuid`                    | Склад-получатель                                                   |
| `inventory_id`          | `uuid`                    | Любая сторона (OR с `from_id`/`to_id`)                             |
| `direction`             | `incoming\|outgoing\|any` | Только в паре с `inventory_id`; без него — игнорируется            |
| `from_type_in`          | `InventoryType[]`         | JOIN `inventories` стороны from                                    |
| `to_type_in`            | `InventoryType[]`         | Аналогично для to                                                  |
| `transfer_id`           | `uuid`                    | Все проводки конкретной накладной                                  |
| `transfer_type_in`      | `TransferType[]`          | JOIN `stock_transfers.type`                                        |
| `order_id`              | `uuid`                    | JOIN `stock_transfers.order_id`                                    |
| `created_by_id`         | `uuid`                    | JOIN `stock_transfers.created_by_id` (реальный автор проводки)     |
| `quantity_from`         | `int`                     | `quantity >= N`                                                    |
| `quantity_to`           | `int`                     | `quantity <= N`                                                    |
| `quantity_eq`           | `int`                     | Точное значение; взаимоисключающ с range — 422 `QUANTITY_CONFLICT` |
| `date_from` / `date_to` | `datetime`                | UTC                                                                |
| `date_preset`           | `enum`                    | Как в §4.1                                                         |

### 6.2. Free-text `q`

Каналы:
1. Телефон — JOIN через `inventory → user → identities/phone_numbers` для обеих сторон.
2. Целое — `quantity = int(q)` (если `^[0-9]{1,9}$` и не телефон).
3. Текст — `products.name`, `inventories.name` (обеих сторон), `users.username` (создатель), `stock_transfers.reason` (JOIN, hit'ится через `LOSS_WRITE_OFF`).

UUID-запрет и нормализация — как в §4.2 (hex ≥ 8 подряд, канонический UUID, `0x…` — 422). Никакого «short-id» канала нет.

### 6.3. Сортировка

| `sort`       | Поле            | Default  |
| ------------ | --------------- | -------- |
| `created_at` | `created_at`    | **DESC** |
| `quantity`   | `quantity`      |          |
| `product`    | `products.name` |          |

Tiebreaker — `id DESC` (UUIDv7 монотонный). **Критично**: на append-only леджере cursor по `(created_at, id)` даёт стабильную пагинацию без дрейфа.

### 6.4. Пагинация

- **Offset** (default): `page`, `size` (1..100, default 50). Глубина ≤ 10 000.
- **Cursor** (настоятельно рекомендуется для экспорта и «Загрузить ещё»): `cursor` base64(`created_at|id`).

### 6.5. Контракт ответа

```json
{
  "items": [ StockTransactionResponse + {
      "from_inventory": { "id": "...", "name": "Склад Центр", "type": "WAREHOUSE" },
      "to_inventory":   { "id": "...", "name": "Машина АВ123", "type": "COURIER" },
      "transfer_type": "COURIER_LOAD"
  } ],
  "pagination": { "mode": "offset", "page": 1, "size": 50, "total_count": 18420, "total_pages": 369 },
  "summary": {
    "total_transactions": 18420,
    "total_quantity": 62300,
    "by_transfer_type": { "COURIER_LOAD": 22400, "CLIENT_DELIVERY": 28100, "LOSS_WRITE_OFF": 120, "...": "..." },
    "by_product": [
      { "product_id": "...", "product_name": "Bonaqua 19л", "total_quantity": 12400 },
      { "product_id": "...", "product_name": "Тара 19л", "total_quantity": 11200 }
    ]
  }
}
```

`summary.by_product` ограничивается top-10 по `total_quantity`; остальное — «прочие».

### 6.6. Дополнительно: `GET /backoffice/stock-transactions/summary`

Отдельный лёгкий endpoint для дашбордов: те же фильтры (§6.1), возвращает только блок `summary`. Кэш TTL 30s по каноничному хешу фильтров — опционально (§10).

---

## 7. Страница «Транспорт» (Transports) — `GET /backoffice/transport/`

### 7.1. Фильтры

| Параметр               | Тип          | Описание                                                                                                           |
| ---------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------ |
| `q`                    | `string`     | По `name`, `users.username` ответственного курьера, телефон курьера                                                |
| `user_id`              | `uuid`       | Фильтр по курьеру (как сейчас)                                                                                     |
| `user_id_in`           | `uuid[]`     | Множественная версия                                                                                               |
| `is_active`            | `bool`       | Архивные или нет                                                                                                   |
| `has_stock`            | `bool`       | У курьера есть хотя бы одна позиция с `balance.quantity > 0`                                                       |
| `has_product_id`       | `uuid`       | Есть баланс по товару                                                                                              |
| `last_activity_within` | `int` (days) | Был ли `stock_transaction` в последние N дней (EXISTS subquery по `stock_transactions.from_id = id OR to_id = id`) |

### 7.2. Сортировка / пагинация

- `sort`: `name` (default ASC), `created_at DESC`, `last_activity_at DESC` (через LATERAL / correlated subquery).
- Offset-only (`page`, `size` 1..100, default 20).

### 7.3. Контракт ответа

```json
{
  "items": [ TransportResponse + {
    "total_quantity": 180, "last_activity_at": "2026-04-18T13:45:00Z", "courier_name": "Иванов"
  } ],
  "pagination": { "mode": "offset", "page": 1, "size": 20, "total_count": 14, "total_pages": 1 },
  "summary": {
    "total_couriers": 14, "active_couriers": 12, "total_quantity_on_wheels": 2240
  }
}
```

---

## 8. Страница «Универсальный поиск» (Inventories Search) — `GET /backoffice/inventories/search`

Существующий эндпоинт остаётся, но усиливается.

### 8.1. Фильтры

| Параметр       | Тип                        | Описание                                                                                              |
| -------------- | -------------------------- | ----------------------------------------------------------------------------------------------------- |
| `q`            | `string`, **required**     | 2..100 символов. Каналы §4.2 (телефон, текст — `name`, `user.username`). UUID-like ввод отклоняется 422.          |
| `type_in`      | `InventoryType[]`          | Заменяет single `type`                                                                                |
| `user_role_in` | `Role[]`                   | JOIN users.role — поиск «инвентарь всех B2B клиентов»                                                 |
| `has_stock`    | `bool`                     | Хотя бы одна позиция в балансе                                                                        |
| `is_active`    | `bool`                     |                                                                                                       |
| `limit`        | `int` (1..200, default 50) |                                                                                                       |

**Scope**: STOREKEEPER не видит `CLIENT` / `COURIER` чужих владельцев. Для CLIENT-инвентарей возвращать только если явно разрешено через отдельный scope (§10).

### 8.2. Ответ

```json
{
  "items": [ InventorySearchResult + { "user_name": "Клиент Ромашка", "has_stock": true } ],
  "total_count": 12
}
```

Пагинация не требуется — это autocomplete-эндпоинт, верхняя граница `limit=200`.

---

## 9. Страница «Остатки по товару» (Balances Cross-view) — **НОВЫЙ** `GET /backoffice/balances/`

Кросс-вью на `inventory_balances`. Даёт бухгалтеру/складу ответ «где находится товар X?» одним запросом.

### 9.1. Фильтры

| Параметр            | Тип               | Описание                                               |
| ------------------- | ----------------- | ------------------------------------------------------ |
| `product_id`        | `uuid`            | Чаще всего используется                                |
| `product_id_in`     | `uuid[]`          |                                                        |
| `product_type_in`   | `ProductType[]`   |                                                        |
| `inventory_type_in` | `InventoryType[]` | Фильтр на тип склада (default: `WAREHOUSE`, `COURIER`) |
| `inventory_id_in`   | `uuid[]`          | Конкретные места                                       |
| `user_id`           | `uuid`            | Остатки конкретного пользователя (клиент, курьер)      |
| `quantity_from`     | `int`             | `balance.quantity >= N`                                |
| `quantity_to`       | `int`             | `<=`                                                   |
| `nonzero_only`      | `bool`            | default `true`                                         |
| `q`                 | `string`          | Имя товара / имя склада (trigram)                      |

### 9.2. Сортировка

- `quantity` (DESC default), `product_name` (ASC), `inventory_name` (ASC).

### 9.3. Пагинация

Offset (`page`, `size` 1..100, default 50), cursor не обязателен.

### 9.4. Ответ

```json
{
  "items": [
    {
      "product": { "id": "...", "name": "Bonaqua 19л", "type": "WATER" },
      "inventory": { "id": "...", "name": "Склад Центр", "type": "WAREHOUSE" },
      "quantity": 420
    }
  ],
  "pagination": { "...": "..." },
  "summary": {
    "total_quantity": 12400,
    "by_inventory_type": { "WAREHOUSE": 9200, "COURIER": 2800, "CLIENT": 400 }
  }
}
```

---

## 10. Индексы и перформанс

### 10.1. Ожидаемые объёмы (Y+1)

- `stock_transfers`: до 300k строк.
- `stock_transactions`: до 2M строк (append-only → растёт линейно).
- `inventory_balances`: до 50k (product × inventory).
- `inventories`: до 5k (включая все CLIENT — 1 на клиента).

### 10.2. Существующие индексы (проверено)

- `stock_transfers`: `(type)`, `(status)`, `(from_id)`, `(to_id)`, `(order_id)`, `(route_sheet_id)` — колоночные (`models.py`).
- `stock_transactions`: `(product_id)`, `(transfer_id)`, `(from_id)`, `(to_id)`, `idx_st_product_from (product_id, from_id)`, `idx_st_product_to (product_id, to_id)`.
- `inventories`: `(type)` колоночный, `idx_inventory_user_type (user_id, type)`, уникальный частичный `uq_active_courier_inventory`.
- `inventory_balances`: UNIQUE `(inventory_id, product_id)` + отдельный `index=True` на `product_id` → фильтры по `inventory_id` (композит) и по `product_id` (отдельный) — оба покрыты. Поиска по `(product_id, inventory_id)` без `product_id` — нет, но это пригодится в §9 через цепочку `product_id_in → uq-by-inventory`.
- `stock_transfer_items`: `(transfer_id)`, `(product_id)`.

### 10.3. Дополнительные индексы

Стиль — как в `alembic/versions/b2c4e8f1a7d3_finances_search_indexes.py`: `autocommit_block()` + `CREATE INDEX CONCURRENTLY IF NOT EXISTS`. `CREATE EXTENSION` идемпотентен (`IF NOT EXISTS`) — повторное создание не вредит.

```sql
-- Общее расширение (идемпотентно; уже включено финансовой миграцией)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- TRANSFERS: основной sort/cursor key
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_stock_transfer_created_at_id
  ON stock_transfers (created_at DESC, id DESC) WHERE is_active = true;

-- TRANSFERS: создатель / приёмщик (не индексированы колоночно)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_stock_transfer_created_by
  ON stock_transfers (created_by_id, created_at DESC)
  WHERE is_active = true;
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_stock_transfer_accepted_by
  ON stock_transfers (accepted_by_id, created_at DESC)
  WHERE accepted_by_id IS NOT NULL AND is_active = true;

-- TRANSFERS: trigram на reason (для `reason_search` и ветки q-text)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_stock_transfer_reason_trgm
  ON stock_transfers USING gin (reason gin_trgm_ops)
  WHERE reason IS NOT NULL;

-- STOCK_TRANSACTIONS: главный ключ пагинации леджера
-- (is_active не применяем — леджер append-only)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_stock_transaction_created_at_id
  ON stock_transactions (created_at DESC, id DESC);

-- STOCK_TRANSACTIONS: product + date для журналов «товар за период»
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_stock_transaction_product_created_at
  ON stock_transactions (product_id, created_at DESC);

-- INVENTORIES: trigram на name (для q-text и search_inventories)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_inventory_name_trgm
  ON inventories USING gin (name gin_trgm_ops)
  WHERE is_active = true;

-- INVENTORY_BALANCES: partial on nonzero (для has_stock / low_stock)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_inventory_balance_nonzero
  ON inventory_balances (inventory_id, product_id)
  WHERE quantity > 0;

-- INVENTORY_BALANCES: product-first для кросс-вью «где товар X»
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_inventory_balance_product_inventory
  ON inventory_balances (product_id, inventory_id, quantity DESC);

-- PRODUCTS: trigram на name (для q-text на `/transfers`, `/stock-transactions`, `/balances`)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_product_name_trgm
  ON products USING gin (name gin_trgm_ops)
  WHERE is_active = true;

-- USERS.username — trigram (shared с финансовым FRD; уже создан финансовой миграцией)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_username_trgm
  ON users USING gin (username gin_trgm_ops)
  WHERE is_active = true;

-- IDENTITIES / PHONE_NUMBERS — поиск по суффиксу/подстроке цифр телефона
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_identity_local_phone_digits_trgm
  ON identities USING gin (
    (regexp_replace(provider_identity_id, '\D', '', 'g')) gin_trgm_ops
  ) WHERE provider = 'local';

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phone_numbers_digits_trgm
  ON phone_numbers USING gin (
    (regexp_replace(phone, '\D', '', 'g')) gin_trgm_ops
  );
```

Expression-индексы на `RIGHT(id::text, 8)` и аналоги **не создаются** — short-id / UUID-поиска нет.

⚠ **asyncpg memory-нюанс**: миграция содержит `regexp_replace(... , '\D', ...)` — без PL/pgSQL и без `$$`, `text()`-wrap не требуется. Если в будущем понадобится `$$`-dollar-quoting (например, для триггеров) — оборачивать через `sa.text()`, не форматировать SQL-форматтером (см. репо-memo про asyncpg dollar-quoting).

### 10.4. SLA

| Эндпоинт                               | p95 target | Комментарий                                                |
| -------------------------------------- | ---------- | ---------------------------------------------------------- |
| `GET /transfers` (offset, 1–2 фильтра) | < 250 мс   | Обычно ≤ 1–2k matches, горячие индексы                     |
| `GET /transfers?q=...`                 | < 400 мс   | Trigram + expression-индексы                               |
| `GET /stock-transactions` (cursor)     | < 150 мс   | Append-only + composite index `(created_at, id)`           |
| `GET /stock-transactions` (offset)     | < 300 мс   | При глубине ≤ 10k                                          |
| `GET /warehouses`                      | < 200 мс   |                                                            |
| `GET /inventories/search?q=...`        | < 200 мс   | Trigram на `name`                                          |
| `GET /balances` (product_id)           | < 150 мс   | `idx_inventory_balance_product_inventory` прямое попадание |

### 10.5. Анти-паттерны

- `COUNT(*)` на `stock_transactions` без верхней границы `date_to` — запрещено (полный скан 2M). Ограничение глубины offset-пагинации `page*size ≤ 10_000` (§4.4) делает default-`COUNT(*)` допустимым только для «узких» фильтров; для широких — `HEAD`-ответ должен отдавать `{items, pagination: {mode: "cursor"}}` без `total_count`.
- `selectinload(StockTransfer.items)` в списочных эндпоинтах без ограничения `size` — взрывает в N+1 при `size=100` × среднее 5 items. **Использовать**: легковесный aggregated count через `func.array_length(...)` или отдельный `func.count()` по `items` в subquery — детали в `services.py`.
- В inventory-моделях `lazy="raise"` **не выставлен** (в отличие от `orders/models.py`, `users/models.py`). Это значит, что любой доступ к `Inventory.balances` / `StockTransfer.items` без явного `selectinload` внутри async-контекста вызовет `MissingGreenlet`. При рефакторе репо в §12 держать все `.balances`/`.items` под явным eager-load'ом — **не полагаться** на `lazy="raise"` как на защиту.

---

## 11. Контракт API (сводка)

### 11.1. Эндпоинты

| Метод   | Путь                                                | Scope                        |
| ------- | --------------------------------------------------- | ---------------------------- |
| GET     | `/api/v1/backoffice/warehouses/`                    | `INVENTORY_READ`             |
| GET     | `/api/v1/backoffice/transport/`                     | `TRANSPORTS_READ`            |
| GET     | `/api/v1/backoffice/transfers/`                     | `LOGISTICS_TRANSFER`         |
| GET     | `/api/v1/backoffice/transfers/summary`              | `LOGISTICS_TRANSFER`         |
| GET     | `/api/v1/backoffice/inventories/search`             | `INVENTORY_READ`             |
| **GET** | **`/api/v1/backoffice/stock-transactions/`**        | **`INVENTORY_READ`** (новый) |
| **GET** | **`/api/v1/backoffice/stock-transactions/summary`** | **`INVENTORY_READ`** (новый) |
| **GET** | **`/api/v1/backoffice/balances/`**                  | **`INVENTORY_READ`** (новый) |

### 11.2. Backward compatibility

- `GET /transfers`: сегодняшние query-параметры этого эндпоинта — `page`, `size`, `type`, `from_date`/`to_date` (`date`), `warehouse_id`. FRD сохраняет их все как deprecated aliases (`type_in` / `date_from`-`date_to` (`datetime`) / `warehouse_id_in` wins при конфликте). Для `from_date`/`to_date` (`date`) сохраняется текущая семантика «start-of-day / end-of-day в UTC» (см. хелперы `date_to_datetime_start`/`_end` в `src/api/v1/backoffice/transfers.py`) — FRD не меняет поведение, только добавляет datetime-вариант `date_from`/`date_to`. Новые фильтры из §4.1 (`status_in`, `from_id`, `to_id`, `created_by_id`, `order_id`, `product_id`, диапазоны) вводятся под новыми именами, в сервисе/репозитории `from_inventory_id`/`to_inventory_id` уже существуют и будут переиспользованы. Shape ответа в переходный период: **оба** варианта — текущий `list[TransferResponse]` (direct array) и расширенный `{items, pagination, summary}` — переключение по флагу `?format=paged` (default `paged=false` на один мажор, затем инвертируется). В OpenAPI старый shape помечается `@deprecated`.
- `GET /transport`: старый ответ — direct `list[TransportResponse]` — остаётся; расширенный shape доступен по `?format=paged`.
- `GET /warehouses`: то же правило. Default shape пока остаётся direct-list, чтобы не ломать UI в релизе.
- `GET /inventories/search`: `q=""` сейчас разрешён (и возвращает `[]`-like); после релиза FRD — 422 `SEARCH_TOO_SHORT`. Deprecation-warning один релиз.
- Новые эндпоинты (`/stock-transactions`, `/balances`) — без legacy.

### 11.3. Ошибки

Стандартный формат `{ "error": { "code": ..., "message": ..., "details": ... } }` (`src/api/exceptions/handlers.py`). Коды §4.6 и §6 (`QUANTITY_CONFLICT`, `DATE_RANGE_INVALID`, `PAGINATION_TOO_DEEP`, `CURSOR_INVALID`, `SEARCH_TOO_SHORT`, `SEARCH_TOO_LONG`, `SEARCH_UUID_NOT_ALLOWED`, `DATE_PRESET_CONFLICT`, `QUANTITY_RANGE_INVALID`). Все сообщения — на русском.

---

## 12. Влияние на слои кода

| Слой                                      | Изменения                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `inventory/schemas.py`                    | Ввести `TransferFilter`, `StockTransactionFilter`, `WarehouseFilter`, `TransportFilter`, `BalanceFilter`, `InventorySearchFilter`; ввести `PaginationMeta` (offset+cursor), summary-схемы (`TransferSummary`, `StockTransactionSummary`, `WarehouseSummary`, `TransportSummary`, `BalanceSummary`) и соответствующие `*ListResponse`. Расширить `TransferResponse` (`items_count`, `total_quantity`). Никаких `*_short_id` полей вводить не нужно.                                                                                                                                                 |
| `inventory/repositories.py`               | Переписать `search_transfers`: **добавить парный `count_transfers_with_filters`** (те же WHERE без `ORDER BY`/`LIMIT`/`selectinload`), aliased `Inventory` для from/to, JOIN `users` + `identities` + `phone_numbers` (через q-детектор), JOIN `stock_transfer_items` + `products`, aggregated `SUM(items.quantity)`. Добавить `get_transfers_cursor`, `get_transfers_summary`. Новый репозиторий-метод `get_stock_transactions_with_filters`, `get_stock_transactions_cursor`, `get_stock_transactions_summary` (JOIN `stock_transfers` + `inventories` from/to + `products`). Расширить `get_all_warehouses_with_balances` фильтрами (`stock_below` через HAVING). Новый `get_balances_view(filters)`. |
| `inventory/services.py`                   | Ввести `q`-parser в `src/modules/inventory/search.py` (аналог финансового). `StockTransferService.search_transfers` принимает Pydantic-фильтр целиком и возвращает `TransferListResponse`. Новый `StockLedgerService` с методами `list`, `summary`. `WarehouseService.get_warehouses_with_balances` принимает фильтр + пагинацию.                                                                                                                                                                                                                                                                |
| `inventory/uow.py`                        | Добавить репозитории для чтения смежных таблиц (`users`, `identities`, `phone_numbers`, `products`) — **только SELECT**, запись в эти таблицы из inventory-модуля запрещена (DDD).                                                                                                                                                                                                                                                                                                                                                                                                               |
| `inventory/dependencies.py`               | Новые `get_stock_ledger_service`, `get_balance_service`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `api/v1/backoffice/transfers.py`          | Переписать `GET /` с полным набором query-параметров §4.1; добавить `GET /summary`. Backward-compat через `format=paged`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `api/v1/backoffice/warehouses.py`         | Добавить query-параметры §5.2, `format=paged`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `api/v1/backoffice/transport.py`          | Добавить `q`, `has_stock`, `last_activity_within`, `format=paged`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `api/v1/backoffice/inventories.py`        | Добавить `type_in`, `user_role_in`, `has_stock`, валидация `q` (2..100).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `api/v1/backoffice/stock_transactions.py` | **Новый файл** — роуты §6.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `api/v1/backoffice/balances.py`           | **Новый файл** — роуты §9.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `api/v1/backoffice/__init__.py`           | Монтирование двух новых роутеров.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `core/security/permissions.py`            | **Добавить `Scope.INVENTORY_READ` в `ROLE_SCOPES[Role.ACCOUNTANT]`** — иначе бухгалтер не откроет `/stock-transactions` и `/balances` (сейчас у него только `FINANCES_READ`, `BILLS_READ`, `CONTRACTS_READ`, `USERS_READ`). Остальные scope'ы (`LOGISTICS_TRANSFER` на `/transfers`) сохраняются as-is.                                                                                                                                                                                                                                                                                             |
| `alembic/versions/`                       | Миграция `inventory_search_indexes` — §10.3.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Тесты                                     | Unit: q-детектор (телефон / int / text; UUID-like ввод в любой форме → 422 `SEARCH_UUID_NOT_ALLOWED`). Integration: каждый фильтр happy+edge, cursor-стабильность на append-only, backward-compat old params, scope STOREKEEPER не видит чужие склады. Perf-smoke: 500k `stock_transactions`.                                                                                                                                                                                                                                                                                                    |

DDD-инвариант: чтение чужих таблиц (`users`, `identities`, `phone_numbers`, `products`) из inventory-репозиториев — **только SELECT** через `load_only`/`selectinload`, без mutations. Никаких `password_hash` в SELECT-листе.

---

## 13. Открытые вопросы / зависимости

| #   | Вопрос                                             | Статус     | Решение                                                                                                                                                                                                                                                                                                                     |
| --- | -------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `route_sheet` как сущность                         | **Закрыт**  | `StockTransfer.route_sheet_id: uuid` фильтруется как структурный UUID (UI передаёт его из выбранного маршрута). Поиск/ввод идентификатора маршрута в `q` не поддерживается. Человекочитаемый `route_sheet_number` — отдельный FRD routes-модуля.                                                                    |
| 2   | Scope `ACCOUNTANT` на `/stock-transactions`        | **Закрыт** | Сейчас `ACCOUNTANT` имеет `FINANCES_READ`/`FINANCES_WRITE`/`BILLS_READ`/`CONTRACTS_READ`/`USERS_READ`, но **не имеет** `INVENTORY_READ`. Для чтения леджера движений товаров ему нужен RO-доступ — добавить `Scope.INVENTORY_READ` в `ROLE_SCOPES[Role.ACCOUNTANT]` в `src/core/security/permissions.py` (Python-код, не Alembic-миграция) вместе с релизом (см. §15.1 п.7).                                                                                                                                                    |
| 3   | `pg_trgm` в prod                                   | **Закрыт** | Разделяется с финансовым FRD. миграция финансов идёт первой, inventory-миграция лишь создаёт индексы.                                                                                                                                                                                                                       |
| 4   | Short-id коллизии                                  | **Закрыт** | Не применимо: short-id функциональности в продукте нет. Пользователь не ищет по идентификаторам, коллизии хвостов UUID нерелевантны.                                                                                                                                                                        |
| 5   | Default shape transfers API                        | **Открыт** | В релизе — `?format=paged=false` default (direct list). Через 1 мажор — переключить default в `paged`. Зафиксировать в CHANGELOG.                                                                                                                                                                                           |
| 6   | CLIENT-инвентари в поиске                          | **Открыт** | Сейчас `/inventories/search` отдаёт все типы. В UX — STOREKEEPER не работает с клиентскими инвентарями; скрыть `CLIENT` / `VIRTUAL_*` для `STOREKEEPER`-роли и показать только по запросу `type_in=CLIENT`.                                                                                                                 |
| 7   | `stock_below` / `stock_above` семантика            | **Открыт** | Считать ли «пустой склад» как `stock=0`? Если да — `has_product_id` без `has_stock=true` вернёт склады, где была позиция с нулём, что, вероятно, не то, что ожидает пользователь. MVP: `stock_below/above` работают только в паре с `has_product_id` (иначе игнорируются с warning).                                        |
| 8   | Кэш `summary`                                      | **Открыт** | MVP без кэша. Порог — если `GET /summary` > 150ms p95 на прод-данных.                                                                                                                                                                                                                                                       |
| 9   | `product.sku` / штрихкод                           | **Закрыт** | В `Product` полей `sku` / `barcode` **нет** (проверено — `src/modules/catalog/models.py`). Поля модели: `name`, `type`, `price`, `attributes (JSONB)`, `returnable_item_id`. Канал 4 в `q` **не вводится** в MVP. Nice-to-have: если появится колонка — добавить 4-й канал и trigram-индекс `ix_product_sku_trgm` в v2 (§15.2).  |
| 10  | Двойное обновление `inventory_balances` при чтении | **Закрыт** | Триггер `trigger_update_inventory_balances` на `AFTER INSERT` в `stock_transactions` синхронно делает `INSERT ... ON CONFLICT ... DO UPDATE` в `inventory_balances` (два ряда — `from_id` с отрицательным дельтой, `to_id` с положительным) и в том же statement проверяет `quantity >= 0` для non-virtual inventories. UPDATE/DELETE на `stock_transactions` вызывают `RAISE EXCEPTION`. Следовательно `GET /balances` читает согласованные данные без on-the-fly-пересчёта. Источник — `src/infrastructure/database/scripts/update_inventory_balances.sql`.                                                                                                                                                                         |

---

## 14. Saved views (Presets)

Чтобы STOREKEEPER / ADMIN не собирали одни и те же фильтры каждое утро:

| Preset                          | Страница    | Фильтры                                                                             |
| ------------------------------- | ----------- | ----------------------------------------------------------------------------------- |
| `transfers.drafts_mine`         | Transfers   | `status_in=DRAFT`, scope auto                                                       |
| `transfers.today_losses`        | Transfers   | `type_in=LOSS_WRITE_OFF`, `date_preset=today`                                       |
| `transfers.today_courier_loads` | Transfers   | `type_in=COURIER_LOAD`, `date_preset=today`                                         |
| `transfers.pending_acceptance`  | Transfers   | `status_in=COMPLETED`, `is_accepted=false`                                          |
| `ledger.today_by_product`       | StockLedger | `date_preset=today`, `sort=quantity_desc`                                           |
| `warehouses.low_stock_water`    | Warehouses  | `has_product_id=:WATER_MAIN`, `stock_below=100`                                     |
| `transport.idle_couriers`       | Transport   | `last_activity_within=3`, `has_stock=true` (3 дня не было движений, но товар висит) |
| `balances.zero_but_expected`    | Balances    | `product_id=...`, `quantity_to=0`, `inventory_type_in=WAREHOUSE`                    |

API: `GET /api/v1/backoffice/inventory/presets` — список (hardcoded server-side). Передача `?preset=transfers.drafts_mine` — сервер накладывает фильтры, явные query-параметры пользователя переопределяют. MVP: только серверные пресеты (enum в коде).

---

## 15. Roadmap

### 15.1. Iteration 1 (MVP этого FRD)

1. Schemas: `*Filter`, `*ListResponse`, `PaginationMeta`, `*Summary`.
2. Ошибки: новые коды `QUANTITY_CONFLICT`, `PAGINATION_TOO_DEEP`, `CURSOR_INVALID`, `SEARCH_*`, `DATE_PRESET_CONFLICT`, `DATE_RANGE_INVALID`, `QUANTITY_RANGE_INVALID` (shared с финансами через общий `core/exceptions.py` — не дублировать).
3. `q`-parser в `inventory/search.py` (3 канала: телефон, целое, текст) + UUID-detector (pre-check).
4. `search_transfers` — полная перезапись + парный `count_transfers_with_filters` + cursor + summary.
5. Новые эндпоинты: `/stock-transactions/`, `/stock-transactions/summary`, `/balances/`.
6. Миграция `inventory_search_indexes` (§10.3).
7. **Правка `src/core/security/permissions.py`: добавить `Scope.INVENTORY_READ` в `ROLE_SCOPES[Role.ACCOUNTANT]`** — без этого бухгалтер получит 403 на `/stock-transactions` и `/balances`. Код-правка, без отдельной Alembic-миграции (scope-mapping хранится в Python).
8. Backward-compat: `?format=paged` на 3 существующих эндпоинтах.
9. Тесты unit (q-детектор) + integration (happy+edge на фильтр, scope STOREKEEPER, ACCOUNTANT теперь читает `/stock-transactions`).
10. CHANGELOG для фронтендера: новые query-параметры, shape ответа, коды ошибок, deprecated aliases — на русском.

### 15.2. Iteration 2 (next PR)

- Cursor-режим на `/transfers` (сейчас только offset).
- Отдельный `/transfers/summary` endpoint (сейчас inline).
- Persisted personal saved views — таблица `user_inventory_presets(user_id, name, filters_json)`.
- Relevance-ранжирование в `q` через `pg_trgm.similarity()` — только при подтверждённой UX-потребности.
- `product.sku` в каналах `q` (если поле появится).
- Кэш `summary` (Redis TTL 30s).
- Фильтр `transfers.has_mismatched_balance` (подозрение на расхождение факт/система) — аналитика, требует отдельной выкладки.

---

## 16. Out of scope (финальная фиксация)

- Изменение схемы БД (новых колонок, нормализации telefonov, переименований) — только индексы.
- Экспорт в XLSX/CSV — отдельный FRD.
- UI-макеты и дизайн-токены — `dashboard_ui.md`.
- Аналитические ряды (тренды за N месяцев) — dashboard-домен.
- Client self-service страницы тары — отдельный скоуп.
- `route_sheet` как полноценная сущность с человеческим номером.
- Автоматические алерты «low stock < min_stock» — отдельный FRD «Inventory Alerts».
