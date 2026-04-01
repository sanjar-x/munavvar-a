# PRD — Product Requirements Document

# Dashboard API для MunavvarA (HOD)

**Версия:** 2.0
**Дата:** 2026-04-01
**Статус:** Draft (reviewed)
**BRD-ссылка:** `research/DASHBOARD_BRD.md` (v1.5, 20 BR)
**Changelog v2.0:** Синхронизация с BRD v1.5 + ревью кодовой базы.

- **Новые EP:** EP-18 (Inventory Trends, BR-17), EP-19 (Virtual Accounts + Integrity, BR-18), EP-20 (Courier Load by Days, BR-19), EP-21 (Revenue B2B/B2C, BR-20)
- **Критическое исправление SQL:** Все inventory-запросы переведены с `stock_transfer_items` (черновик) на `stock_transactions` (леджер — «истина в последней инстанции»). `stock_transfer_items` — это документ до проведения, `stock_transactions` — фактические проведённые движения, обновляющие `inventory_balances` через PG-триггер.
- **EP-8 (BR-6):** Добавлен `change_percent` — % изменения vs предыдущий период
- **EP-9 (BR-7):** Добавлена заметка о 3 источниках дебиторки и PENDING-правиле
- **EP-12 (BR-9):** Добавлен `overdue_debt_ratio` — % просроченной задолженности
- **EP-13 (BR-10):** Добавлен `total_equipment_stock`, `losses_period`, стокипер-изоляция
- **EP-14 (BR-11):** Добавлена разбивка по конкретным продуктам (`per_product`)
- **EP-16 (BR-13):** Добавлена изоляция кладовщика (BUSINESS.md §13.14)
- **Раздел 7:** Обновлено фазирование — EP-18..EP-21 распределены по фазам
- **Приложение А:** Обновлено — 21 эндпоинт
- **Раздел 6.1:** Обновлена таблица SQL-источников — разделение `stock_transfer_items` vs `stock_transactions`

**Changelog v1.1:** Review по BUSINESS.md, DASHBOARD_BRD.md, dashboard_orders.md. Исправлены: типы продуктов (ProductType enum), определение частичных доставок, scopes авторизации, session dependency, фильтрация системных пользователей, EP-1 scope, timezone heatmap.

---

## 1. Обзор продукта

### 1.1 Цель

Dashboard API — набор read-only REST-эндпоинтов, предоставляющих агрегированные данные для дашбордов админ-панели MunavvarA. API проектируется по CQRS-принципу: отдельные query-объекты и эндпоинты для чтения, не затрагивающие транзакционную логику.

### 1.2 Архитектурный подход

```
Frontend (RTK Query)
    ↓ HTTP GET
API Layer: src/api/v1/backoffice/dashboard/
    ↓
Query Services: src/modules/{domain}/dashboard_queries.py
    ↓ Read-only SQL
PostgreSQL (existing tables, no new tables)
```

**Принципы:**

- **CQRS** — dashboard-запросы не проходят через CRUD-сервисы и UoW; используют прямые read-only сессии
- **Отдельный модуль запросов** (`dashboard_queries.py`) в каждом домене — не смешивается с бизнес-сервисами
- **Без новых таблиц** — все данные агрегируются из существующих таблиц через SQL
- **Без побочных эффектов** — только SELECT-запросы

---

## 2. Техническая архитектура

### 2.1 Размещение файлов

```
src/
├── api/v1/backoffice/dashboard/
│   ├── __init__.py          # dashboard_router, монтируется в backoffice
│   ├── orders.py            # Эндпоинты EP-1..EP-7 (BR-1..BR-5, BR-15, BR-16)
│   ├── finances.py          # Эндпоинты EP-8..EP-12, EP-21 (BR-6..BR-9, BR-20)
│   ├── inventory.py         # Эндпоинты EP-13..EP-16, EP-18, EP-19 (BR-10..BR-13, BR-17, BR-18)
│   └── couriers.py          # Эндпоинты EP-17, EP-20 (BR-14, BR-19)
│
├── modules/orders/
│   ├── dashboard_queries.py # SQL-запросы для order analytics
│   └── dashboard_schemas.py # Pydantic-схемы ответов
│
├── modules/finances/
│   ├── dashboard_queries.py # SQL-запросы для finance analytics
│   └── dashboard_schemas.py # Pydantic-схемы ответов
│
├── modules/inventory/
│   ├── dashboard_queries.py # SQL-запросы для inventory analytics
│   └── dashboard_schemas.py # Pydantic-схемы ответов
│
└── modules/users/
    └── dashboard_queries.py # SQL-запросы для courier fleet (uses User + Inventory)
```

### 2.2 Паттерн Query-объекта

Каждый `dashboard_queries.py` содержит класс, принимающий `AsyncSession` (read-only) и предоставляющий методы-запросы:

```python
class OrderDashboardQueries:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_orders_summary(self, ...) -> OrdersSummary:
        ...
```

FastAPI dependency:

```python
from src.infrastructure.database.session import get_session

async def get_order_dashboard_queries(
    session: AsyncSession = Depends(get_session),
) -> OrderDashboardQueries:
    return OrderDashboardQueries(session)
```

> **Примечание:** В проекте единая session dependency — `get_session()` из `src/infrastructure/database/session.py`. Отдельной read-only сессии нет. Dashboard queries используют ту же сессию, но **не вызывают** `commit()` / `flush()`.

Это легче, чем полный UoW: нет `commit()`, нет транзакций, только `SELECT`.

### 2.3 Общие параметры

Все аналитические эндпоинты принимают стандартный набор фильтров через query params:

```python
class PeriodFilter(BaseModel):
    date_from: date | None = None  # Если не указана — 30 дней назад
    date_to: date | None = None    # Если не указана — сегодня
```

```python
class GranularityParam(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
```

### 2.4 Глобальные правила фильтрации данных

Во **всех** dashboard-запросах необходимо исключать системных пользователей:

```python
from src.core.constants import SYSTEM_USER_ID, WALKIN_USER_ID

# В каждом запросе, возвращающем данные по клиентам:
WHERE users.id NOT IN (SYSTEM_USER_ID, WALKIN_USER_ID)

# В запросах по заказам — Walk-in заказы ВКЛЮЧАЮТСЯ в общую статистику
# (они — реальные продажи), но ИСКЛЮЧАЮТСЯ из:
# - Топ клиентов (EP-7)
# - Должников (EP-10)
# - Должников по таре (EP-15)
```

**Обоснование (BUSINESS.md §4):** Walk-in user — системная сущность для анонимных покупок. Его баланс обнуляется после каждой продажи. Включение в рейтинги и списки должников некорректно.

---

## 3. Спецификация эндпоинтов

### 3.1 Orders Dashboard

#### EP-1: `GET /api/v1/backoffice/dashboard/orders/summary`

**BRD:** BR-1 (Операционная сводка дня)
**Scope:** `orders:read`
**Описание:** Операционный снимок для диспетчера — комбинация текущего состояния всех активных заказов + статистика за сегодня.

**Response Schema:**

```python
class OrderStatusCount(BaseModel):
    status: str       # OrderStatus value
    count: int

class OrdersSummary(BaseModel):
    # --- Активные заказы (все даты, незавершённые) ---
    active_by_status: list[OrderStatusCount]  # NEW, ASSIGNED, IN_TRANSIT, ARRIVED
    unassigned_orders: int                    # NEW заказы типа delivery без курьера

    # --- Статистика за сегодня ---
    total_today: int                          # всего создано сегодня
    delivered_today: int                      # DELIVERED + PICKUP_COMPLETED сегодня
    cancelled_today: int                      # CANCELLED сегодня
    revenue_today: int                        # тийины, сумма завершённых сегодня
    by_sale_type: dict[str, int]             # {"delivery": N, "warehouse_pickup": N} за сегодня

    # --- Ресурсы ---
    active_couriers: int                      # курьеры с is_active транспортом
```

**Изменение vs v1.0:** Разделение на «активные заказы» (all time, non-terminal) и «статистика за сегодня». Диспетчеру критично видеть ВСЕ незавершённые заказы, включая вчерашние — это основа оперативного управления (dashboard_orders.md §3.2: «Незакрытые заказы — заказы старше 24ч без доставки — целевое значение 0»).

**SQL-логика:**

