# FRD — Фильтрация, поиск и пагинация на страницах «Финансы» и «Транзакции»

**Документ:** Functional Requirements Document
**Скоуп:** Backoffice Finances module (`src/modules/finances`) — страницы `Accounts` и `Transactions`
**Статус:** Draft v3 (Senior review applied)
**Связанные артефакты:**
- `research/DASHBOARD_BRD.md`, `research/dashboard_finance.md`
- `src/modules/finances/{models,schemas,repositories,services}.py`
- `src/modules/users/models.py` (User, Identity, PhoneNumber)
- `src/modules/orders/models.py` (Order — **без human-readable `number`**)
- `src/modules/contracts/models.py` (Contract — **c уникальным `number`**)
- `src/api/v1/backoffice/finances.py`

### TL;DR

Страницы `/accounts` и `/transactions` получают полноценный набор **мультизначных фильтров + одно поле `q`** для человеческого поиска (телефон, имя, номер договора, короткий ID заказа, сумма, текст причины). Пагинация — **offset** по умолчанию (с `total_count` и `summary`) + **cursor** для глубоких выборок и экспорта. Поиск по UUID через `q` **явно запрещён** (422) — длинные UUID-ы пользователи не набирают; для навигации UI использует структурные фильтры (`order_id`, `account_id`, `client_id`…), проставляемые по клику. Все изменения — backward-совместимые: существующие single-value параметры остаются как aliases на один релиз.

### Сверка с кодом (опорные факты)

| Допущение                                           | Проверка в коде                          | Вывод                                                                                                                                                                                                                                        |
| --------------------------------------------------- | ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| У `Order` есть человеческий `number`                | `src/modules/orders/models.py`           | **Нет.** В UI показывается 8-символьный short-id из **случайного хвоста** UUIDv7 (`RIGHT(order_id::text, 8)`), а не из префикса — см. §4.1 и пояснение ниже (UUIDv7-collision).                                                              |
| У `Contract` есть `number`                          | `src/modules/contracts/models.py:35`     | **Есть**, `String(50)`, `unique`. Используется для поиска B2B-транзакций.                                                                                                                                                                    |
| Телефон хранится в `users.identities`               | `src/modules/users/models.py:51-98`      | Да: `Identity.provider_identity_id` при `provider=LOCAL` = телефон. Доп. номера — в `phone_numbers.phone` (UNIQUE, `String(20)`). **Данные НЕ нормализованы при записи** — см. §4.2 про двойную нормализацию.                                 |
| Роль пользователя индексирована                     | `src/modules/users/models.py:119`        | `index=True` — фильтр `user_role_in` безопасен.                                                                                                                                                                                              |
| `Transaction.verified_by_id` есть и индексирован    | `src/modules/finances/models.py:107-113` | Да. Резолв имени — JOIN на `users`.                                                                                                                                                                                                          |
| `Transaction.created_by_id`                         | Не существует в модели                   | Фильтр **вне MVP**, нужна миграция (§10.1).                                                                                                                                                                                                  |
| `pg_trgm` уже установлен                            | `alembic/versions/*.py`                  | **Не установлен.** Миграция FRD добавит `CREATE EXTENSION IF NOT EXISTS pg_trgm`.                                                                                                                                                            |
| `Order.sale_type` индексирован                      | `orders/models.py:94`                    | Да.                                                                                                                                                                                                                                          |
| `Order.payment_method` индексирован                 | `orders/models.py:46-56`                 | **Нет** — колонка без `index=True`. Миграция §7.2 добавляет `idx_order_payment_method`, чтобы фильтр `order_payment_method_in` не уходил в seq-scan.                                                                                         |
| `Order.status` индексирован                         | `orders/models.py:67`                    | Да.                                                                                                                                                                                                                                          |
| Существующий `TransactionFilter`                    | `schemas.py:311-318`                     | Использует `min_amount`/`max_amount`, single `status`. FRD вводит `amount_from`/`amount_to` + `status_in`, **старые имена оставляются** как aliases (§8.3).                                                                                  |
| Существующий `/accounts` response                   | `services.py:209-212`                    | Возвращает `{total_count, accounts: [AccountResponse]}`. `AccountResponse` **уже содержит `user_name`** (`schemas.py:56`) — дополнительного enrichment на этой странице не требуется.                                                        |
| Существующий `/transactions` response               | `services.py:448-451`                    | Возвращает `{total_count, transactions: [TransactionDetail]}`. `TransactionDetail` embeds `AccountShort` **без `user_name`** — именно его нужно обогатить (§4.5).                                                                            |
| `has_debt` в текущем коде                           | `repositories.py:185-189`                | = `type == CLIENT AND balance > 0`. Знаковая конвенция: у CLIENT-счёта **положительный** баланс = клиент должен системе; отрицательный = предоплата/кредит клиента. Оставляем как legacy, документируем в §5.1.                              |

**UUIDv7-collision примечание.** UUIDv7 = `[48 bits unix_ts_ms | 4 bits version | 12 bits rand_a | 2 bits variant | 62 bits rand_b]`. Первые 8 hex-символов (`hex[0:8]`) — это старшие 32 бита timestamp, которые инкрементируются раз в ~65 секунд. **Все заказы, созданные в одном 65-секундном окне, имеют одинаковый префикс** — как short-id он бесполезен. Поэтому `order_short_id = RIGHT(order_id::text, 8)` — это последние 8 hex из `rand_b`, полностью случайные. Вероятность коллизии при 1M заказов ≈ 1M² / (2·16⁸) ≈ 116 пар — приемлемо для UI-поиска (пользователь видит 1–2 результата и выбирает нужный по сумме/дате/имени).

---

## 1. Контекст и цели

### 1.1. Бизнес-проблема

