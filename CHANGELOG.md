# CHANGELOG

Документ для фронтенд-команды: все breaking и не-breaking изменения бэкенд API HOD.

Формат: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Версионирование не семантическое — привязано к итерациям FRD.

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