```sql
-- Активные заказы (НЕ фильтруем по дате!)
SELECT status, COUNT(*) FROM orders
WHERE status IN ('new', 'assigned', 'in_transit', 'arrived')
  AND is_active = true
GROUP BY status;

-- Незназначенные
SELECT COUNT(*) FROM orders
WHERE status = 'new' AND sale_type = 'delivery'
  AND courier_id IS NULL AND is_active = true;

-- Сегодня
SELECT
  COUNT(*) AS total_today,
  COUNT(*) FILTER (WHERE status IN ('delivered', 'pickup_completed')) AS delivered_today,
  COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_today,
  COALESCE(SUM(total_amount) FILTER (WHERE status IN ('delivered', 'pickup_completed')), 0) AS revenue_today
FROM orders
WHERE created_at::date = CURRENT_DATE AND is_active = true;

-- Активные курьеры
SELECT COUNT(DISTINCT user_id) FROM inventories
WHERE type = 'COURIER' AND is_active = true;
```

---

#### EP-2: `GET /api/v1/backoffice/dashboard/orders/trends`

**BRD:** BR-2 (Тренд заказов)
**Scope:** `orders:read`
**Query Params:** `date_from`, `date_to`, `granularity` (day|week|month), `sale_type` (delivery|warehouse_pickup|null), `client_type` (client_b2c|client_b2b|null)

**Response Schema:**

```python
class OrderTrendPoint(BaseModel):
    period: str          # "2026-03-15" | "2026-W12" | "2026-03"
    orders_count: int
    revenue: int         # тийины
    avg_order_value: int # тийины

class OrderTrendResponse(BaseModel):
    points: list[OrderTrendPoint]
    total_orders: int
    total_revenue: int
```

**SQL-логика:**

```sql
SELECT
  date_trunc(:granularity, created_at)::date AS period,
  COUNT(*) AS orders_count,
  SUM(total_amount) AS revenue,
  AVG(total_amount)::bigint AS avg_order_value
FROM orders
  JOIN users ON orders.client_id = users.id
WHERE status IN ('delivered', 'pickup_completed')
  AND created_at BETWEEN :date_from AND :date_to
  AND is_active = true
  -- Опциональные фильтры:
  AND (:sale_type IS NULL OR orders.sale_type = :sale_type)
  AND (:client_type IS NULL OR users.role = :client_type)
GROUP BY 1
ORDER BY 1;
```

**Примечание:** Считаем только завершённые заказы (delivered, pickup_completed) — это реальная выручка. Отменённые не генерируют дохода.

---

#### EP-3: `GET /api/v1/backoffice/dashboard/orders/funnel`

**BRD:** BR-3 (Воронка статусов)
**Scope:** `orders:read`
**Query Params:** `date_from`, `date_to`

**Response Schema:**

```python
class StatusFunnelItem(BaseModel):
    status: str
    count: int
    percentage: float    # от total

class OrderFunnelResponse(BaseModel):
    total: int           # всего заказов за период
    statuses: list[StatusFunnelItem]  # отсортировано по FSM-порядку
```

**SQL-логика:**

```sql
SELECT status, COUNT(*) AS count
FROM orders
WHERE created_at BETWEEN :date_from AND :date_to
  AND is_active = true
GROUP BY status;
```

**Важное уточнение:** Это **распределение по текущему статусу**, а НЕ конверсионная воронка. Истинная воронка (сколько заказов _прошло_ через каждый этап) требует таблицы `order_status_history`, которой пока нет.

Для бизнеса доставки воды распределение по текущему статусу достаточно информативно:

- Большое количество в «NEW» → проблема с назначением курьеров
- Большое количество в «ASSIGNED» → курьеры не выезжают
- Высокий % «CANCELLED» → проблема с качеством/доступностью

**Будущее улучшение:** Добавить таблицу `order_status_history` (order_id, status, timestamp) для полноценной конверсионной воронки и расчёта среднего времени на каждом этапе.

**Порядок сортировки в ответе:**

```python
_FSM_ORDER = [
    "new", "assigned", "in_transit", "arrived",
    "delivered", "pickup_completed", "cancelled",
]
```

---

#### EP-4: `GET /api/v1/backoffice/dashboard/orders/heatmap`

**BRD:** BR-4 (Тепловая карта)
**Scope:** `orders:read`
**Query Params:** `date_from`, `date_to`

**Response Schema:**

```python
class HeatmapCell(BaseModel):
    day_of_week: int     # 1=Пн, 7=Вс (ISO 8601)
    hour: int            # 0-23 (по Ташкенту)
    count: int

class OrderHeatmapResponse(BaseModel):
    cells: list[HeatmapCell]
    max_count: int       # для нормализации цвета на фронте
```

**SQL-логика:**

```sql
SELECT
  EXTRACT(ISODOW FROM created_at AT TIME ZONE 'Asia/Tashkent') AS day_of_week,
  EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Tashkent') AS hour,
  COUNT(*) AS count
FROM orders
WHERE created_at BETWEEN :date_from AND :date_to
  AND is_active = true
GROUP BY 1, 2
ORDER BY 1, 2;
```

> **Изменение vs v1.0:** Используется `EXTRACT(ISODOW ...)` (возвращает 1=Пн..7=Вс по ISO 8601), а не `EXTRACT(DOW ...)` (возвращает 0=Вс..6=Сб). Конвертация в `AT TIME ZONE 'Asia/Tashkent'` (UTC+5) для корректного отображения пиковых часов по местному времени.

---

#### EP-5: `GET /api/v1/backoffice/dashboard/orders/payment-breakdown`

**BRD:** BR-5 (Разбивка способов оплаты)
**Scope:** `orders:read`
**Query Params:** `date_from`, `date_to`

**Response Schema:**

```python
class PaymentMethodStats(BaseModel):
    method: str          # PaymentMethod value: "cash", "card", "contract"
    orders_count: int
    total_amount: int    # тийины

class PaymentBreakdownResponse(BaseModel):
    methods: list[PaymentMethodStats]
    total_orders: int
    total_amount: int
```

**SQL-логика:**

```sql
SELECT
  payment_method AS method,
  COUNT(*) AS orders_count,
  SUM(total_amount) AS total_amount
FROM orders
WHERE status IN ('delivered', 'pickup_completed')
  AND created_at BETWEEN :date_from AND :date_to
  AND is_active = true
GROUP BY payment_method;
```

> **Бизнес-контекст (BUSINESS.md §6.3):** Самовывоз (`warehouse_pickup`) всегда оплачивается наличными. Поэтому в разрезе `CONTRACT` будут только delivery-заказы от B2B-клиентов.

---

#### EP-6: `GET /api/v1/backoffice/dashboard/orders/partial-deliveries`

**BRD:** BR-15 (Частичные доставки)
**Scope:** `orders:read`
**Query Params:** `date_from`, `date_to`

**Response Schema:**

```python
class PartialDeliveryStats(BaseModel):
    total_deliveries: int
    partial_deliveries: int
    partial_rate: float           # 0.0 - 1.0
```

> **Критическое изменение vs v1.0:** Убраны поля `total_ordered_amount`, `total_delivered_amount`, `lost_revenue`.

**Обоснование:** При частичной доставке `order_items.quantity` **перезаписывается** фактическим количеством, а `order.total_amount` пересчитывается (см. `BaseOrderService._handle_order_fulfillment` lines 846-881). Оригинальные заказанные количества **не сохраняются** в системе. Поэтому невозможно вычислить «потерянную выручку» — разница между заказанным и доставленным недоступна ретроспективно.

**Детектирование частичных доставок:** Единственный надёжный способ — анализ складских перемещений. При полной доставке создаётся один `StockTransfer` типа `CLIENT_DELIVERY`. При частичной — тот же transfer, но с количествами, не совпадающими с исходными order_items (которые уже перезаписаны).

**Альтернативный подход (рекомендуется):** Добавить boolean-поле `is_partial_delivery` в таблицу `orders`, которое устанавливается в `_handle_order_fulfillment` при обнаружении частичной доставки. Это дешёвое изменение, позволяющее впоследствии строить точную аналитику.

**SQL-логика (без модификации модели — эвристика):**

```sql
-- Подсчёт заказов с пометкой о частичной доставке пока невозможен напрямую.
-- Эвристика: сравнить сумму items с total_amount НЕ работает,
-- т.к. items.quantity уже перезаписаны.

-- До реализации is_partial_delivery поле:
-- Возвращать null / заглушку с пояснением "requires schema change"
```

**Решение для реализации:**

1. **Фаза 0 (schema change):** Добавить `is_partial_delivery: bool = False` в `Order` модель. В `_handle_order_fulfillment`: установить `True`, если `actual_items_dto` содержит хотя бы один item с quantity < оригинального.
2. **Фаза 1 (dashboard query):** `COUNT(*) FILTER (WHERE is_partial_delivery)` — тривиальный запрос.