Backoffice (ADMIN / ACCOUNTANT / CASHIER) ежедневно работает с:
- **Транзакциями** — append-only леджером (100–1000+ записей в день, десятки тысяч в месяц). Нужно быстро находить оплату клиента, сверять сдачу курьера, ловить PENDING-проводки, расследовать расхождения.
- **Счетами (Accounts)** — CLIENT / COURIER / системные. Нужно искать должников, выбирать курьеров со сданной / не-сданной выручкой, контролировать лимиты.

Текущая реализация (`repositories.py:148`, `repositories.py:356`) поддерживает только базовые фильтры: `status`, `account_id`, `order_id`, диапазон дат, диапазон суммы; поиск по счетам — только по `account.name` и `user.username` через ILIKE. Этого недостаточно для UX-эффективной работы на объёмах прод-данных.

### 1.2. Цели FRD

1. Определить **полный набор фильтров** для страниц Accounts и Transactions, покрывающий ≥95% реальных сценариев бухгалтера/кассира.
2. Определить **семантику поиска** (free-text) — по каким полям, с какими правилами ранжирования и нормализации.
3. Определить **стратегию пагинации** (offset vs cursor) и гарантии стабильности при append-only леджере.
4. Зафиксировать **контракт API** (query-параметры, shape ответа, коды ошибок), пригодный для фронтенда и для интеграций/экспортов.
5. Обозначить **индексы и перформанс-требования** (p95 latency) под ожидаемые объёмы.

### 1.3. Не в скоупе

- UI/UX-макеты (отдельный документ `dashboard_ui.md` / дизайн-система).
- Экспорт в XLSX/CSV (будет отдельный FRD «Finance Exports»).
- Дашборд-виджеты и агрегаты (покрыто в `dashboard_finance.md`).
- Client/Courier self-service страницы (у них отдельный скоуп).

---

## 2. Персоны и сценарии использования

| Роль          | Типовой сценарий                                                                                                                        | Критичные фильтры                                                          |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| ADMIN         | «Покажи все REJECTED за сегодня», «Найди транзакцию по заказу по 8-значному ID `4a2b7c91`»                                              | `status_in`, `order_short_id`, `date_preset`, `verified_by_id`             |
| ACCOUNTANT    | «Сколько PENDING пришло через карту», «Сдачи курьера Иванова за неделю»                                                                 | `status_in=pending`, `from_account_type_in`, `courier_id`, `date_preset`   |
| CASHIER       | «Найди оплату клиента +998 90 123-45-67 на 150 000 сум», «Что принято сегодня»                                                          | `q` (телефон/сумма), `date_preset=today`                                   |
| ADMIN (аудит) | «Все переводы между двумя счетами», «История операций по заказу X», «Все проводки, где reason ~ 'бонус'»                                | `from_account_id`, `to_account_id`, `order_id`, `q` (текст)                |

---

## 3. Принципы проектирования

1. **Server-driven фильтрация.** Всё, что влияет на выборку, передаётся query-параметрами. Фронт не фильтрует клиентски.
2. **Композиционность.** Все фильтры комбинируются через AND. Multi-value фильтры (массивы) — внутренний OR.
3. **Идемпотентность ссылок.** URL с query-параметрами ↔ точный набор результатов (shareable, bookmarkable).
4. **Пустой фильтр = все активные.** `is_active=False` никогда не попадает в стандартные списки (леджер append-only, но архивация счетов допустима).
5. **Единообразие имён.** `_from` / `_to` для диапазонов (`date_from`, `amount_from`), `_in` для multi-value (`status_in`), `_search` для free-text в конкретном поле, `q` для глобального поиска.
6. **Стабильная сортировка.** Всегда tiebreaker по `id` (UUIDv7 монотонный по времени).
7. **Денежные значения — целые сумы** (`BIGINT`, без копеек). Фильтры по сумме принимают целые; форматирование — ответственность фронта.
8. **Даты.** Все datetime-фильтры — UTC ISO-8601. Для `date_preset` окно вычисляется в TZ `Asia/Tashkent`. Если клиент передаёт `date_to` как `YYYY-MM-DD` без времени — сервер интерпретирует как `23:59:59.999999 UTC` того дня (inclusive).
9. **PII-протекция.** Телефон и имя — чувствительные данные; логируется только `q.length` и факт совпадения канала, не сам ввод.

---

## 4. Страница «Транзакции» (Transactions)

### 4.1. Структурные фильтры