> **Этот эндпоинт переносится из Фазы 3 в Фазу 3+** (зависит от schema change). Без поля `is_partial_delivery` эндпоинт реализовать корректно невозможно.

---

#### EP-7: `GET /api/v1/backoffice/dashboard/orders/top-clients`

**BRD:** BR-16 (Топ клиентов)
**Scope:** `orders:read`
**Query Params:** `date_from`, `date_to`, `limit` (default 10), `sort_by` (orders_count|total_amount)

**Response Schema:**

```python
class TopClientItem(BaseModel):
    client_id: uuid.UUID
    client_name: str
    client_type: str     # Role value (client_b2c / client_b2b)
    orders_count: int
    total_amount: int    # тийины

class TopClientsResponse(BaseModel):
    clients: list[TopClientItem]
```

**SQL-логика:**

```sql
SELECT
  u.id AS client_id,
  ui.full_name AS client_name,
  u.role AS client_type,
  COUNT(*) AS orders_count,
  SUM(o.total_amount) AS total_amount
FROM orders o
  JOIN users u ON o.client_id = u.id
  LEFT JOIN user_identities ui ON u.id = ui.user_id
WHERE o.status IN ('delivered', 'pickup_completed')
  AND o.created_at BETWEEN :date_from AND :date_to
  AND o.is_active = true
  AND u.id NOT IN (:SYSTEM_USER_ID, :WALKIN_USER_ID)  -- исключаем системных
GROUP BY u.id, ui.full_name, u.role
ORDER BY :sort_by DESC
LIMIT :limit;
```

---

### 3.2 Finance Dashboard

#### EP-8: `GET /api/v1/backoffice/dashboard/finances/revenue-trend`

**BRD:** BR-6 (Динамика выручки)
**Scope:** `finances:read`
**Query Params:** `date_from`, `date_to`, `granularity` (day|week|month)

**Response Schema:**

```python
class RevenueTrendPoint(BaseModel):
    period: str
    revenue: int         # тийины (положительное число)
    orders_count: int

class RevenueTrendResponse(BaseModel):
    points: list[RevenueTrendPoint]
    total_revenue: int
    total_orders: int
    change_percent: float | None  # % изменения vs аналогичный предыдущий период (BRD v1.3 BR-6)
```

**SQL-логика — через orders (рекомендуется):**

```sql
SELECT
  date_trunc(:granularity, created_at)::date AS period,
  SUM(total_amount) AS revenue,
  COUNT(*) AS orders_count
FROM orders
WHERE status IN ('delivered', 'pickup_completed')
  AND created_at BETWEEN :date_from AND :date_to
  AND is_active = true
GROUP BY 1
ORDER BY 1;
```

> **Изменение vs v1.0:** Выбран Вариант A (через orders) вместо Вариант B (через transactions).
>
> **Обоснование:** Для бизнес-аналитики выручки orders — первичный источник. Transactions включают ручные проводки, инкассации, возвраты и другие операции, не связанные напрямую с продажами, что исказит график. Если потребуется финансовый анализ через двойную запись — это отдельный эндпоинт.

---

#### EP-9: `GET /api/v1/backoffice/dashboard/finances/debt-aging`

**BRD:** BR-7 (Aging-бакеты дебиторки)
**Scope:** `finances:read`

**Response Schema:**

```python
class AgingBucket(BaseModel):
    label: str           # "0-7 дней", "8-14 дней", ...
    min_days: int
    max_days: int | None # None для последнего бакета (60+)
    clients_count: int
    total_amount: int    # тийины

class DebtAgingResponse(BaseModel):
    buckets: list[AgingBucket]
    total_debt: int
    total_debtors: int

# Три источника дебиторки (BRD v1.3 BR-7):
# 1. Карточные платежи до подтверждения (PENDING) — формально должник
# 2. B2B по договору (contract) — сознательный долг
# 3. Неоплаченные доставки — редкость
# PENDING-должники включаются в бакеты; фронтенд разделяет визуально.
```

**Определение «давности долга»:**

«Дней без оплаты» = количество дней с момента **последнего платежа** клиента (последняя COMPLETED транзакция, где деньги списываются с CLIENT-счёта, т.е. `from_id = client_account_id`).

Если клиент **никогда не платил** — считаем дни от даты создания аккаунта.

> **Обоснование (BUSINESS.md §8.2):** В бизнесе доставки воды с недельным циклом заказов, «дней без оплаты» — более релевантная метрика, чем «дней с момента возникновения долга». Клиент может накопить долг за 3 доставки, но если он платил 5 дней назад — это нормально.

**Бакеты** (адаптированы под цикл заказов воды — BUSINESS.md показывает еженедельные заказы):

| Бакет          | Диапазон   | Интерпретация          |
| -------------- | ---------- | ---------------------- |
| Текущий        | 0-7 дней   | Нормальный цикл оплаты |
| Предупреждение | 8-14 дней  | Пропущен один цикл     |
| Просрочка      | 15-30 дней | Активная проблема      |
| Критично       | 31-60 дней | Требует вмешательства  |
| Безнадёжный    | 60+ дней   | Риск списания          |

**SQL-логика:**

```sql
WITH client_debts AS (
  SELECT
    a.id AS account_id,
    a.user_id,
    a.balance,
    (
      SELECT MAX(t.created_at)
      FROM transactions t
      WHERE t.from_id = a.id
        AND t.status = 'completed'
    ) AS last_payment_at,
    a.created_at AS account_created_at
  FROM accounts a
  WHERE a.type = 'CLIENT'
    AND a.balance > 0
    AND a.user_id NOT IN (:SYSTEM_USER_ID, :WALKIN_USER_ID)
),
aged AS (
  SELECT
    balance,
    EXTRACT(DAY FROM
      CURRENT_TIMESTAMP - COALESCE(last_payment_at, account_created_at)
    )::int AS days_overdue
  FROM client_debts
)
SELECT
  CASE
    WHEN days_overdue <= 7  THEN '0-7 дней'
    WHEN days_overdue <= 14 THEN '8-14 дней'
    WHEN days_overdue <= 30 THEN '15-30 дней'
    WHEN days_overdue <= 60 THEN '31-60 дней'
    ELSE '60+ дней'
  END AS label,
  COUNT(*) AS clients_count,
  SUM(balance) AS total_amount
FROM aged
GROUP BY 1
ORDER BY MIN(days_overdue);
```

---

#### EP-10: `GET /api/v1/backoffice/dashboard/finances/top-debtors`

**BRD:** BR-8 (Топ должников)
**Scope:** `finances:read`
**Query Params:** `limit` (default 10)

**Response Schema:**

```python
class TopDebtorItem(BaseModel):
    client_id: uuid.UUID
    client_name: str
    client_type: str     # "client_b2c" | "client_b2b"
    phone: str
    debt_amount: int     # тийины
    last_payment_date: date | None
    days_overdue: int

class TopDebtorsResponse(BaseModel):
    debtors: list[TopDebtorItem]
    total_debt: int
```

**SQL-логика:**

```sql
SELECT
  u.id AS client_id,
  ui.full_name AS client_name,
  u.role AS client_type,
  ui.phone,
  a.balance AS debt_amount,
  (
    SELECT MAX(t.created_at)::date
    FROM transactions t
    WHERE t.from_id = a.id AND t.status = 'completed'
  ) AS last_payment_date,
  EXTRACT(DAY FROM
    CURRENT_TIMESTAMP - COALESCE(
      (SELECT MAX(t.created_at) FROM transactions t WHERE t.from_id = a.id AND t.status = 'completed'),
      a.created_at
    )
  )::int AS days_overdue
FROM accounts a
  JOIN users u ON a.user_id = u.id
  LEFT JOIN user_identities ui ON u.id = ui.user_id
WHERE a.type = 'CLIENT'
  AND a.balance > 0
  AND u.id NOT IN (:SYSTEM_USER_ID, :WALKIN_USER_ID)
ORDER BY a.balance DESC
LIMIT :limit;
```

> **Переиспользование:** Логика близка к `BillingService.get_client_debts()` / `AccountRepository.get_client_debtors()`. Для dashboard_queries строим отдельный оптимизированный запрос с `days_overdue`, который в существующем сервисе отсутствует.

---

#### EP-11: `GET /api/v1/backoffice/dashboard/finances/payment-methods`

**BRD:** BR-5 (финансовая призма — суммы, а не количество заказов)
**Scope:** `finances:read`
**Query Params:** `date_from`, `date_to`

**Response Schema:**