| Параметр                  | Тип                       | Описание                                                                                                                 | Примечания                                                                                                  |
| ------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| `status_in`               | `TransactionStatus[]`     | Multi-select: `pending`, `completed`, `rejected`                                                                         | Заменяет текущий single `status`; backward-совместимо (§8.3)                                                |
| `direction`               | `incoming\|outgoing\|any` | Только в паре с `account_id` — направление относительно счёта                                                            | Без `account_id` игнорируется                                                                               |
| `account_id`              | `uuid`                    | Все транзакции, где счёт участвует как `from_id` ИЛИ `to_id`                                                             | Совместим с `direction`                                                                                     |
| `from_account_id`         | `uuid`                    | Точное совпадение `from_id`                                                                                              |                                                                                                             |
| `to_account_id`           | `uuid`                    | Точное совпадение `to_id`                                                                                                |                                                                                                             |
| `from_account_type_in`    | `AccountType[]`           | JOIN `accounts` и фильтр по типу счёта-источника                                                                         | Пример: «все списания с курьерских касс»                                                                    |
| `to_account_type_in`      | `AccountType[]`           | Аналогично для счёта-получателя                                                                                          | Пример: «все пополнения системного BANK»                                                                    |
| `order_id`                | `uuid`                    | Точный заказ (полный UUID)                                                                                               | Для API-интеграций; в UI подставляется при клике на карточку заказа                                         |
| `order_short_id`          | `string(8)`               | 8 hex-символов случайного хвоста UUID заказа — «короткий ID», отображаемый в UI                                          | Внутренне `RIGHT(order_id::text, 8) = lower(value)`; expression-индекс (§7.2)                               |
| `order_status_in`         | `OrderStatus[]`           | JOIN `orders` — например «все проводки по `delivered` заказам»                                                           | Индекс `orders.status` уже есть                                                                             |
| `order_payment_method_in` | `PaymentMethod[]`         | JOIN `orders.payment_method`                                                                                             | Миграция §7.2 добавляет индекс                                                                              |
| `order_sale_type_in`      | `SaleType[]`              | JOIN `orders.sale_type` (`delivery` / `warehouse_pickup`)                                                                | Индекс уже есть                                                                                             |
| `contract_id`             | `uuid`                    | JOIN `orders.contract_id`                                                                                                | Для deep-link из карточки договора                                                                          |
| `contract_number`         | `string`                  | Номер договора (JOIN `orders → contracts`, `contracts.number ILIKE 'value%'`)                                            | Основной B2B-поиск; человекочитаемо                                                                         |
| `client_id`               | `uuid`                    | Транзакции, где одна из сторон — CLIENT-счёт пользователя                                                                | JOIN `accounts.user_id`                                                                                     |
| `courier_id`              | `uuid`                    | Аналогично для COURIER-счёта                                                                                             |                                                                                                             |
| `user_role_in`            | `Role[]`                  | JOIN `users.role` через любой из счётов транзакции                                                                       | Пример: «все транзакции с участием B2B-клиентов»                                                            |
| `verified_by_id`          | `uuid`                    | Кто подтвердил (бухгалтер)                                                                                               |                                                                                                             |
| `verified`                | `bool`                    | `true` = `verified_by_id IS NOT NULL`; `false` = IS NULL                                                                 |                                                                                                             |
| `has_order`               | `bool`                    | `true` = `order_id IS NOT NULL`; «ручные проводки» — `false`                                                             | Игнорируется, если задан `order_id` / `order_short_id`                                                      |
| `reason_search`           | `string`                  | Поиск в `transactions.reason` (`ILIKE '%value%'`)                                                                        | Альтернатива `q` для точечных запросов через пресеты                                                        |
| `date_from`               | `datetime`                | `created_at >= date_from`                                                                                                | UTC                                                                                                         |
| `date_to`                 | `datetime`                | `created_at <= date_to`                                                                                                  | UTC, inclusive (см. §3.8)                                                                                   |
| `date_preset`             | `enum`                    | `today`, `yesterday`, `this_week`, `last_week`, `this_month`, `last_month`, `last_7d`, `last_30d`                        | Сервер вычисляет границы в TZ `Asia/Tashkent`; взаимоисключающ с `date_from`/`date_to` — 422                |
| `amount_from`             | `int`                     | `amount >= amount_from` (в сумах)                                                                                        | `ge=0`; alias старого `min_amount` (§8.3)                                                                   |
| `amount_to`               | `int`                     | `amount <= amount_to`                                                                                                    | `ge=0`; alias старого `max_amount`                                                                          |
| `amount_eq`               | `int`                     | Точная сумма (быстрый фильтр «150000»)                                                                                   | Взаимоисключающе с `amount_from`/`amount_to` — 422                                                          |
| ~~`created_by_id`~~       | `uuid`                    | **Вне MVP.** Требует миграции — добавить колонку `transactions.created_by_id` (nullable, RESTRICT, индекс). См. §10.1    | После миграции: автор ручной проводки                                                                       |

### 4.2. Free-text поиск (`q`)

**Принцип.** Поиск работает **только по человекочитаемым данным** — тем, что пользователь видит глазами в интерфейсе или помнит по работе с клиентом. UUID любого вида (полный или частичный) **в `q` не принимается как UUID-значение** — в т.ч. не ищется по `transactions.id`, `order_id`, `from_id`, `to_id`, `user_id`. Для прямого перехода по UUID используются структурные фильтры `order_id`, `account_id`, `from_account_id`, `to_account_id` (§4.1), которые проставляются UI-навигацией (клик из карточки, deep-link), а не ручным вводом.

**Параметр.** `q: string, min_length=2, max_length=100`.