```python
class PaymentMethodFinanceStats(BaseModel):
    method: str          # "cash", "card", "contract"
    transactions_count: int
    total_amount: int    # тийины

class PaymentMethodsFinanceResponse(BaseModel):
    methods: list[PaymentMethodFinanceStats]
```

**SQL-логика:**

```sql
SELECT
  o.payment_method AS method,
  COUNT(*) AS transactions_count,
  SUM(o.total_amount) AS total_amount
FROM orders o
WHERE o.status IN ('delivered', 'pickup_completed')
  AND o.created_at BETWEEN :date_from AND :date_to
  AND o.is_active = true
GROUP BY o.payment_method;
```

> **Решение:** Используем `orders.payment_method` как источник (проще и корректнее, чем анализ to_account.type в transactions). Финансовый эндпоинт отличается от EP-5 тем, что может быть доступен бухгалтеру (scope `finances:read`) без доступа к заказам.

---

#### EP-12: `GET /api/v1/backoffice/dashboard/finances/summary-kpis`

**BRD:** BR-9 (Расчётные финансовые KPI)
**Scope:** `finances:read`
**Query Params:** `date_from`, `date_to`

**Response Schema:**

```python
class FinanceSummaryKPIs(BaseModel):
    # Основные метрики заказов
    avg_order_value: int              # тийины (AOV)
    total_orders: int
    total_revenue: int                # тийины

    # Карточные платежи
    card_confirmation_rate: float     # 0.0-1.0 (confirmed / total)
    card_rejection_rate: float        # 0.0-1.0 (rejected / total)
    avg_card_confirmation_hours: float | None  # среднее время в часах

    # Инкассация курьеров
    collection_rate: float            # 0.0-1.0 (сдано / собрано за период)

    # Просроченная задолженность (BRD v1.3 BR-9)
    overdue_debt_ratio: float         # 0.0-1.0 (сумма долгов > 7 дней / общая сумма долгов)
```

**SQL-логика:**

```sql
-- AOV и revenue (из orders)
SELECT
  COUNT(*) AS total_orders,
  SUM(total_amount) AS total_revenue,
  (SUM(total_amount) / NULLIF(COUNT(*), 0))::bigint AS avg_order_value
FROM orders
WHERE status IN ('delivered', 'pickup_completed')
  AND created_at BETWEEN :date_from AND :date_to
  AND is_active = true;

-- Card confirmation stats (из transactions)
SELECT
  COUNT(*) FILTER (WHERE status = 'completed') AS confirmed,
  COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
  COUNT(*) AS total,
  AVG(
    EXTRACT(EPOCH FROM (updated_at - created_at)) / 3600
  ) FILTER (WHERE status = 'completed') AS avg_hours
FROM transactions t
  JOIN accounts a ON t.to_id = a.id
WHERE a.type = 'CARD'
  AND t.created_at BETWEEN :date_from AND :date_to;

-- Collection rate (из courier accounts)
-- Собрано = сумма транзакций TO courier_account за период
-- Сдано = сумма транзакций FROM courier_account TO cash_account за период
WITH courier_activity AS (
  SELECT
    SUM(t.amount) FILTER (
      WHERE t.to_id = a.id
    ) AS collected,
    SUM(t.amount) FILTER (
      WHERE t.from_id = a.id
    ) AS deposited
  FROM accounts a
    JOIN transactions t ON t.to_id = a.id OR t.from_id = a.id
  WHERE a.type = 'COURIER'
    AND t.status = 'completed'
    AND t.created_at BETWEEN :date_from AND :date_to
)
SELECT
  COALESCE(deposited, 0)::float / NULLIF(COALESCE(collected, 0), 0) AS collection_rate
FROM courier_activity;
```

---

### 3.3 Inventory Dashboard

#### EP-13: `GET /api/v1/backoffice/dashboard/inventory/summary`

**BRD:** BR-10 (Складская сводка)
**Scope:** `inventory:read`
**Query Params:** `date_from`, `date_to` (для losses_period)

**Response Schema:**

```python
class InventorySummary(BaseModel):
    total_water_stock: int          # полные бутыли (склады + курьеры)
    total_container_stock: int      # пустые бутыли (склады + курьеры)
    total_equipment_stock: int      # оборудование (склады + курьеры) — BRD v1.2 BR-10
    containers_at_clients: int      # тара у клиентов
    stock_on_couriers: int          # всего единиц товара на курьерах
    losses_today: int               # списания за сегодня (количество единиц)
    losses_period: int              # списания за период date_from..date_to — BRD v1.2 BR-10
    active_couriers_count: int      # курьеров с активным транспортом
```

> **Изменение vs v1.0 — OQ-1 RESOLVED:** В таблице `products` есть поле `type` с enum `ProductType` (значения: `water`, `container`, `equipment`). Эвристика через `container_id` / `is_returnable` НЕ нужна. Используем прямой фильтр `products.type = 'water'` и `products.type = 'container'`.

**SQL-логика:**

```sql
SELECT
  -- Вода на складах и курьерах
  SUM(ib.quantity) FILTER (
    WHERE p.type = 'water' AND i.type IN ('WAREHOUSE', 'COURIER')
  ) AS total_water_stock,

  -- Тара (пустые бутыли) на складах и курьерах
  SUM(ib.quantity) FILTER (
    WHERE p.type = 'container' AND i.type IN ('WAREHOUSE', 'COURIER')
  ) AS total_container_stock,

  -- Оборудование на складах и курьерах (BRD v1.2)
  SUM(ib.quantity) FILTER (
    WHERE p.type = 'equipment' AND i.type IN ('WAREHOUSE', 'COURIER')
  ) AS total_equipment_stock,

  -- Тара у клиентов
  SUM(ib.quantity) FILTER (
    WHERE p.type = 'container' AND i.type = 'CLIENT'
  ) AS containers_at_clients,

  -- Всего товара на курьерах
  SUM(ib.quantity) FILTER (
    WHERE i.type = 'COURIER'
  ) AS stock_on_couriers

FROM inventory_balances ib
  JOIN inventories i ON ib.inventory_id = i.id
  JOIN products p ON ib.product_id = p.id
WHERE ib.quantity > 0;

-- Потери за сегодня (через stock_transactions — леджер)
SELECT COALESCE(SUM(st_txn.quantity), 0) AS losses_today
FROM stock_transactions st_txn
  JOIN stock_transfers st ON st_txn.transfer_id = st.id
  JOIN inventories i_to ON st_txn.to_id = i_to.id
WHERE i_to.type = 'VIRTUAL_LOSS'
  AND st_txn.created_at::date = CURRENT_DATE;

-- Потери за период (BRD v1.2)
SELECT COALESCE(SUM(st_txn.quantity), 0) AS losses_period
FROM stock_transactions st_txn
  JOIN inventories i_to ON st_txn.to_id = i_to.id
WHERE i_to.type = 'VIRTUAL_LOSS'
  AND st_txn.created_at BETWEEN :date_from AND :date_to;

-- Активные курьеры
SELECT COUNT(DISTINCT user_id) AS active_couriers_count
FROM inventories
WHERE type = 'COURIER' AND is_active = true;
```

**Изоляция кладовщика:** Если `warehouse_owner_id` передан, добавлять фильтр `AND i.user_id = :warehouse_owner_id` для строк с `i.type = 'WAREHOUSE'`. Остальные типы (COURIER, CLIENT) показываются всем или скрываются для кладовщика.

---

#### EP-14: `GET /api/v1/backoffice/dashboard/inventory/container-distribution`

**BRD:** BR-11 (Распределение тары)
**Scope:** `inventory:read`

**Response Schema:**

```python
class ContainerProductBreakdown(BaseModel):
    product_id: uuid.UUID
    product_name: str
    at_warehouses: int
    at_couriers: int
    at_clients: int
    lost: int
    total: int

class ContainerDistribution(BaseModel):
    at_warehouses: int
    at_couriers: int
    at_clients: int
    lost: int                 # VIRTUAL_LOSS balance
    total_in_system: int      # |VIRTUAL_VENDOR balance| (всего введено в систему)
    per_product: list[ContainerProductBreakdown]  # BRD v1.2 BR-11: разбивка по типам бутылей
```

**SQL-логика:**

```sql
SELECT
  SUM(ib.quantity) FILTER (WHERE i.type = 'WAREHOUSE') AS at_warehouses,
  SUM(ib.quantity) FILTER (WHERE i.type = 'COURIER') AS at_couriers,
  SUM(ib.quantity) FILTER (WHERE i.type = 'CLIENT') AS at_clients,
  SUM(ib.quantity) FILTER (WHERE i.type = 'VIRTUAL_LOSS') AS lost,
  ABS(SUM(ib.quantity) FILTER (WHERE i.type = 'VIRTUAL_VENDOR')) AS total_in_system
FROM inventory_balances ib
  JOIN inventories i ON ib.inventory_id = i.id
  JOIN products p ON ib.product_id = p.id
WHERE p.type = 'container';
```

---

#### EP-15: `GET /api/v1/backoffice/dashboard/inventory/container-debtors`

**BRD:** BR-12 (Должники по таре)
**Scope:** `inventory:read`
**Query Params:** `limit` (default 10)

**Response Schema:**

```python
class ContainerDebtorItem(BaseModel):
    client_id: uuid.UUID
    client_name: str
    client_type: str          # "client_b2c" | "client_b2b"
    container_balance: int    # количество бутылей
    last_order_date: date | None
    days_since_last_order: int | None

class ContainerDebtorsResponse(BaseModel):
    debtors: list[ContainerDebtorItem]
    total_containers_at_clients: int
```

**SQL-логика:**

```sql
SELECT
  u.id AS client_id,
  ui.full_name AS client_name,
  u.role AS client_type,
  SUM(ib.quantity) AS container_balance,
  (
    SELECT MAX(o.created_at)::date
    FROM orders o
    WHERE o.client_id = u.id
      AND o.status IN ('delivered', 'pickup_completed')
  ) AS last_order_date
FROM inventory_balances ib
  JOIN inventories i ON ib.inventory_id = i.id
  JOIN products p ON ib.product_id = p.id
  JOIN users u ON i.user_id = u.id
  LEFT JOIN user_identities ui ON u.id = ui.user_id
WHERE i.type = 'CLIENT'
  AND p.type = 'container'
  AND ib.quantity > 0
  AND u.id NOT IN (:SYSTEM_USER_ID, :WALKIN_USER_ID)
GROUP BY u.id, ui.full_name, u.role
ORDER BY container_balance DESC
LIMIT :limit;
```

---

#### EP-16: `GET /api/v1/backoffice/dashboard/inventory/movement-stats`

**BRD:** BR-13 (Статистика перемещений)
**Scope:** `inventory:read`
**Query Params:** `date_from`, `date_to`

**Response Schema:**

```python
class MovementTypeStats(BaseModel):
    transfer_type: str    # TransferType value
    transfers_count: int
    total_items: int      # сумма quantity по всем items

class MovementStatsResponse(BaseModel):
    types: list[MovementTypeStats]
    total_transfers: int
    total_items: int
```

**SQL-логика:**

```sql
SELECT
  st.type AS transfer_type,
  COUNT(DISTINCT st.id) AS transfers_count,
  SUM(st_txn.quantity) AS total_items
FROM stock_transfers st
  JOIN stock_transactions st_txn ON st_txn.transfer_id = st.id
WHERE st.created_at BETWEEN :date_from AND :date_to
  -- Изоляция кладовщика (BRD v1.2 BR-13, BUSINESS.md §13.14):
  -- AND (:warehouse_owner_id IS NULL OR
  --      st.from_id IN (SELECT id FROM inventories WHERE user_id = :warehouse_owner_id)
  --      OR st.to_id IN (SELECT id FROM inventories WHERE user_id = :warehouse_owner_id))
GROUP BY st.type;
```

> **Изоляция кладовщика (BRD v1.2):** При роли `STOREKEEPER` фильтровать перемещения, где склад-источник (`from_id`) или склад-получатель (`to_id`) принадлежит текущему пользователю. Закомментированный SQL выше показывает подход.

---

### 3.4 Courier Fleet Dashboard

#### EP-17: `GET /api/v1/backoffice/dashboard/couriers/fleet`

**BRD:** BR-14 (Дашборд курьеров)
**Scope:** `users:read`

> **Изменение vs v1.0:** Scope изменён с `couriers:read` (не существует) на `users:read` (ADMIN, ACCOUNTANT). Это корректный существующий scope для просмотра информации о сотрудниках.

**Response Schema:**

```python
class CourierVehicleBalance(BaseModel):
    product_id: uuid.UUID
    product_name: str
    quantity: int

class CourierFleetCard(BaseModel):
    courier_id: uuid.UUID
    courier_name: str
    vehicle_id: uuid.UUID | None
    vehicle_name: str | None       # номер машины
    is_active: bool                # есть ли активный транспорт
    vehicle_balances: list[CourierVehicleBalance]
    orders_assigned_today: int
    orders_delivered_today: int
    cash_balance: int              # тийины (баланс кассы курьера)
    cash_collected_today: int      # тийины (собрано за сегодня)
    containers_collected_today: int # тара, собранная у клиентов сегодня

class CourierFleetResponse(BaseModel):
    couriers: list[CourierFleetCard]
    total_active: int
    total_stock_on_couriers: int
    total_courier_cash: int        # тийины
```

> **Изменение vs v1.0:** Добавлено поле `containers_collected_today` (dashboard_orders.md §6.5: «Баланс тары по курьерам — сколько пустых бутылей собрал каждый курьер за сегодня»).

**SQL-логика — CTE-подход для производительности:**

```sql
WITH courier_users AS (
  SELECT u.id, ui.full_name
  FROM users u
    LEFT JOIN user_identities ui ON u.id = ui.user_id
  WHERE u.role = 'courier' AND u.is_active = true
),
courier_vehicles AS (
  SELECT i.user_id, i.id AS vehicle_id, i.name AS vehicle_name, i.is_active
  FROM inventories i
  WHERE i.type = 'COURIER' AND i.is_active = true
),
vehicle_stock AS (
  SELECT ib.inventory_id, p.id AS product_id, p.name AS product_name, ib.quantity
  FROM inventory_balances ib
    JOIN products p ON ib.product_id = p.id
  WHERE ib.quantity > 0
),
courier_accounts AS (
  SELECT a.user_id, a.id AS account_id, a.balance AS cash_balance
  FROM accounts a
  WHERE a.type = 'COURIER'
),
today_orders AS (
  SELECT
    courier_id,
    COUNT(*) FILTER (WHERE status NOT IN ('cancelled')) AS assigned_today,
    COUNT(*) FILTER (WHERE status = 'delivered') AS delivered_today
  FROM orders
  WHERE created_at::date = CURRENT_DATE AND courier_id IS NOT NULL
  GROUP BY courier_id
),
today_cash AS (
  SELECT
    a.user_id,
    SUM(t.amount) AS collected
  FROM transactions t
    JOIN accounts a ON t.to_id = a.id
  WHERE a.type = 'COURIER'
    AND t.status = 'completed'
    AND t.created_at::date = CURRENT_DATE
  GROUP BY a.user_id
),
today_containers AS (
  SELECT
    st.to_id AS inventory_id,
    SUM(sti.quantity) AS collected
  FROM stock_transfers st
    JOIN stock_transactions sti ON sti.transfer_id = st.id
    JOIN products p ON sti.product_id = p.id
  WHERE st.type = 'CLIENT_RETURN'
    AND st.status = 'COMPLETED'
    AND st.created_at::date = CURRENT_DATE
    AND p.type = 'container'
  GROUP BY st.to_id
)
SELECT
  cu.id AS courier_id,
  cu.full_name AS courier_name,
  cv.vehicle_id, cv.vehicle_name, cv.is_active,
  ca.cash_balance,
  COALESCE(tod.assigned_today, 0) AS orders_assigned_today,
  COALESCE(tod.delivered_today, 0) AS orders_delivered_today,
  COALESCE(tc.collected, 0) AS cash_collected_today,
  COALESCE(tcont.collected, 0) AS containers_collected_today
FROM courier_users cu
  LEFT JOIN courier_vehicles cv ON cu.id = cv.user_id
  LEFT JOIN courier_accounts ca ON cu.id = ca.user_id
  LEFT JOIN today_orders tod ON cu.id = tod.courier_id
  LEFT JOIN today_cash tc ON cu.id = tc.user_id
  LEFT JOIN today_containers tcont ON cv.vehicle_id = tcont.inventory_id;
```

Vehicle balances загружаются отдельным запросом или через nested subquery.

---

#### EP-18: `GET /api/v1/backoffice/dashboard/inventory/trends`

**BRD:** BR-17 (Тренды складских остатков)
**Scope:** `inventory:read`
**Query Params:** `date_from`, `date_to`, `product_type` (water|container|null)

**Response Schema:**

```python
class InventoryTrendPoint(BaseModel):
    date: str               # "2026-03-15"
    water_stock: int         # полные бутыли на складах + курьерах
    container_stock: int     # пустые бутыли на складах + курьерах
    containers_at_clients: int  # тара у клиентов

class InventoryTrendResponse(BaseModel):
    points: list[InventoryTrendPoint]
```