**Каналы поиска (детектор выбирает подмножество — чтобы не платить за JOIN'ы зря; каналы сочетаются по OR).**

| Порядок | Паттерн                                                | Где ищем                                                                                                                                                                                      | Пример ввода                |
| ------- | ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| 1       | `^\+?\d[\d\s\-\(\)]{7,19}$` → нормализация в 9–13 цифр | `regexp_replace(provider_identity_id, '\D', '', 'g') LIKE '%digits%'` на `identities` при `provider='local'` **и** то же на `phone_numbers.phone` для обоих участников — через JOIN `accounts.user` | `+998 90 123…`, `901234567` |
| 2       | `^[A-Za-zА-Яа-я]{2,8}-?\d{2,4}-?\d{2,6}$`              | `contracts.number ILIKE 'q%'` через JOIN `orders → contracts`                                                                                                                                 | `HOD-2025-001`              |
| 3       | `^[0-9a-f]{8}$` (ровно 8 hex, нижний регистр)          | `RIGHT(order_id::text, 8) = lower(q)` — «короткий ID» заказа из случайного хвоста UUIDv7 (см. пояснение в §Сверка)                                                                            | `4a2b7c91`                  |
| 4       | `^\d{1,13}$` (целое > 0, помещается в BIGINT)          | `amount = int(q)`                                                                                                                                                                             | `150000`                    |
| 5       | Иначе (текст ≥ 2 символов)                             | `users.username` (обоих участников), `transactions.reason` — `ILIKE '%q%'` (с экранированием `%`/`_`/`\`)                                                                                     | `Азизов`, `возврат`         |

**Нормализация телефона.** `phone_numbers.phone` и `identities.provider_identity_id` **не нормализуются при записи** (исторически): пользователь мог ввести `+998 90 123-45-67` или `998901234567`. Поэтому на поиске нормализуются **обе стороны**: запрос → чистые цифры; колонки — через выражение `regexp_replace(col, '\D', '', 'g')`. Чтобы не делать seq-scan, миграция §7.2 создаёт expression-индексы на оба поля.

**Important:** каналы 3–4–5 могут сработать одновременно — например, `4a2b7c91` валиден и как short-id (hex), и как текст; оба OR-условия добавляются в запрос. Цель детектора — не исключение, а включение **ровно нужных JOIN'ов** (телефон требует `identities`/`phone_numbers`, контракт — `contracts`, и т.д.). Детектор идёт сверху вниз, но матчи НЕ взаимоисключающие.

**Явный запрет UUID.** Если `q` соответствует regex `^[0-9a-f]{9,}$` (hex ≥ 9 символов) или содержит дефис (полный UUID) — сервер возвращает 422 `SEARCH_UUID_NOT_ALLOWED` с сообщением «Поиск по UUID не поддерживается; используйте телефон, имя, номер договора, сумму или 8-значный ID заказа». Это явный UX-сигнал, а не тихий zero-result. Ровно 8 hex без дефисов — валидный short-id (канал 3).

**UX-требования к фронту (обязательные для работы поиска).**

- На каждой карточке/строке транзакции UI **обязан показывать**:
  - `order_short_id` (**последние** 8 hex-символов `order_id` — см. §Сверка, UUIDv7-collision) — кликабельный, копируется в буфер;
  - имя контрагента (`from_account.user_name` / `to_account.user_name`);
  - номер договора, если есть (`contract_number`).
- Это именно те строки, которые пользователь набирает в `q` при поиске «по тому, что видел глазами».
- Плейсхолдер поля ввода: «Телефон, имя, договор, ID заказа, сумма».
- Для перехода «все транзакции по этому клиенту / счёту / заказу» UI использует **структурные фильтры** (`client_id`, `account_id`, `order_id`), проставляя их по клику — пользователю не нужно копировать UUID.

**Экранирование и безопасность.**

- Wildcards `%` и `_` от пользователя экранируются (`ESCAPE '\'`).
- `q.length < 2` → 422 `SEARCH_TOO_SHORT`.
- `q.length > 100` → 422 `SEARCH_TOO_LONG`.
- Пробелы по краям `strip()`; множественные пробелы внутри схлопываются перед детектором телефона.

**Ранжирование.** MVP: всегда `ORDER BY created_at DESC, id DESC`. Relevance-ранжирование через `pg_trgm.similarity()` — отложено до подтверждённой UX-потребности (§12, шаг 10).

### 4.3. Сортировка

| `sort` (query) | Поле                  | По умолчанию     |
| -------------- | --------------------- | ---------------- |
| `created_at`   | `created_at`          | **default DESC** |
| `amount`       | `amount`              |                  |
| `status`       | `status` (enum order) |                  |

Формат: `sort=created_at&order=desc`. Всегда добавляется tiebreaker `id DESC`. Допустимые `order`: `asc` / `desc`. Неизвестное значение — 422.

### 4.4. Пагинация

**Режимы:** поддерживаются два — клиент выбирает по use-case.

#### 4.4.1. Offset-based (по умолчанию)

- `page` (int, ge=1, default=1)
- `size` (int, ge=1, le=100, default=50)

Ответ включает `total_count`, `page`, `size`, `total_pages`. Подходит для UI с нумерованными страницами «1, 2, 3 … 42».

**Ограничение:** при `page * size > 10_000` — 422 с `error_code=PAGINATION_TOO_DEEP` и рекомендацией использовать cursor. Причина: deep offset на append-only леджере деградирует до seq-scan.

#### 4.4.2. Cursor-based (для «Загрузить ещё», экспортов, больших выборок)

- `cursor` (opaque base64; кодирует `(created_at_iso, id_hex)` последнего элемента)
- `size` (тот же, что в offset-режиме)

Формат курсора: `base64(f"{created_at.isoformat()}|{id.hex}")`. Декодер валидирует обе части; битый cursor → 422 `CURSOR_INVALID`.

SQL tie-break: `WHERE (created_at, id) < (:cursor_ts, :cursor_id) ORDER BY created_at DESC, id DESC LIMIT :size+1`. `has_more = len(rows) > size` (лишний элемент отбрасывается и идёт в `next_cursor`).

Ответ: `items`, `next_cursor` (nullable), `has_more` (bool). **Нет** `total_count` (не считается ради перформанса). При смене фильтров cursor инвалидируется семантически — клиент обязан отбросить его. Сервер не проверяет консистентность фильтров с cursor'ом, но возвращает стабильные результаты только при фиксированных фильтрах.

### 4.5. Контракт ответа

```json
{
  "items": [ TransactionDetail ],
  "pagination": {
    "mode": "offset",
    "page": 1,
    "size": 50,
    "total_count": 1283,
    "total_pages": 26
  },
  "summary": {
    "sum_amount": 18230000,
    "count_by_status": { "pending": 12, "completed": 1250, "rejected": 21 }
  }
}
```

- `summary` считается **по применённым фильтрам, игнорируя пагинацию** — даёт бухгалтеру «сумму отфильтрованного». Реализуется отдельным SQL-запросом с теми же WHERE (без `ORDER BY`/`LIMIT`).
- Для cursor-режима `pagination` = `{ "mode": "cursor", "next_cursor": "...", "has_more": true, "size": 50 }` (без `total_count` и `total_pages`). `summary` в cursor-режиме **не возвращается** — считается только для первой страницы по запросу `include_summary=true`.
- Shape `items` — существующий `TransactionDetail` (`schemas.py:177`); поля `from_account`, `to_account`, `verified_by_id`, `order_id`, `created_at`, `reason` уже есть.
- **Расширить `AccountShort`** (`schemas.py:69-76`, используется как вложенная схема в `TransactionDetail`): добавить `user_name: str | None` — `User.username`, т.е. ФИО физлица / название компании (не логин), см. `users/models.py:107`. В существующем `AccountResponse` это поле **уже есть** (`schemas.py:56`) — расширяем только `AccountShort`, чтобы embedding в транзакциях нёс ту же информацию. Заполняется JOIN'ом в репозитории, исключает N+1 на фронте.
- **Расширить `TransactionDetail`:** добавить `verified_by_name: str | None` (JOIN `users` по `verified_by_id`; null, если `verified_by_id IS NULL`) и `order_short_id: str | None` (`RIGHT(order_id::text, 8)` — последние 8 hex случайного хвоста UUIDv7, см. §Сверка). `order_short_id` **обязателен** в ответе, когда `order_id IS NOT NULL`.
- Существующая `TransactionResponse` (`schemas.py:122`) — дубликат `TransactionDetail` и должен быть помечен `@deprecated` в OpenAPI, со сроком удаления в следующем мажоре (§10.2).

### 4.6. Валидация

| Правило                                        | Код ошибки                      |
| ---------------------------------------------- | ------------------------------- |
| `date_from > date_to`                          | `DATE_RANGE_INVALID` (422)      |
| `amount_from > amount_to`                      | `AMOUNT_RANGE_INVALID` (422)    |
| `amount_eq` вместе с `amount_from`/`amount_to` | `AMOUNT_CONFLICT` (422)         |
| `date_preset` вместе с `date_from`/`date_to`   | `DATE_PRESET_CONFLICT` (422)    |
| `direction` без `account_id`                   | Игнорируется (warning-log)      |
| `q.length < 2`                                 | `SEARCH_TOO_SHORT` (422)        |
| `q.length > 100`                               | `SEARCH_TOO_LONG` (422)         |
| `q` — полный UUID или hex > 8 символов         | `SEARCH_UUID_NOT_ALLOWED` (422) |
| `page*size > 10_000` (offset)                  | `PAGINATION_TOO_DEEP` (422)     |
| битый/просроченный `cursor`                    | `CURSOR_INVALID` (422)          |

Все ошибки через `AppException` иерархию (`src/core/exceptions.py`), без `HTTPException`, сообщения на русском.

---

## 5. Страница «Счета» (Accounts)

### 5.1. Структурные фильтры

| Параметр              | Тип             | Описание                                                                       |
| --------------------- | --------------- | ------------------------------------------------------------------------------ |
| `type_in`             | `AccountType[]` | Multi-select; заменяет single `type`                                           |
| `user_id`             | `uuid`          | Счета конкретного пользователя                                                 |
| `user_role_in`        | `Role[]`        | JOIN users + фильтр по ролям владельца (`client_b2c`, `client_b2b`, `courier`) |
| `balance_from`        | `int`           | `balance >= balance_from` (может быть отрицательным)                           |
| `balance_to`          | `int`           | `balance <= balance_to`                                                        |
| `has_debt`            | `bool`          | `balance > 0 AND type=CLIENT` (legacy semantics: у CLIENT-счёта положительный баланс = клиент должен системе; см. §Сверка) |
| `is_in_credit`        | `bool`          | `balance < 0 AND type=CLIENT` — «переплата клиента»                                                                         |
| `zero_balance`        | `bool`          | `balance = 0`                                                                  |
| `has_recent_activity` | `int` (days)    | Существует хотя бы 1 транзакция за последние N дней (EXISTS subquery)          |
| `stale_since`         | `int` (days)    | Нет транзакций более N дней (антоним `has_recent_activity`)                    |
| `created_from`        | `date`          | Счёт создан не ранее                                                           |
| `created_to`          | `date`          | Счёт создан не позднее                                                         |

### 5.2. Free-text поиск (`q`)

Принцип и каналы — как в §4.2: **поиск только по человекочитаемым данным**, UUID через `q` не принимается (см. правило `SEARCH_UUID_NOT_ALLOWED`). Для страницы Accounts применяются ветки:

1. **Телефон** (нормализация по §4.2): JOIN `users → identities` (`provider='local'`) + `users → phone_numbers`; матч по суффиксу `provider_identity_id` / `phone_numbers.phone`.
2. **Текст:** `accounts.name ILIKE '%q%'`, `users.username ILIKE '%q%'` (trigram-индексы покрывают оба).
3. **Целое число:** `balance = int(q)` (если помещается в BIGINT). Полезно для «найти счёт с балансом ровно 500 000».

Переход на детали конкретного счёта / пользователя — через структурный фильтр `user_id` (§5.1) или прямой URL-параметр, выставляемый UI по клику. Общие правила длины, экранирования, запрета UUID — как в §4.2.

### 5.3. Сортировка

| `sort`        | Поле                        |
| ------------- | --------------------------- |
| `balance`     | `balance` (default DESC)    |
| `name`        | `accounts.name`             |
| `created_at`  | `created_at` (DESC default) |
| `last_txn_at` | max(created_at транзакций)  |

`sort=balance&order=desc` — стандарт для вкладки «Должники».

### 5.4. Пагинация

Offset-only (`page`, `size` как в §4.4.1). Объём Accounts << Transactions, cursor не обязателен. Тот же лимит глубины `page*size ≤ 10_000`.

### 5.5. Контракт ответа

```json
{
  "items": [ AccountResponse + { "last_transaction_at": "2026-04-18T09:12:00Z" } ],
  "pagination": { "mode": "offset", "page": 1, "size": 50, "total_count": 312, "total_pages": 7 },
  "summary": {
    "sum_balance": 184300000,
    "count_by_type": { "client": 250, "courier": 8, "cash": 1, ... }
  }
}
```

---

## 6. Saved views (Presets)

Чтобы операторы не переформировывали один и тот же набор фильтров каждый день.

| Preset (ключ сервера)       | Страница     | Фильтры                                                                        |
| --------------------------- | ------------ | ------------------------------------------------------------------------------ |
| `txn.pending_card_today`    | Transactions | `status_in=pending`, `to_account_type_in=card`, `date_preset=today`            |
| `txn.rejected_today`        | Transactions | `status_in=rejected`, `date_preset=today`                                      |
| `txn.courier_deposits`      | Transactions | `from_account_type_in=courier`, `to_account_type_in=cash`, `date_preset=today` |
| `txn.b2b_contract_payments` | Transactions | `order_payment_method_in=contract`, `date_preset=this_month`                   |
| `acc.top_debtors`           | Accounts     | `type_in=client`, `has_debt=true`, `sort=balance&order=desc`                   |
| `acc.stale_couriers`        | Accounts     | `type_in=courier`, `stale_since=3`                                             |

API:
- `GET /api/v1/backoffice/finances/presets` — список (hardcoded серверных + персональных пользовательских, если фича дойдёт).
- `GET /api/v1/backoffice/finances/transactions?preset=txn.pending_card_today` — сервер подставляет фильтры.
- Явно переданные query-параметры **переопределяют** пресет (merge-semantics, user-параметр wins).

**MVP:** только серверные пресеты (enum в коде). Персональные — отдельная таблица в будущем (out of scope).

---

## 7. Индексы и перформанс

### 7.1. Ожидаемые объёмы (Y+1)

- `transactions`: до 1M строк.
- `accounts`: до 20k строк.

### 7.2. Required indexes

**Существующие (проверено в `src/modules/finances/models.py` и `src/modules/users/models.py`):**
- `idx_transaction_from_status (from_id, status)`, `idx_transaction_to_status (to_id, status)` — таб. индексы
- `idx_account_user_type (user_id, type)` — таб. индекс
- `transactions.order_id`, `transactions.verified_by_id` — индексированы колоночно (`models.py:104,111`)
- `accounts.type` — индексирован колоночно (`models.py:27`)
- `users.role` — индексирован (`users/models.py:119`), покрывает `user_role_in`
- `phone_numbers.phone` — **UNIQUE**, обеспечивает fast lookup при полном совпадении телефона
- `orders.status`, `orders.sale_type`, `orders.contract_id`, `orders.warehouse_id`, `orders.courier_id`, `orders.client_id` — индексированы колоночно
- **НЕ индексирован:** `orders.payment_method` — добавляется ниже

**Дополнительные (необходимые для FRD):**

```sql
-- Расширение (разовая операция на уровне БД)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Основной sort/cursor key (партиальный по active)
CREATE INDEX idx_transaction_created_at_id
  ON transactions (created_at DESC, id DESC) WHERE is_active;

-- Trigram для свободного текста
CREATE INDEX idx_transaction_reason_trgm
  ON transactions USING gin (reason gin_trgm_ops);
CREATE INDEX idx_account_name_trgm
  ON accounts USING gin (name gin_trgm_ops);
CREATE INDEX idx_user_username_trgm
  ON users USING gin (username gin_trgm_ops);

-- Частичный индекс для PENDING (горячая выборка + агрегаты дашборда)
CREATE INDEX idx_transaction_pending
  ON transactions (created_at DESC) WHERE status = 'pending' AND is_active;

-- Баланс + тип (top_debtors, stale_couriers, summary)
CREATE INDEX idx_account_type_balance
  ON accounts (type, balance DESC) WHERE is_active;

-- Expression-индекс на "короткий ID" заказа = последние 8 hex случайного
-- хвоста UUIDv7. Именно эту функцию применяет детектор §4.2 канал 3
-- и фильтр `order_short_id`. LEFT(...) не использовать — см. §Сверка.
CREATE INDEX idx_transaction_order_short_id
  ON transactions ((RIGHT(order_id::text, 8)))
  WHERE order_id IS NOT NULL AND is_active;

-- Поиск по цифрам телефона (LOCAL-провайдер).
-- Expression + trigram: нормализованный regexp_replace → trigram gin.
CREATE INDEX idx_identity_local_phone_digits_trgm
  ON identities USING gin (
    (regexp_replace(provider_identity_id, '\D', '', 'g')) gin_trgm_ops
  )
  WHERE provider = 'local';

CREATE INDEX idx_phone_numbers_digits_trgm
  ON phone_numbers USING gin (
    (regexp_replace(phone, '\D', '', 'g')) gin_trgm_ops
  );

-- Индекс под фильтр `order_payment_method_in` (колонка без index=True
-- на уровне модели, см. §Сверка).
CREATE INDEX idx_order_payment_method
  ON orders (payment_method) WHERE is_active;

-- contract.number уже UNIQUE; для ILIKE 'prefix%' нужен text_pattern_ops:
CREATE INDEX idx_contract_number_pattern
  ON contracts (number text_pattern_ops);
```

Все индексы создаются через Alembic-ревизию `finances_search_indexes` с `op.execute("CREATE INDEX CONCURRENTLY ...")` (requires `autocommit_block` в миграции, см. [Alembic docs](https://alembic.sqlalchemy.org/en/latest/cookbook.html#conditional-migration-elements)). `CREATE EXTENSION` выполняется один раз — вынесено в отдельный `op.execute` без CONCURRENTLY.

⚠ **asyncpg-нюанс (уже фигурирует в memory):** если в миграции есть PL/pgSQL с `$$`, оборачивать в `sa.text(...)`. Тут — только CREATE INDEX / CREATE EXTENSION, проблемы с dollar-quoting нет.

### 7.3. SLA

| Эндпоинт                               | p95 target | Комментарий                                                         |
| -------------------------------------- | ---------- | ------------------------------------------------------------------- |
| `GET /transactions` (offset, 1 фильтр) | < 200 мс   | С trigram-индексом и partial index по `pending`                     |
| `GET /transactions` (cursor)           | < 100 мс   | Без COUNT(*)                                                        |
| `GET /transactions?q=...`              | < 400 мс   | При активном pg_trgm                                                |
| `GET /accounts`                        | < 150 мс   |                                                                     |
| `summary` (отдельный запрос)           | < 150 мс   | Кэшируется по ключу = canonical filter hash, TTL 30 с — опционально |

### 7.4. Анти-паттерны (запрещено)

- `COUNT(*)` без фильтра `is_active` (full scan).
- `ORDER BY RANDOM()`.
- Подзапросы в SELECT-листе для каждой строки (N+1) — использовать `joinedload` / `selectinload`, как уже принято.
- Раскрытие `UUID` в query без валидации — FastAPI `uuid.UUID` делает это автоматически.

---

## 8. Контракт API (итог)

### 8.1. Эндпоинты

| Метод | Путь                                                          | Scope           |
| ----- | ------------------------------------------------------------- | --------------- |
| GET   | `/api/v1/backoffice/finances/transactions`                    | `FINANCES_READ` |
| GET   | `/api/v1/backoffice/finances/transactions/summary`            | `FINANCES_READ` |
| GET   | `/api/v1/backoffice/finances/accounts`                        | `FINANCES_READ` |
| GET   | `/api/v1/backoffice/finances/accounts/{account_id}/statement` | `FINANCES_READ` |
| GET   | `/api/v1/backoffice/finances/presets`                         | `FINANCES_READ` |

### 8.2. Именованные query-параметры (сводка)

Все параметры опциональны (кроме `page`/`size` с дефолтами). Полный перечень — в §4.1, §4.3, §4.4, §5.1, §5.3.

### 8.3. Backward compatibility

- Старые single-value фильтры (`status`, `type`, `search`) и старые имена (`min_amount`→`amount_from`, `max_amount`→`amount_to`) **принимаются сервером как deprecated aliases** минимум 1 мажор-релиз. Логика приоритета: если передан `*_in` или новое имя — оно wins, alias игнорируется с `logger.warning("deprecated filter: {name}")`. Aliases перечислены в OpenAPI с `deprecated: true`.
- Ключ ответа `transactions` → `items`: в переходный период сервер возвращает **оба** ключа с одинаковым содержимым. Удаление `transactions` — следующий мажор, фикс в CHANGELOG.
- `TransactionResponse` (`schemas.py:122`) помечается `@deprecated` в пользу `TransactionDetail`. Для create-эндпоинта `POST /transactions` ответ возвращает `TransactionDetail` с тем же shape.

### 8.4. Ошибки

Формат — стандартный проектный `{ "error": { "code": "...", "message": "...", "details": {...} } }` (см. `src/api/exceptions/handlers.py`). Коды, специфичные для фильтров, перечислены в §4.6. Все человеческие сообщения — на русском.

---

## 9. Влияние на слои кода

| Слой                         | Изменения                                                                                                                                                                                                                           |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `finances/schemas.py`        | Расширить `TransactionFilter` / `AccountFilter`; ввести `PaginationMeta` (offset+cursor), `TransactionSummary`, `TransactionListResponse`, `AccountListResponse`.                                                                   |
| `finances/repositories.py`   | Переписать `get_transactions_with_filters` (JOIN `accounts`, `accounts.user`, `orders`, `orders.contract`, `identities`, `phone_numbers`), добавить `get_transactions_cursor`, `get_transactions_summary`; аналогично для accounts. |
| `finances/services.py`       | `BillingService.get_transactions` принимает Pydantic-фильтр целиком; возвращает `TransactionListResponse`; суммарные агрегаты через отдельный метод репозитория.                                                                    |
| `finances/uow.py`            | Без изменений — репозиторий сам читает смежные таблицы, запись туда запрещена.                                                                                                                                                      |
| `api/backoffice/finances.py` | Query-параметры по §4.1/§5.1; новые эндпоинты `/transactions/summary`, `/presets`; сохранить старые ключи ответа 1 релиз (alias).                                                                                                   |
| `alembic/versions/`          | Миграция `finances_search_indexes` (§7.2) — `CREATE EXTENSION pg_trgm`, CONCURRENTLY-индексы, partial-индексы.                                                                                                                      |
| Тесты                        | Unit-тесты детектора `q` (телефон / contract / short-id / int / text; плюс негативные: полный UUID → 422, hex-строка длиной 10 → 422); integration-тесты каждого фильтра (happy + ≥2 edge); perf-smoke на 100k транзакций.          |

Принцип DDD соблюдается: JOIN к `users`/`orders`/`identities`/`phone_numbers`/`contracts` из `finances/repositories.py` — **только чтение** (SELECT). Запись в чужие таблицы запрещена; приватные данные (`password_hash`) никогда не селектятся — репозиторий явно перечисляет нужные колонки через `load_only(...)` или `selectinload` со схлопыванием.

---

## 10. Открытые вопросы / зависимости

| #   | Вопрос                                                            | Статус       | Решение                                                                                                                                                                                                                                                                                                                         |
| --- | ----------------------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `Transaction.created_by_id` — автора ручной проводки нет в БД     | **Открыт**   | Отдельная мини-миграция: добавить `created_by_id` (FK на `users`, nullable). Блокирует фильтр «кто создал», но не остальной FRD.                                                                                                                                                                                                |
| 2   | Человекочитаемый номер заказа                                     | **Закрыт**   | Поля `number` у `orders` нет. UI показывает `order_short_id = RIGHT(order_id::text, 8)` — **последние** 8 hex случайного хвоста UUIDv7 (префикс непригоден: первые 8 hex — старшие биты timestamp, одинаковы у всех заказов в окне ~65 сек). Поиск — фильтр `order_short_id` (§4.1) и ветка §4.2.3. Полный UUID в `q` запрещён (422 `SEARCH_UUID_NOT_ALLOWED`); для навигации по конкретному заказу UI использует структурный фильтр `order_id`. |
| 3   | Форма хранения телефона                                           | **Закрыт**   | `identities.provider_identity_id` при `provider=LOCAL` + `phone_numbers.phone` (UNIQUE). Поиск — нормализация + `LIKE '%suffix'`.                                                                                                                                                                                               |
| 4   | `pg_trgm` в prod                                                  | **Открыт**   | В текущих миграциях нет. Миграция §7.2 добавит `CREATE EXTENSION IF NOT EXISTS` — требует роли с `CREATE` на database.                                                                                                                                                                                                          |
| 5   | TZ для `date_preset`                                              | **Закрыт**   | `Asia/Tashkent` (единственный регион сейчас). При расширении — вынести в `core/config.py` как `BUSINESS_TIMEZONE`.                                                                                                                                                                                                              |
| 6   | Персональные saved views                                          | Out of scope | В будущем — таблица `user_finance_presets(user_id, name, filters_json)`.                                                                                                                                                                                                                                                        |
| 7   | Кэш `summary`                                                     | Открыт       | MVP без кэша. При росте нагрузки — Redis или in-process TTL-cache с ключом = каноничный хеш фильтров.                                                                                                                                                                                                                           |
| 8   | `from_account_type_in` / `to_account_type_in` — тип счёта-стороны | **Закрыт**   | Реализуется через JOIN `accounts AS from_acc / to_acc` и фильтр по `AccountType` (индекс `account.type` уже есть).                                                                                                                                                                                                              |
| 9   | Номер контракта в поиске `q`                                      | **Закрыт**   | `contracts.number` `UNIQUE String(50)` (`contracts/models.py:35`) — JOIN `orders → contracts`, ILIKE prefix.                                                                                                                                                                                                                    |
| 10  | `TransactionResponse` vs `TransactionDetail`                      | **Открыт**   | Сейчас в `schemas.py` сосуществуют `TransactionResponse` (line 122) и `TransactionDetail` (line 177) с почти идентичными shape. FRD предлагает: POST-create возвращает `TransactionDetail`; `TransactionResponse` помечается `@deprecated` и удаляется следующим мажором.                                                       |
| 11  | Знак баланса у CLIENT-счёта                                       | **Закрыт**   | Legacy: у `type=CLIENT` положительный `balance` = клиент должен системе. Фильтр `has_debt` = `balance > 0 AND type=CLIENT`. В UI подписывать «Задолженность клиента / Переплата», а не «Баланс». Смена знака — отдельная инициатива, вне FRD.                                                                                   |
| 12  | Ненормализованные телефоны в БД                                   | **Открыт**   | `phone_numbers.phone` и `identities.provider_identity_id (LOCAL)` не нормализуются при записи. FRD компенсирует expression-индексами (§7.2) и двусторонней нормализацией в запросе (§4.2). Отдельно: техдолг — нормализовать существующие данные и добавить check-constraint.                                                   |

---

## 11. Критерии приёмки (Definition of Done)

1. Все фильтры из §4.1 и §5.1 реализованы и покрыты интеграционными тестами (happy + ≥2 edge на каждый).
2. Поиск `q` проходит smoke-тесты: по `username`, `account.name`, телефону (с префиксом `+` и без), 8-символьному `order_short_id`, номеру контракта, тексту `reason`, сумме. Негативные: полный UUID и hex-строка > 8 символов возвращают 422 `SEARCH_UUID_NOT_ALLOWED`.
3. Offset и cursor режимы пагинации переключаются query-параметром; deep-offset даёт 422 `PAGINATION_TOO_DEEP`.
4. `summary` возвращает корректные агрегаты на фикстуре из 1k транзакций.
5. Перформанс-бюджеты §7.3 проходят на фикстуре из 100k транзакций (локальный Docker Postgres).
6. Backward compatibility: прежний фронт (single `status`, `type`, ключ `transactions` в ответе) работает без изменений.
7. Ошибки валидации §4.6 возвращают документированные `error_code` и русские сообщения.
8. Все новые индексы применены миграцией; `EXPLAIN ANALYZE` для топ-3 query (offset page 1, cursor next, `q` по имени) подтверждает index scan / bitmap heap scan, а НЕ seq scan.
9. Документация OpenAPI (FastAPI auto-gen) содержит описания и примеры для всех query-параметров.
10. Приватные поля `identities.password_hash` и `identities.provider_identity_id` для non-LOCAL провайдеров НЕ попадают в SELECT при поиске.

---

## 12. Roadmap реализации (логический порядок, без дат)

1. **Foundation schemas.** Расширить `TransactionFilter` / `AccountFilter`, добавить `PaginationMeta`, `TransactionSummary`, `TransactionListResponse`, `AccountListResponse`.
2. **Indexes migration.** Alembic-ревизия `finances_search_indexes` (§7.2) с CONCURRENTLY-хуком и `pg_trgm`.
3. **Multi-value и структурные фильтры.** `status_in`, `type_in`, `from/to_account_type_in`, `order_payment_method_in`, `order_sale_type_in`, `has_order`, `verified`, `user_role_in`, `balance_from/to`, `is_in_credit`, `zero_balance`, `stale_since`.
4. **Free-text `q`.** Парсер-детектор (phone → contract → short-id → int → text), ILIKE multi-field; guard на UUID (422). Опционально позже — `similarity()` ranking.
5. **Cursor pagination.** Opaque base64 cursor `(created_at, id)`; hard guard deep offset.
6. **Summary endpoint / inline block.** Отдельный SQL с теми же WHERE; без кэша в MVP.
7. **Presets endpoint.** Hardcoded список (§6).
8. **Resolved counterparty names в `TransactionDetail`.** `from_account.user_name`, `to_account.user_name`, `verified_by_name` — через JOIN, чтобы фронт не делал follow-up запросов.
9. **Опциональные расширения:** `Transaction.created_by_id` (миграция + фильтр), персональные saved views, CSV/XLSX экспорт, `pg_trgm similarity` ранжирование.