**SQL-логика:**

> **Сложность:** Высокая. `inventory_balances` хранит **текущее** состояние, не историческое. Для тренда нужно восстанавливать остатки на каждую дату из `stock_transactions` (append-only леджер).

```sql
-- Подход: для каждого дня периода считаем кумулятивные входящие - исходящие
-- из stock_transactions, сгруппированные по дню и типу продукта.
-- Текущий остаток (inventory_balances) - SUM(изменений после этого дня) = остаток на тот день.

WITH daily_movements AS (
  SELECT
    st_txn.created_at::date AS day,
    p.type AS product_type,
    i_to.type AS to_inv_type,
    i_from.type AS from_inv_type,
    st_txn.quantity
  FROM stock_transactions st_txn
    JOIN products p ON st_txn.product_id = p.id
    JOIN inventories i_to ON st_txn.to_id = i_to.id
    JOIN inventories i_from ON st_txn.from_id = i_from.id
  WHERE st_txn.created_at BETWEEN :date_from AND :date_to + INTERVAL '1 day'
)
-- Далее: агрегация по дням, расчёт running total
-- Конкретная реализация зависит от выбранного подхода (forward/backward from current balance)
```

> **Рекомендация:** Использовать подход «текущий баланс минус будущие изменения» — для каждого дня `D`: `balance_on_D = current_balance - SUM(changes after D)`. Это проще и точнее, чем прямой пересчёт.

---

#### EP-19: `GET /api/v1/backoffice/dashboard/inventory/virtual-accounts`

**BRD:** BR-18 (Баланс виртуальных счетов + контроль целостности)
**Scope:** `inventory:read`

**Response Schema:**

```python
class VirtualProductBalance(BaseModel):
    product_id: uuid.UUID
    product_name: str
    vendor_balance: int      # отрицательный (VIRTUAL_VENDOR)
    loss_balance: int        # положительный (VIRTUAL_LOSS)

class VirtualAccountsResponse(BaseModel):
    vendor_total: int                        # SUM |VIRTUAL_VENDOR| по всем продуктам
    loss_total: int                          # SUM VIRTUAL_LOSS по всем продуктам
    real_total: int                          # SUM (WAREHOUSE + COURIER + CLIENT)
    integrity_ok: bool                       # vendor_total == loss_total + real_total
    integrity_diff: int                      # разница (0 если ok)
    per_product: list[VirtualProductBalance]
    loss_trend_30d: list[int] | None         # потери по дням за последние 30 дней
```

**SQL-логика:**

```sql
-- Балансы виртуальных счетов по продуктам
SELECT
  p.id AS product_id,
  p.name AS product_name,
  SUM(ib.quantity) FILTER (WHERE i.type = 'VIRTUAL_VENDOR') AS vendor_balance,
  SUM(ib.quantity) FILTER (WHERE i.type = 'VIRTUAL_LOSS') AS loss_balance,
  SUM(ib.quantity) FILTER (WHERE i.type IN ('WAREHOUSE', 'COURIER', 'CLIENT')) AS real_balance
FROM inventory_balances ib
  JOIN inventories i ON ib.inventory_id = i.id
  JOIN products p ON ib.product_id = p.id
GROUP BY p.id, p.name;

-- Контрольная сумма: ABS(vendor_total) должен = loss_total + real_total
-- Если расхождение != 0 → integrity_ok = false (критический алерт)

-- Тренд потерь за 30 дней
SELECT
  st_txn.created_at::date AS day,
  SUM(st_txn.quantity) AS daily_losses
FROM stock_transactions st_txn
  JOIN inventories i ON st_txn.to_id = i.id
WHERE i.type = 'VIRTUAL_LOSS'
  AND st_txn.created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;
```

---

#### EP-20: `GET /api/v1/backoffice/dashboard/couriers/load-by-days`

**BRD:** BR-19 (Загрузка курьеров по дням)
**Scope:** `users:read`
**Query Params:** `date_from`, `date_to`

**Response Schema:**

```python
class CourierDayLoad(BaseModel):
    date: str                # "2026-03-15"
    courier_id: uuid.UUID
    courier_name: str
    deliveries_count: int

class CourierLoadResponse(BaseModel):
    data: list[CourierDayLoad]
    total_deliveries: int
    avg_per_courier: float
    max_load: int            # максимальная загрузка одного курьера за один день
```

**SQL-логика:**

```sql
SELECT
  o.created_at::date AS date,
  o.courier_id,
  ui.full_name AS courier_name,
  COUNT(*) AS deliveries_count
FROM orders o
  JOIN users u ON o.courier_id = u.id
  LEFT JOIN user_identities ui ON u.id = ui.user_id
WHERE o.status = 'delivered'
  AND o.created_at BETWEEN :date_from AND :date_to
  AND o.courier_id IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, deliveries_count DESC;
```

---

#### EP-21: `GET /api/v1/backoffice/dashboard/finances/revenue-by-segment`

**BRD:** BR-20 (Выручка по сегментам B2B/B2C)
**Scope:** `finances:read`
**Query Params:** `date_from`, `date_to`

**Response Schema:**

```python
class SegmentRevenue(BaseModel):
    segment: str             # "client_b2b" | "client_b2c"
    orders_count: int
    total_revenue: int       # тийины
    avg_order_value: int     # тийины

class RevenueBySegmentResponse(BaseModel):
    segments: list[SegmentRevenue]
    total_orders: int
    total_revenue: int
```

**SQL-логика:**

```sql
SELECT
  u.role AS segment,
  COUNT(*) AS orders_count,
  SUM(o.total_amount) AS total_revenue,
  (SUM(o.total_amount) / NULLIF(COUNT(*), 0))::bigint AS avg_order_value
FROM orders o
  JOIN users u ON o.client_id = u.id
WHERE o.status IN ('delivered', 'pickup_completed')
  AND o.created_at BETWEEN :date_from AND :date_to
  AND o.is_active = true
  AND u.id NOT IN (:SYSTEM_USER_ID, :WALKIN_USER_ID)
  AND u.role IN ('client_b2b', 'client_b2c')
GROUP BY u.role;
```

---

## 4. Scopes и авторизация

### 4.1 Использование существующих scopes

> **Решение (OQ-4 RESOLVED):** Используем существующие scopes. Новые dashboard-scopes не вводятся.

| Эндпоинт                               | Требуемый scope  | Роли с этим scope           |
| -------------------------------------- | ---------------- | --------------------------- |
| EP-1..EP-7 (orders)                    | `orders:read`    | ADMIN, CASHIER              |
| EP-8..EP-12, EP-21 (finances)          | `finances:read`  | ADMIN, ACCOUNTANT, CASHIER  |
| EP-13..EP-16, EP-18, EP-19 (inventory) | `inventory:read` | ADMIN, STOREKEEPER, CASHIER |
| EP-17, EP-20 (couriers)                | `users:read`     | ADMIN, ACCOUNTANT           |

> **Примечание:** COURIER и CLIENT_B2C/B2B имеют `orders:read`, но они используют отдельные роутеры (`/courier/`, `/client/`), не backoffice. Dashboard-роутер монтируется в `/backoffice/dashboard/`, доступ к которому ограничен middleware или дополнительной проверкой.

### 4.2 Изоляция данных кладовщика

Для EP-13 (складская сводка) и EP-16 (статистика перемещений):

- Если `current_user.role == STOREKEEPER`: данные фильтруются по складам, где `owner_id = current_user.id`
- Если ADMIN / CASHIER: показываются все склады

Реализация:

```python
warehouse_owner_id = (
    current_user.id
    if current_user.role == Role.STOREKEEPER
    else None
)
```

---

## 5. Маппинг эндпоинтов на существующую кодовую базу

### 5.1 Уже реализованные данные (можно переиспользовать)

| EP                       | Существующий метод                                           | Что нужно                                   |
| ------------------------ | ------------------------------------------------------------ | ------------------------------------------- |
| EP-10 (топ должников)    | `BillingService.get_client_debts()` → `ClientsDebtsResponse` | Расширить `days_overdue`                    |
| EP-13 (складская сводка) | `InventoryRepository.get_all_warehouses_with_balances()`     | Новый агрегирующий запрос                   |
| EP-15 (должники по таре) | `StockTransactionRepository.get_debtors_report()`            | Обернуть в schema, добавить last_order_date |
| EP-17 (курьеры)          | `BillingService.get_couriers_summary()` + inventory balances | Объединить в один запрос                    |

### 5.2 Полностью новые запросы

| EP    | Описание                                                          | Сложность |
| ----- | ----------------------------------------------------------------- | --------- |
| EP-1  | Orders summary (active + today stats)                             | Низкая    |
| EP-2  | Order trends (date_trunc + GROUP BY)                              | Средняя   |
| EP-3  | Order funnel (GROUP BY status с ordering)                         | Низкая    |
| EP-4  | Heatmap (ISODOW + HOUR + timezone)                                | Средняя   |
| EP-5  | Payment breakdown (GROUP BY payment_method)                       | Низкая    |
| EP-6  | Partial deliveries (**требует schema change**)                    | Высокая   |
| EP-7  | Top clients (GROUP BY client_id, ORDER BY)                        | Низкая    |
| EP-8  | Revenue trend (orders GROUP BY period)                            | Средняя   |
| EP-9  | Debt aging (buckets + last payment lateral)                       | Высокая   |
| EP-11 | Payment methods finance view                                      | Низкая    |
| EP-12 | Finance summary KPIs (multiple aggregations)                      | Средняя   |
| EP-14 | Container distribution (GROUP BY inventory type)                  | Низкая    |
| EP-16 | Movement stats (GROUP BY transfer_type)                           | Низкая    |
| EP-17 | Courier fleet (CTE multi-join)                                    | Высокая   |
| EP-18 | Inventory trends (backward from current balance)                  | Высокая   |
| EP-19 | Virtual accounts + integrity check (GROUP BY inv type + checksum) | Средняя   |
| EP-20 | Courier load by days (GROUP BY date, courier_id)                  | Низкая    |
| EP-21 | Revenue by B2B/B2C (GROUP BY user.role)                           | Низкая    |

---

## 6. Схемы данных (сводка SQL-источников)

### 6.1 Таблицы, используемые dashboard API

| Таблица                | Назначение в dashboard                                                                                                             |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `orders`               | Счётчики, тренды, воронка, heatmap, AOV, revenue                                                                                   |
| `order_items`          | _(не используется — данные перезаписываются при partial delivery)_                                                                 |
| `transactions`         | Card confirmation stats, инкассация, last_payment для aging                                                                        |
| `accounts`             | Балансы (клиент → долг, курьер → наличные)                                                                                         |
| `stock_transfers`      | Метаданные перемещений: тип, статус, from/to, order_id                                                                             |
| `stock_transactions`   | **Леджер движения товаров** (Event Sourcing, истина в последней инстанции). Объём в единицах, containers collected, потери, тренды |
| `stock_transfer_items` | Черновик строк накладной (до проведения). **НЕ используется** в dashboard-аналитике — только `stock_transactions`                  |
| `inventory_balances`   | Текущие остатки по всем точкам                                                                                                     |
| `inventories`          | Типы точек (WAREHOUSE, COURIER, CLIENT, VIRTUAL\_\*)                                                                               |
| `products`             | `type` enum: `water` / `container` / `equipment`                                                                                   |
| `users`                | Роли, ID для фильтрации                                                                                                            |
| `user_identities`      | Имена, телефоны                                                                                                                    |

### 6.2 Рекомендуемые индексы

```sql
-- Для тренда заказов (EP-2, EP-3, EP-5)
CREATE INDEX idx_orders_created_status
ON orders (created_at, status)
WHERE is_active = true;

-- Для heatmap (EP-4) — timezone conversion
CREATE INDEX idx_orders_created_at
ON orders (created_at)
WHERE is_active = true;

-- Для debt aging / top debtors (EP-9, EP-10)
CREATE INDEX idx_accounts_client_debt
ON accounts (balance DESC, user_id)
WHERE type = 'CLIENT' AND balance > 0;

-- Для last payment subquery (EP-9, EP-10)
CREATE INDEX idx_transactions_from_completed
ON transactions (from_id, created_at DESC)
WHERE status = 'completed';

-- Для container distribution (EP-14)
CREATE INDEX idx_inv_balances_positive
ON inventory_balances (inventory_id, product_id, quantity)
WHERE quantity > 0;

-- Для courier fleet orders today (EP-17)
CREATE INDEX idx_orders_courier_today
ON orders (courier_id, status)
WHERE is_active = true;
```

---

## 7. Фазирование реализации

### Фаза 1: MVP (P0 — 1-2 недели)

Самые критичные для ежедневной работы:

| EP    | Описание                            | BRD   | Сложность | Приоритет |
| ----- | ----------------------------------- | ----- | --------- | --------- |
| EP-1  | Orders summary (активные + сегодня) | BR-1  | Низкая    | P0        |
| EP-13 | Inventory summary (остатки)         | BR-10 | Средняя   | P0        |
| EP-14 | Container distribution (тара)       | BR-11 | Низкая    | P0        |
| EP-17 | Courier fleet (карточки курьеров)   | BR-14 | Высокая   | P0        |
| EP-19 | Virtual accounts + integrity check  | BR-18 | Средняя   | P0        |

**Обоснование:** Диспетчер — заказы и курьеров. Кладовщик — остатки. EP-19 — контроль целостности леджера (главный принцип BUSINESS.md §1).

### Фаза 2: Финансы (P1 — 1-2 недели)

| EP    | Описание                           | BRD   | Сложность | Приоритет |
| ----- | ---------------------------------- | ----- | --------- | --------- |
| EP-8  | Revenue trend (выручка по дням)    | BR-6  | Средняя   | P1        |
| EP-9  | Debt aging (бакеты дебиторки)      | BR-7  | Высокая   | P1        |
| EP-10 | Top debtors (список должников)     | BR-8  | Низкая    | P1        |
| EP-5  | Payment breakdown (способы оплаты) | BR-5  | Низкая    | P1        |
| EP-12 | Finance summary KPIs               | BR-9  | Средняя   | P1        |
| EP-21 | Revenue by B2B/B2C segment         | BR-20 | Низкая    | P1        |

**Обоснование:** Бухгалтеру — финансовая аналитика. EP-21 — критичная B2B/B2C разбивка для стратегических решений.

### Фаза 3: Аналитика (P2 — 1-2 недели)

| EP    | Описание                               | BRD   | Сложность | Приоритет |
| ----- | -------------------------------------- | ----- | --------- | --------- |
| EP-2  | Order trends (тренды)                  | BR-2  | Средняя   | P2        |
| EP-3  | Order funnel (воронка / распределение) | BR-3  | Низкая    | P2        |
| EP-4  | Heatmap (тепловая карта)               | BR-4  | Средняя   | P2        |
| EP-7  | Top clients                            | BR-16 | Низкая    | P2        |
| EP-11 | Payment methods (finance view)         | BR-5  | Низкая    | P2        |
| EP-15 | Container debtors (тара)               | BR-12 | Средняя   | P2        |
| EP-16 | Movement stats (перемещения)           | BR-13 | Низкая    | P2        |
| EP-18 | Inventory trends (7/30 дней)           | BR-17 | Высокая   | P2        |
| EP-20 | Courier load by days                   | BR-19 | Низкая    | P2        |

### Фаза 3+: Требует schema change

| EP   | Описание           | Зависимость                                  |
| ---- | ------------------ | -------------------------------------------- |
| EP-6 | Partial deliveries | Добавить `is_partial_delivery: bool` в Order |

**Обоснование:** EP-6 невозможно реализовать корректно без изменения модели данных.

---

## 8. Тестирование

### 8.1 Стратегия

- **Unit-тесты query-объектов:** Тестировать SQL-запросы на тестовой БД с сидированными данными
- **Integration-тесты эндпоинтов:** HTTP-запросы через httpx AsyncClient
- **Фикстуры:** Использовать `polyfactory` для генерации тестовых заказов, транзакций, балансов

### 8.2 Тест-кейсы (критические)

| EP    | Тест-кейс                                                      |
| ----- | -------------------------------------------------------------- |
| EP-1  | Пустая БД → все счётчики = 0                                   |
| EP-1  | 5 заказов в разных статусах → корректные active + today counts |
| EP-1  | Вчерашний незавершённый заказ → попадает в active_by_status    |
| EP-2  | Тренд за 7 дней с 3 заказами в разные дни → 3 точки с данными  |
| EP-4  | Heatmap корректно конвертирует UTC → Ташкент                   |
| EP-7  | Walk-in заказы не попадают в топ клиентов                      |
| EP-9  | 3 должника в разных бакетах → корректное распределение         |
| EP-9  | Клиент без платежей → days_overdue от даты создания аккаунта   |
| EP-10 | Walk-in и System не попадают в список должников                |
| EP-13 | ProductType.WATER корректно отделяется от CONTAINER            |
| EP-17 | Курьер с транспортом, балансами и заказами → полная карточка   |
| EP-17 | Курьер без транспорта → vehicle_id = null, is_active = false   |
| All   | Кладовщик видит только свои склады                             |
| All   | Бухгалтер не видит orders dashboard (scope check)              |

---

## 9. Мониторинг и SLA

### 9.1 Метрики

| Метрика                                 | Целевое значение |
| --------------------------------------- | ---------------- |
| p50 response time (summary endpoints)   | < 200 мс         |
| p95 response time (summary endpoints)   | < 500 мс         |
| p50 response time (analytics endpoints) | < 500 мс         |
| p95 response time (analytics endpoints) | < 2 сек          |
| Error rate                              | < 0.1%           |

### 9.2 Логирование

- Каждый dashboard-запрос логируется через стандартный `AccessLoggerMiddleware` (request_id, method, path, status, duration)
- Slow queries (> 1 сек) — structlog WARNING в dashboard_queries
- SQL-ошибки — structlog ERROR

---

## 10. Открытые вопросы

| #     | Вопрос                                                        | Влияние                           | Статус / Решение                                                                                                                                                                                                           |
| ----- | ------------------------------------------------------------- | --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OQ-1  | Как различать воду от тары в SQL?                             | EP-13, EP-14                      | ✅ **RESOLVED.** Используем `products.type` enum (`ProductType.WATER`, `ProductType.CONTAINER`, `ProductType.EQUIPMENT`). Эвристика не нужна.                                                                              |
| OQ-2  | Нужна ли `order_status_history` для воронки?                  | EP-3                              | ⏳ **DEFERRED.** Для MVP — распределение по текущему статусу. True funnel — отдельная задача.                                                                                                                              |
| OQ-3  | Timezone для heatmap?                                         | EP-4                              | ✅ **RESOLVED.** `AT TIME ZONE 'Asia/Tashkent'` + `EXTRACT(ISODOW ...)`.                                                                                                                                                   |
| OQ-4  | Новые scopes или существующие?                                | Все EP                            | ✅ **RESOLVED.** Существующие scopes (`orders:read`, `finances:read`, `inventory:read`, `users:read`).                                                                                                                     |
| OQ-5  | Определение воды/тары через CatalogService?                   | EP-13, EP-14                      | ✅ **RESOLVED.** Не нужно — `products.type` достаточно для SQL-фильтрации.                                                                                                                                                 |
| OQ-6  | Кешировать в Redis?                                           | NFR-2                             | ⏳ **DEFERRED.** На MVP — нет. RTK Query polling + SQL-индексы достаточны.                                                                                                                                                 |
| OQ-7  | Как определить частичную доставку ретроспективно?             | EP-6                              | 🔴 **BLOCKED.** `order_items.quantity` перезаписывается при доставке. Нужно добавить `Order.is_partial_delivery: bool`.                                                                                                    |
| OQ-8  | Нужен ли отдельный scope `dashboard:*`?                       | Авторизация                       | ✅ **RESOLVED.** Нет — используем существующие. Scope `couriers:read` не существует, используем `users:read`.                                                                                                              |
| OQ-9  | `stock_transfer_items` vs `stock_transactions` для аналитики? | EP-13, EP-16, EP-17, EP-18, EP-19 | ✅ **RESOLVED (v2.0).** `stock_transactions` — леджер (Event Sourcing, истина в последней инстанции). `stock_transfer_items` — черновик до проведения. Для dashboard-аналитики используем **только** `stock_transactions`. |
| OQ-10 | Как строить тренды остатков без исторических снимков?         | EP-18                             | ⏳ **APPROACH DEFINED.** Подход «текущий баланс минус будущие изменения»: `balance_on_D = current_balance - SUM(stock_transactions after D)`. Сложность высокая, но без materialized views выполнимо.                      |

---

## 11. Зависимости

| Зависимость                                       | Статус                                | Блокирует                |
| ------------------------------------------------- | ------------------------------------- | ------------------------ |
| Таблицы и модели                                  | ✅ Готово                             | —                        |
| PG-триггеры для балансов                          | ✅ Готово                             | —                        |
| `ProductType` enum (water/container/equipment)    | ✅ Готово                             | —                        |
| `get_session()` dependency                        | ✅ Готово                             | —                        |
| Финансовый dashboard endpoint                     | ✅ Готово (`GET /finances/dashboard`) | —                        |
| `BillingService.get_couriers_summary()`           | ✅ Готово                             | EP-17 (переиспользуется) |
| `BillingService.get_client_debts()`               | ✅ Готово                             | EP-10 (расширяется)      |
| `StockTransactionRepository.get_debtors_report()` | ✅ Готово                             | EP-15 (переиспользуется) |
| Фронтенд dashboard pages                          | ❌ Не начат                           | Не блокирует API         |
| SQL-индексы для dashboard                         | ❌ Не созданы                         | Производительность       |
| `Order.is_partial_delivery` field                 | ❌ Не создано                         | EP-6                     |

---

## 12. Необходимые изменения в существующих моделях

### 12.1 Order — добавить `is_partial_delivery`

**Зачем:** EP-6 (Partial Deliveries). Текущая реализация `_handle_order_fulfillment` перезаписывает `order_items.quantity` фактическими количествами, теряя информацию о частичной доставке.

**Изменение:**

```python
# src/modules/orders/models.py
class Order(Base):
    ...
    is_partial_delivery: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false",
    )
```

```python
# src/modules/orders/services.py :: _handle_order_fulfillment
# После пересчёта item quantities:
if any(
    actual_map.get(item.product_id, item.quantity) < item.quantity
    for item in order.items
):
    order.is_partial_delivery = True
```

**Миграция:** Alembic `ALTER TABLE orders ADD COLUMN is_partial_delivery BOOLEAN NOT NULL DEFAULT false;`

**Приоритет:** P2 (Фаза 3+). Не блокирует MVP.

---

## Приложение А: Полный список эндпоинтов

| #     | Метод | Путь                                          | BRD   | Scope          | Фаза |
| ----- | ----- | --------------------------------------------- | ----- | -------------- | ---- |
| EP-1  | GET   | `/dashboard/orders/summary`                   | BR-1  | orders:read    | 1    |
| EP-2  | GET   | `/dashboard/orders/trends`                    | BR-2  | orders:read    | 3    |
| EP-3  | GET   | `/dashboard/orders/funnel`                    | BR-3  | orders:read    | 3    |
| EP-4  | GET   | `/dashboard/orders/heatmap`                   | BR-4  | orders:read    | 3    |
| EP-5  | GET   | `/dashboard/orders/payment-breakdown`         | BR-5  | orders:read    | 2    |
| EP-6  | GET   | `/dashboard/orders/partial-deliveries`        | BR-15 | orders:read    | 3+   |
| EP-7  | GET   | `/dashboard/orders/top-clients`               | BR-16 | orders:read    | 3    |
| EP-8  | GET   | `/dashboard/finances/revenue-trend`           | BR-6  | finances:read  | 2    |
| EP-9  | GET   | `/dashboard/finances/debt-aging`              | BR-7  | finances:read  | 2    |
| EP-10 | GET   | `/dashboard/finances/top-debtors`             | BR-8  | finances:read  | 2    |
| EP-11 | GET   | `/dashboard/finances/payment-methods`         | BR-5  | finances:read  | 3    |
| EP-12 | GET   | `/dashboard/finances/summary-kpis`            | BR-9  | finances:read  | 2    |
| EP-13 | GET   | `/dashboard/inventory/summary`                | BR-10 | inventory:read | 1    |
| EP-14 | GET   | `/dashboard/inventory/container-distribution` | BR-11 | inventory:read | 1    |
| EP-15 | GET   | `/dashboard/inventory/container-debtors`      | BR-12 | inventory:read | 3    |
| EP-16 | GET   | `/dashboard/inventory/movement-stats`         | BR-13 | inventory:read | 3    |
| EP-17 | GET   | `/dashboard/couriers/fleet`                   | BR-14 | users:read     | 1    |
| EP-18 | GET   | `/dashboard/inventory/trends`                 | BR-17 | inventory:read | 3    |
| EP-19 | GET   | `/dashboard/inventory/virtual-accounts`       | BR-18 | inventory:read | 1    |
| EP-20 | GET   | `/dashboard/couriers/load-by-days`            | BR-19 | users:read     | 3    |
| EP-21 | GET   | `/dashboard/finances/revenue-by-segment`      | BR-20 | finances:read  | 2    |

**Итого: 21 эндпоинт, 4 домена, 3 фазы (+1 отложенная)**
