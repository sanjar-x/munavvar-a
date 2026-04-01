# BRD Frontend — Business Requirements Document

# Dashboard Frontend для MunavvarA (HOD)

**Версия:** 1.4
**Дата:** 2026-04-01
**Статус:** Production
**Автор:** Engineering
**Backend BRD:** `research/DASHBOARD_BRD.md` (v1.5, 20 BR)
**Backend PRD:** `research/DASHBOARD_PRD.md` (v2.0, 21 EP)
**UI Research:** `research/dashboard_ui.md`
**UX Research:** `research/dashboard_ux.md`

**Changelog v1.4 (полная сверка BRD ↔ Frontend BRD ↔ Codebase):**

- **D-1:** §4.2 — убрана фраза «после реализации EP-8, EP-10 на бэкенде» — все EP реализованы
- **D-2:** §4.3 EP-14 — исправлено: ContainerDonut НЕ фильтруется по кладовщику. EP-14 возвращает глобальные данные (в отличие от EP-13 и EP-16, где есть `_storekeeper_id`)
- **D-3:** §6.9 EP-10 `phone` — добавлена заметка: поле **всегда `null`** в бэкенде (сознательно, для избежания N+1 запросов). Колонка «Телефон» показывает «—»
- **D-4:** §6.12 EP-15 `days_since_last_order` — добавлена заметка: поле **всегда `null`** в бэкенде (не вычисляется). Колонка «Дней без заказа» показывает «—»
- **D-5:** §6.15 EP-18 — уточнён дефолт: API **по умолчанию возвращает 7 дней** (не 30, как остальные EP). PeriodFilter должен отправлять `date_from`/`date_to` явно при выборе 30 дней
- **D-6:** §6 — добавлена заметка о структурной разнице EP-5 vs EP-11: EP-5 имеет `total_orders` + `total_amount` на верхнем уровне, EP-11 — только `methods[]`. Фронтенд должен вычислять итоги для EP-11 самостоятельно
- **D-7:** Добавлено Приложение Б: Полный реестр API-контрактов — точные поля, типы, дефолты, query params для каждого из 20 EP. Единый источник истины для фронтенд-интеграции
- Итого: 7 исправлений + новое приложение

**Changelog v1.3 (backend sync — все 20 EP реализованы):**

- **CRITICAL:** §16 Зависимости — обновлены статусы: все 20 эндпоинтов (EP-1..EP-5, EP-7..EP-21) теперь **✅ Реализованы** на бэкенде. EP-6 остаётся 🔴 (требует schema change)
- **B-1:** §5.3 EP-13 — убраны `date_from`/`date_to` query params и `losses_period` — бэкенд НЕ принимает эти параметры, схема НЕ содержит `losses_period`. Оставлен только `losses_today`
- **B-2:** §4.3 EP-13 — убрана заметка о `losses_period` для `InventoryAnalytics`, т.к. поле не существует в бэкенд-контракте
- **B-3:** §6.7 EP-19 `loss_trend_30d` — убрана пометка «не реализовано в бэкенд-схеме»: поле РЕАЛИЗОВАНО (`LossTrendPoint` в `dashboard_schemas.py`, тип `list[LossTrendPoint]` с `date` и `quantity`)
- **B-4:** §8.1 — исправлена строка аналитических графиков: убран EP-17 (он polling 60s, не кэш 15 мин)
- **B-5:** Фазирование — все фазы теперь разблокированы (все EP реализованы), кроме EP-6 (Phase 3+)
- Итого: 5 исправлений синхронизации с бэкендом

**Changelog v1.2 (final review → production):**

- **R-1:** §5.3 EP-19 — убран `StorekeeperDashboard` из страницы (BR-18 = только Админ, согласовано с §4.3)
- **R-2:** `cancelled_today` из EP-1 — отображается как подтекст «Отменено: N» под StatCard «Доставлено»
- **R-3:** EP-17 агрегаты `total_active`, `total_stock_on_couriers`, `total_courier_cash` — summary-строка над CourierFleetGrid
- Финальная сверка: 20/20 BR ✅, 21/21 EP ✅, ролевой доступ ✅, фазы ✅, все v1.1 fixes ✅
- Статус изменён на **Production**

**Changelog v1.1 (review):**

- **C-1:** EP-13 — добавлен `losses_period` и `date_from/date_to` query params (BRD v1.2 BR-10)
- **C-2/C-3:** AccountantDashboard разделён на Фазу 1 (KPI + PENDING + курьеры) и Фазу 2 (+ RevenueTrend + TopDebtors)
- **C-4:** `VirtualAccountsPanel` убран из StorekeeperDashboard — BR-18 доступен только Админу (BRD §5)
- **M-1..M-7:** Добавлены спецификации 7 недостающих компонентов: ContainerDebtorsTable, TopClientsTable, MovementStatsChart, InventoryTrendChart, CourierLoadChart, SegmentRevenueChart, OrderFunnelChart
- **M-8:** `by_sale_type` из EP-1 отображается под StatCard «Всего сегодня»
- **M-9:** Добавлена заметка о `loss_trend_30d` (в PRD, но не в бэкенд-схеме)
- **M-10:** Добавлена настройка `ConfigProvider locale={ruRU}` для русской локализации Ant Design
- **m-1:** Исправлена ссылка EP-6 → EP-8 в таблице polling (§8.1)
- **m-2:** Добавлена утилита `pluralize()` для русских окончаний
- **m-3:** Исправлен `formatMoney()` — regex применяется только к целой части
- **m-4:** Добавлен `formatDateTime` в структуру каталогов
- **m-5:** Добавлена заметка о Dark Mode (отложен до post-MVP)
- **m-6:** Документированы exact drill-down URL params для ActionItemsList
- **m-7:** Кассир ограничен inventory summary на домашнем экране, без доступа к InventoryAnalytics
- Итого: **21 исправление** (4 CRITICAL, 10 MAJOR, 7 MINOR)

---

## 1. Назначение документа

Настоящий BRD определяет требования к фронтенд-реализации Dashboard-экранов админ-панели MunavvarA. Документ является мостом между Backend PRD (21 API-эндпоинт) и конечной реализацией на React. Описывает: страницы, компоненты, маппинг API -> UI, форматирование данных, ролевой доступ, стратегию кэширования и фазирование.

---

## 2. Технологический стек

| Технология                 | Версия  | Назначение                              |
| -------------------------- | ------- | --------------------------------------- |
| React                      | 19.2.0  | UI-библиотека                           |
| Redux Toolkit + RTK Query  | 2.11.2  | State management + серверный кэш        |
| React Router DOM           | ^7.13.0 | Клиентский роутинг                      |
| Ant Design                 | v6      | UI-фреймворк (60+ компонентов)          |
| @ant-design/pro-components | latest  | ProTable, ProForm, ProLayout, ProCard   |
| @ant-design/icons          | latest  | Иконки                                  |
| Recharts                   | latest  | Графики (Line, Bar, Area, Pie, Heatmap) |
| Vite                       | 7.3.1   | Сборка + HMR                            |
| ESLint                     | 9.39.1  | Линтер                                  |
| Vercel                     | —       | Деплой (SPA с rewrites)                 |

**Шрифт:** Inter (Google Fonts) с `font-variant-numeric: tabular-nums` для финансовых данных.

**Локализация Ant Design:** `import ruRU from 'antd/locale/ru_RU'` → `<ConfigProvider locale={ruRU}>` — русские строки для DatePicker, Pagination, Empty, Table, Modal и др.

---

## 3. Архитектура фронтенда

### 3.1 Структура каталогов

```
frontend/src/
├── app/
│   ├── store.js                    # Redux store + RTK Query middleware
│   └── routes.jsx                  # React Router конфигурация
│
├── services/
│   ├── baseApi.js                  # RTK Query createApi, baseQuery с JWT
│   ├── dashboardOrdersApi.js       # EP-1..EP-7 (orders dashboard)
│   ├── dashboardFinancesApi.js     # EP-8..EP-12, EP-21 (finances dashboard)
│   ├── dashboardInventoryApi.js    # EP-13..EP-16, EP-18, EP-19 (inventory dashboard)
│   └── dashboardCouriersApi.js     # EP-17, EP-20 (courier fleet)
│
├── pages/
│   ├── dashboard/
│   │   ├── AdminDashboard.jsx      # Домашний экран администратора
│   │   ├── AccountantDashboard.jsx # Домашний экран бухгалтера
│   │   ├── StorekeeperDashboard.jsx# Домашний экран кладовщика
│   │   ├── CashierDashboard.jsx    # Домашний экран кассира
│   │   ├── OrdersAnalytics.jsx     # Аналитика заказов (Фаза 3)
│   │   ├── FinanceAnalytics.jsx    # Финансовая аналитика (Фаза 2)
│   │   ├── InventoryAnalytics.jsx  # Складская аналитика (Фаза 3)
│   │   └── CourierAnalytics.jsx    # Аналитика курьеров (Фаза 3)
│   └── ...
│
├── components/
│   ├── dashboard/
│   │   ├── StatCard.jsx            # KPI-карточка (число + тренд + sparkline)
│   │   ├── TrendIndicator.jsx      # Стрелка вверх/вниз + процент
│   │   ├── PeriodFilter.jsx        # Фильтр периода (date_from, date_to, пресеты)
│   │   ├── GranularitySelector.jsx # Переключатель day/week/month
│   │   ├── ActionItemsList.jsx     # Блок «Требуют внимания»
│   │   ├── OrderStatusCounters.jsx # Счётчики по статусам заказов
│   │   ├── CourierFleetGrid.jsx    # Сетка карточек курьеров
│   │   ├── CourierCard.jsx         # Карточка одного курьера
│   │   ├── ContainerDonut.jsx      # Donut-chart распределения тары
│   │   ├── DebtAgingChart.jsx      # Stacked bar aging-бакетов
│   │   ├── RevenueTrendChart.jsx   # Line chart выручки
│   │   ├── OrderHeatmap.jsx        # Heatmap заказов (день x час)
│   │   ├── OrderFunnelChart.jsx    # Horizontal bar воронки статусов
│   │   ├── TopDebtorsTable.jsx     # Таблица топ-должников
│   │   ├── TopClientsTable.jsx     # Таблица топ-клиентов
│   │   ├── ContainerDebtorsTable.jsx # Таблица должников по таре
│   │   ├── MovementStatsChart.jsx  # Bar chart перемещений по типам
│   │   ├── InventoryTrendChart.jsx # Line chart трендов остатков
│   │   ├── VirtualAccountsPanel.jsx# Виртуальные счета + integrity
│   │   ├── IntegrityAlert.jsx      # Критический алерт целостности
│   │   ├── PaymentBreakdownChart.jsx # Pie/Donut способов оплаты
│   │   ├── SegmentRevenueChart.jsx # Bar chart B2B vs B2C
│   │   ├── CourierLoadChart.jsx    # Stacked bar загрузки курьеров
│   │   └── FinanceKPICards.jsx     # Группа KPI-карточек финансов
│   └── common/
│       ├── MoneyCell.jsx           # Форматирование денежных сумм
│       ├── PhoneCell.jsx           # Форматирование телефонов
│       ├── StatusTag.jsx           # Tag со статусом заказа/транзакции
│       ├── FreshnessIndicator.jsx  # Индикатор свежести данных
│       ├── EmptyState.jsx          # Пустое состояние с иллюстрацией
│       └── ErrorBoundary.jsx       # Обработка ошибок компонентов
│
├── hooks/
│   ├── useCurrentRole.js           # Текущая роль пользователя
│   ├── usePeriodFilter.js          # Состояние фильтра периода
│   └── usePollingInterval.js       # Динамический polling interval
│
├── utils/
│   ├── formatMoney.js              # Тийины -> "1 234 567 сум"
│   ├── formatPhone.js              # "998901234567" -> "+998 90 123-45-67"
│   ├── formatDate.js               # ISO 8601 -> "ДД.ММ.ГГГГ", formatDateTime()
│   ├── formatPercent.js            # 0.125 -> "+12.5%"
│   ├── pluralize.js                # Русские окончания: pluralize(5, 'заказ', 'заказа', 'заказов')
│   └── constants.js                # Маппинги статусов, цветов, порядок FSM
│
└── theme/
    ├── antdTheme.js                # Ant Design ConfigProvider token overrides
    └── chartTheme.js               # Recharts цветовая палитра
```

### 3.2 Паттерн RTK Query API Slice

Каждый dashboard-домен — отдельный API slice, инжектируемый в `baseApi`:

```javascript
// services/dashboardOrdersApi.js
import { baseApi } from "./baseApi";

export const dashboardOrdersApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getOrdersSummary: builder.query({
      query: () => "/backoffice/dashboard/orders/summary",
      // polling каждые 60 сек (NFR-3)
    }),
    getOrderTrends: builder.query({
      query: ({ dateFrom, dateTo, granularity, saleType, clientType }) => ({
        url: "/backoffice/dashboard/orders/trends",
        params: {
          date_from: dateFrom,
          date_to: dateTo,
          granularity,
          sale_type: saleType,
          client_type: clientType,
        },
      }),
      keepUnusedDataFor: 900, // кэш 15 мин (аналитика)
    }),
    // ...остальные endpoints
  }),
});
```

### 3.3 Аутентификация

- JWT-токен хранится в Redux state (или `localStorage` с fallback)
- `baseQuery` автоматически добавляет `Authorization: Bearer <token>` ко всем запросам
- При 401 — редирект на `/login`
- Роль пользователя извлекается из JWT payload (`role` claim)

---

## 4. Ролевые домашние экраны

После входа каждая роль попадает на **свой** домашний экран. Навигация фильтруется по роли — пользователь видит только доступные разделы.

### 4.1 Администратор — «Центр управления операциями»

**URL:** `/dashboard`
**Scope:** `orders:read` + `inventory:read` + `finances:read` + `users:read`

| Зона           | Компонент                 | API-источник                                                            | Данные                                                   |
| -------------- | ------------------------- | ----------------------------------------------------------------------- | -------------------------------------------------------- |
| KPI-карточки   | `StatCard` x 5            | EP-1 (`/orders/summary`)                                                | Новые, В пути, Доставлено, Выручка сегодня, Курьеры      |
| Разбивка дня   | Подтекст под «Всего»      | EP-1 (`by_sale_type`)                                                   | «Доставка: N / Самовывоз: M» под карточкой `total_today` |
| Отмены         | Подтекст под «Доставлено» | EP-1 (`cancelled_today`)                                                | «Отменено: N» красным под карточкой `delivered_today`    |
| Action Items   | `ActionItemsList`         | EP-1 + `GET /finances/dashboard` (сущ.)                                 | Незназначенные заказы, ожидающие подтверждения, алерты   |
| Статусы        | `OrderStatusCounters`     | EP-1 (`active_by_status`)                                               | 4 счётчика незавершённых статусов                        |
| Курьеры сводка | `<Statistic>` x 3         | EP-17 (`total_active`, `total_stock_on_couriers`, `total_courier_cash`) | Активных: N, Товара на курьерах: N ед., Наличных: X сум  |
| Курьеры        | `CourierFleetGrid`        | EP-17 (`/couriers/fleet`)                                               | Карточки курьеров с остатками и прогрессом               |
| Тара           | `ContainerDonut`          | EP-14 (`/inventory/container-distribution`)                             | Распределение тары по местоположению                     |
| Целостность    | `IntegrityAlert`          | EP-19 (`/inventory/virtual-accounts`)                                   | Показывается только если `integrity_ok === false`        |
| Виртуальные    | `VirtualAccountsPanel`    | EP-19 (`/inventory/virtual-accounts`)                                   | Баланс VIRTUAL_VENDOR/VIRTUAL_LOSS + целостность         |

**Polling:** EP-1, EP-17 — каждые 60 сек. EP-14, EP-19 — при загрузке страницы, кэш 15 мин.

**Drill-down URL params:**

| KPI / Action Item                     | URL при клике                                          |
| ------------------------------------- | ------------------------------------------------------ |
| Новые заказы (StatCard)               | `/orders?status=new`                                   |
| Незназначенные заказы (ActionItems)   | `/orders?status=new&sale_type=delivery&assigned=false` |
| Доставлено сегодня (StatCard)         | `/orders?status=delivered,pickup_completed&date=today` |
| Ожидающие подтверждения (ActionItems) | `/finances/transactions?status=pending`                |
| Активные курьеры (StatCard)           | `/couriers?active=true`                                |

### 4.2 Бухгалтер — «Финансовый центр»

**URL:** `/dashboard`
**Scope:** `finances:read` + `users:read`

**Фаза 1 (MVP):**

| Зона         | Компонент                  | API-источник                                                  | Данные                                                |
| ------------ | -------------------------- | ------------------------------------------------------------- | ----------------------------------------------------- |
| KPI-карточки | `FinanceKPICards`          | Существующий `GET /finances/dashboard`                        | Выручка, Касса, Ожидают по карте, Долг, Наличные кур. |
| Действия     | Таблица PENDING-транзакций | Существующий CRUD `GET /finances/transactions?status=pending` | Ожидающие подтверждения                               |
| Курьеры      | Мини-таблица наличных      | EP-17 (`/couriers/fleet`)                                     | Курьер, наличные на руках, собрано сегодня            |

**Добавляется в Фазе 2** (EP-8, EP-10 реализованы на бэкенде):

| Зона     | Компонент           | API-источник                     | Данные                              |
| -------- | ------------------- | -------------------------------- | ----------------------------------- |
| Должники | `TopDebtorsTable`   | EP-10 (`/finances/top-debtors`)  | Топ-10 должников с суммами и датами |
| Выручка  | `RevenueTrendChart` | EP-8 (`/finances/revenue-trend`) | Линейный график выручки за 30 дней  |

**Polling:** PENDING-транзакции — каждые 30 сек. EP-17 — каждые 60 сек. EP-8, EP-10 — при загрузке, кэш 15 мин.

**Inline-действия:** Кнопки [Подтвердить] / [Отклонить] прямо в таблице ожидающих транзакций. При отклонении — Popconfirm с обязательным полем «Причина».

### 4.3 Кладовщик — «Мой склад»

**URL:** `/dashboard`
**Scope:** `inventory:read`

| Зона         | Компонент        | API-источник                                | Данные                                               |
| ------------ | ---------------- | ------------------------------------------- | ---------------------------------------------------- |
| KPI-карточки | `StatCard` x 4   | EP-13 (`/inventory/summary`)                | Вода, Тара, Оборудование, Потери сегодня             |
| Тара         | `ContainerDonut` | EP-14 (`/inventory/container-distribution`) | Глобальные данные (EP-14 НЕ фильтрует по кладовщику) |

> **Примечание:** `VirtualAccountsPanel` (EP-19, BR-18) **не отображается** на экране кладовщика — по BRD §5 BR-18 доступен только Админу.

**Изоляция данных:** EP-13 автоматически фильтрует остатки по складам кладовщика (`warehouse_owner_id`). EP-14 возвращает **глобальные** данные без фильтрации — кладовщик видит распределение тары по всей системе. Фронтенд не передаёт дополнительных параметров — бэкенд определяет пользователя по JWT. Подробнее см. Приложение Б, §Б.6.

**Polling:** EP-13 — каждые 60 сек. EP-14 — при загрузке, кэш 15 мин.

> **EP-13:** Эндпоинт НЕ принимает query params. Возвращает `losses_today` (потери за сегодня) автоматически. Поле `losses_period` отсутствует в бэкенд-контракте.

### 4.4 Кассир — «Касса»

**URL:** `/dashboard`
**Scope:** `orders:read` + `inventory:read` + `finances:read`

| Зона         | Компонент      | API-источник                 | Данные                               |
| ------------ | -------------- | ---------------------------- | ------------------------------------ |
| KPI-карточки | `StatCard` x 3 | EP-1 (`/orders/summary`)     | Заказов сегодня, Доставлено, Выручка |
| Остатки      | Мини-таблица   | EP-13 (`/inventory/summary`) | Остатки воды/тары на складах         |

**Примечание:** Основной рабочий экран кассира — POS-интерфейс продаж (отдельный от dashboard scope). Dashboard-карточки — информационное дополнение. Кассир **не имеет доступа** к аналитическим страницам `/dashboard/inventory` и `/dashboard/couriers` — только к сводке на домашнем экране.

---

## 5. Маппинг API-эндпоинтов на UI-компоненты

### 5.1 Orders Dashboard (EP-1 .. EP-7)

| EP   | Эндпоинт                     | Компонент(ы)                                            | Страница                                 | Фаза |
| ---- | ---------------------------- | ------------------------------------------------------- | ---------------------------------------- | ---- |
| EP-1 | `/orders/summary`            | `StatCard` x5, `OrderStatusCounters`, `ActionItemsList` | AdminDashboard, CashierDashboard         | 1    |
| EP-2 | `/orders/trends`             | `RevenueTrendChart` (с переключателем granularity)      | OrdersAnalytics                          | 3    |
| EP-3 | `/orders/funnel`             | `OrderFunnelChart`                                      | OrdersAnalytics                          | 3    |
| EP-4 | `/orders/heatmap`            | `OrderHeatmap`                                          | OrdersAnalytics                          | 3    |
| EP-5 | `/orders/payment-breakdown`  | `PaymentBreakdownChart`                                 | AdminDashboard (Фаза 2), OrdersAnalytics | 2    |
| EP-6 | `/orders/partial-deliveries` | Отложен (требует schema change)                         | —                                        | 3+   |
| EP-7 | `/orders/top-clients`        | `TopClientsTable`                                       | OrdersAnalytics                          | 3    |

### 5.2 Finance Dashboard (EP-8 .. EP-12, EP-21)

| EP    | Эндпоинт                       | Компонент(ы)            | Страница                              | Фаза |
| ----- | ------------------------------ | ----------------------- | ------------------------------------- | ---- |
| EP-8  | `/finances/revenue-trend`      | `RevenueTrendChart`     | AccountantDashboard, FinanceAnalytics | 2    |
| EP-9  | `/finances/debt-aging`         | `DebtAgingChart`        | FinanceAnalytics                      | 2    |
| EP-10 | `/finances/top-debtors`        | `TopDebtorsTable`       | AccountantDashboard, FinanceAnalytics | 2    |
| EP-11 | `/finances/payment-methods`    | `PaymentBreakdownChart` | FinanceAnalytics                      | 3    |
| EP-12 | `/finances/summary-kpis`       | `FinanceKPICards`       | FinanceAnalytics                      | 2    |
| EP-21 | `/finances/revenue-by-segment` | `SegmentRevenueChart`   | FinanceAnalytics                      | 2    |

> **⚠ EP-5 vs EP-11 — структурная разница ответов:** Оба используют `PaymentBreakdownChart`, но API-контракты **различаются**:
>
> - **EP-5** (`PaymentBreakdownResponse`): имеет `methods[]` + `total_orders: int` + `total_amount: int` на верхнем уровне
> - **EP-11** (`PaymentMethodsFinanceResponse`): имеет **только** `methods[]` — без итогов на верхнем уровне
> - Также поля в `methods` именуются по-разному: EP-5 → `orders_count`, EP-11 → `transactions_count`
>
> Компонент `PaymentBreakdownChart` должен обрабатывать оба случая: при получении данных от EP-11 — вычислять итоги самостоятельно (`methods.reduce(...)`).

### 5.3 Inventory Dashboard (EP-13 .. EP-16, EP-18, EP-19)

| EP    | Эндпоинт                            | Компонент(ы)                                                                          | Страница                                                 | Фаза |
| ----- | ----------------------------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------------- | ---- |
| EP-13 | `/inventory/summary`                | `StatCard` x 4 (без query params — `losses_today` вычисляется бэкендом автоматически) | AdminDashboard, StorekeeperDashboard, InventoryAnalytics | 1    |
| EP-14 | `/inventory/container-distribution` | `ContainerDonut` + таблица                                                            | AdminDashboard, StorekeeperDashboard                     | 1    |
| EP-15 | `/inventory/container-debtors`      | `ContainerDebtorsTable`                                                               | InventoryAnalytics                                       | 3    |
| EP-16 | `/inventory/movement-stats`         | `MovementStatsChart`                                                                  | InventoryAnalytics                                       | 3    |
| EP-18 | `/inventory/trends`                 | `InventoryTrendChart`                                                                 | InventoryAnalytics                                       | 3    |
| EP-19 | `/inventory/virtual-accounts`       | `VirtualAccountsPanel`, `IntegrityAlert`                                              | AdminDashboard                                           | 1    |

### 5.4 Courier Fleet (EP-17, EP-20)

| EP    | Эндпоинт                 | Компонент(ы)                      | Страница                            | Фаза |
| ----- | ------------------------ | --------------------------------- | ----------------------------------- | ---- |
| EP-17 | `/couriers/fleet`        | `CourierFleetGrid`, `CourierCard` | AdminDashboard, AccountantDashboard | 1    |
| EP-20 | `/couriers/load-by-days` | `CourierLoadChart`                | CourierAnalytics                    | 3    |

---

## 6. Спецификации компонентов

### 6.1 StatCard — KPI-карточка

```
+------------------------------------------+
|  Общая выручка               за 30 дней  |
|                                          |
|  127 450 000 сум                         |
|  ▲ +12.5% vs пред. период               |
|  [~~~~~~~~sparkline~~~~~~~~]             |
+------------------------------------------+
```

**Props:**

| Prop        | Тип                 | Описание                                      |
| ----------- | ------------------- | --------------------------------------------- |
| `title`     | `string`            | Название метрики                              |
| `value`     | `number`            | Значение (тийины для денег, штуки для кол-ва) |
| `format`    | `'money'\|'number'` | Формат отображения                            |
| `trend`     | `number\|null`      | Процент изменения (0.125 = +12.5%)            |
| `sparkData` | `number[]`          | Массив значений для мини-графика (опц.)       |
| `loading`   | `boolean`           | Показать Skeleton                             |
| `onClick`   | `() => void`        | Drill-down при клике                          |
| `suffix`    | `string`            | Единица ("сум", "шт", "")                     |

**Реализация:** `Ant Design Statistic` + `ProCard` + мини-`<AreaChart>` из Recharts.

**Состояние загрузки:** `<Skeleton.Input active />` вместо спиннера (dashboard_ui.md §9.2).

### 6.2 OrderStatusCounters — Счётчики статусов

Горизонтальная полоса из 4 карточек для активных (незавершённых) заказов:

```
[Новые: 12] [Назначены: 8] [В пути: 5] [Прибыли: 2]
```

**Источник данных:** EP-1 `active_by_status` (массив `{status, count}`).

**Поведение:**

- Каждый счётчик — кликабельный, переход к отфильтрованному списку заказов
- Цветовая кодировка по статусу (см. раздел 7.2)
- Если массив не содержит статус — показать 0
- Пустые статусы (count=0) показываются серым

### 6.3 CourierCard — Карточка курьера

```
+------------------------------------------+
|  Иванов Пётр            🟢 Активен       |
|  Машина: 01 A 123 BC                     |
|                                          |
|  Заказы: 5 назначено / 3 доставлено      |
|  ██████████░░░░░░  60%                   |
|                                          |
|  Наличные: 450 000 сум                   |
|  Собрано: 350 000 сум                    |
|  Тара собрана: 12 шт                     |
|                                          |
|  Остаток в машине:                       |
|  Вода Hayot 19Л: 7 | Тара Hayot: 5       |
+------------------------------------------+
```

**Источник данных:** EP-17 `CourierFleetCard`.

**Props:**

| Prop      | Тип                | Описание                       |
| --------- | ------------------ | ------------------------------ |
| `courier` | `CourierFleetCard` | Объект карточки курьера из API |

**Поведение:**

- Статус-индикатор: зелёный кружок если `is_active === true`, серый если `false`
- Прогресс-бар: `delivered_today / assigned_today`
- `vehicle_balances` — компактная таблица остатков (скрыть если пустой массив)
- `cash_balance` — форматируется через `formatMoney()`
- Клик → переход к карточке курьера (`/couriers/:id`)

### 6.4 ContainerDonut — Распределение тары

**Тип визуализации:** Donut Chart (Recharts `<PieChart>` с `innerRadius`).

**Источник данных:** EP-14 `ContainerDistribution`.

**Сегменты:**

| Сегмент | Поле API        | Цвет      | Подпись     |
| ------- | --------------- | --------- | ----------- |
| Склады  | `at_warehouses` | `#1677FF` | На складах  |
| Курьеры | `at_couriers`   | `#FAAD14` | На курьерах |
| Клиенты | `at_clients`    | `#52C41A` | У клиентов  |
| Потери  | `lost`          | `#FF4D4F` | Потери      |

**Центр donut:** `total_in_system` — общее количество тары в системе.

**Дополнительно:** Таблица `per_product` (разбивка по типам бутылей) под графиком. Компактная таблица:

| Тара           | Склады | Курьеры | Клиенты | Потери | Всего |
| -------------- | ------ | ------- | ------- | ------ | ----- |
| Тара Hayot 19Л | 230    | 45      | 180     | 12     | 467   |
| Тара MunavvarA | 180    | 30      | 120     | 8      | 338   |

### 6.5 DebtAgingChart — Aging-бакеты дебиторки

**Тип визуализации:** Horizontal Stacked Bar Chart или сегментированная полоса.

**Источник данных:** EP-9 `DebtAgingResponse`.

**Бакеты:**

| Бакет          | Цвет      | Диапазон   |
| -------------- | --------- | ---------- |
| Текущий        | `#52C41A` | 0-7 дней   |
| Предупреждение | `#FAAD14` | 8-14 дней  |
| Просрочка      | `#FA8C16` | 15-30 дней |
| Критично       | `#FF4D4F` | 31-60 дней |
| Безнадёжный    | `#CF1322` | 60+ дней   |

**Отображение:** Каждый бакет — секция полосы, ширина пропорциональна `total_amount`. Под полосой — легенда с `clients_count` и `total_amount` на бакет.

**Итоги:** `total_debt` и `total_debtors` вверху как `<Statistic>`.

### 6.6 RevenueTrendChart — Динамика выручки

**Тип визуализации:** Line Chart (Recharts `<LineChart>` с `<Area>` fill).

**Источник данных:** EP-8 `RevenueTrendResponse` или EP-2 `OrderTrendResponse`.

**Управление:**

- `<GranularitySelector>` — переключатель day/week/month
- `<PeriodFilter>` — выбор периода (пресеты: 7д, 30д, 90д, 365д, произвольный)

**Данные графика:**

- X: `period` (дата)
- Y: `revenue` (форматируется в тысячах: "127.5K" или "1.3M")
- Tooltip: точные суммы в формате `formatMoney()`

**Метрики над графиком:**

- `total_revenue` — общая выручка за период
- `total_orders` — общее количество заказов
- `change_percent` — `<TrendIndicator>` (стрелка + процент)

### 6.7 VirtualAccountsPanel — Виртуальные счета

**Источник данных:** EP-19 `VirtualAccountsResponse`.

**Компоненты:**

1. **Integrity Alert** — если `integrity_ok === false`:

   ```
   ⛔ КРИТИЧЕСКАЯ ОШИБКА ЛЕДЖЕРА
   Расхождение: {integrity_diff} ед.
   Введено в систему: {vendor_total} | Списано: {loss_total} | На реальных точках: {real_total}
   Немедленно обратитесь к администратору.
   ```

   Компонент: `Ant Design Alert` type="error" с `showIcon`.

2. **Сводка** — три числа в `<Statistic>`:
   - Введено в систему (VIRTUAL_VENDOR): `vendor_total`
   - Списано (VIRTUAL_LOSS): `loss_total`
   - На реальных точках: `real_total`

3. **Таблица по продуктам** — `per_product`:
   | Продукт | Введено | Списано |
   | ------- | ------- | ------- |

4. **Тренд потерь** (sparkline) — поле `loss_trend_30d` (массив `LossTrendPoint` с полями `date: str`, `quantity: int` — потери по дням за 30 дней). **Реализовано** в бэкенде (`VirtualAccountsResponse.loss_trend_30d`). Отображать как мини-`<AreaChart>` рядом с `loss_total`. Если массив пуст — не показывать.

### 6.8 OrderHeatmap — Тепловая карта

**Тип визуализации:** Матрица 7x24 (дни недели x часы).

**Источник данных:** EP-4 `OrderHeatmapResponse`.

**Реализация:** Recharts не имеет нативного heatmap. Варианты:

1. **CSS Grid + цветовые ячейки** — простой и производительный подход
2. **Recharts ScatterChart** с кастомными ячейками

**Оси:**

- Y: Пн, Вт, Ср, Чт, Пт, Сб, Вс (из `day_of_week` 1-7, ISO 8601)
- X: 0:00, 1:00, ..., 23:00 (из `hour` 0-23, время Ташкента)

**Цветовая шкала:** Линейная интерполяция от белого (#FFFFFF) при count=0 до primary (#1677FF) при count=`max_count`.

**Tooltip:** При наведении — "Понедельник, 14:00 — 23 заказа". Использовать `pluralize(count, 'заказ', 'заказа', 'заказов')` для корректных русских окончаний.

### 6.9 TopDebtorsTable — Таблица должников

**Источник данных:** EP-10 `TopDebtorsResponse`.

**Колонки:**

| Колонка          | Поле API            | Формат                   | Выравн. |
| ---------------- | ------------------- | ------------------------ | ------- |
| #                | Порядковый номер    | 1, 2, 3...               | Центр   |
| Клиент           | `client_name`       | Текст                    | Лево    |
| Тип              | `client_type`       | `<StatusTag>` B2C/B2B    | Центр   |
| Телефон          | `phone`             | `formatPhone()` или "—"  | Лево    |
| Задолженность    | `debt_amount`       | `formatMoney()` красным  | Право   |
| Последний платёж | `last_payment_date` | `formatDate()` или "—"   | Центр   |
| Дней без оплаты  | `days_overdue`      | Число, красный если > 14 | Центр   |

> **⚠ Бэкенд-ограничение:** Поле `phone` **всегда возвращается как `null`** — бэкенд сознательно не загружает телефон, чтобы избежать N+1 запросов к таблице `user_identities`. Колонка «Телефон» будет показывать «—». Если телефон необходим — получать при переходе к карточке клиента.

**Действия:** Клик на строку → переход к карточке клиента (`/clients/:id`).

**Footer:** `total_debt` — общая сумма задолженности.

### 6.10 PeriodFilter — Фильтр периода

Общий компонент для всех аналитических экранов.

**Пресеты:**

| Кнопка     | `date_from`             | `date_to`   |
| ---------- | ----------------------- | ----------- |
| Сегодня    | `today`                 | `today`     |
| 7 дней     | `today - 6d`            | `today`     |
| 30 дней    | `today - 29d`           | `today`     |
| Этот месяц | Первый день тек. месяца | `today`     |
| 90 дней    | `today - 89d`           | `today`     |
| 365 дней   | `today - 364d`          | `today`     |
| Период     | RangePicker             | RangePicker |

**Компонент:** `Ant Design Radio.Group` для пресетов + `RangePicker` для произвольного периода.

**Состояние:** Хранится в URL query params (`?from=2026-03-01&to=2026-04-01`) для возможности поделиться ссылкой.

### 6.11 FreshnessIndicator — Индикатор свежести

Показывает timestamp последнего обновления данных (dashboard_ux.md §8.3).

```
Данные на 14:35:22  🟢
```

**Цвета:**

- `#52C41A` (зелёный) — данные < 1 мин
- `#FAAD14` (жёлтый) — данные 1-5 мин
- `#FF4D4F` (красный) — данные > 5 мин или потеря соединения

**Реализация:** `fulfilledTimeStamp` из RTK Query endpoint state → вычисление разницы с `Date.now()`.

### 6.12 ContainerDebtorsTable — Должники по таре

**Источник данных:** EP-15 `ContainerDebtorsResponse`.

**Колонки:**

| Колонка         | Поле API            | Формат                 | Выравн. |
| --------------- | ------------------- | ---------------------- | ------- |
| #               | Порядковый номер    | 1, 2, 3...             | Центр   |
| Клиент          | `client_name`       | Текст                  | Лево    |
| Тип             | `client_type`       | `<StatusTag>` B2C/B2B  | Центр   |
| Тара на балансе | `container_balance` | Число, шт              | Право   |
| Последний заказ | `last_order_date`   | `formatDate()` или "—" | Центр   |

> **⚠ Бэкенд-ограничение:** Поле `days_since_last_order` **всегда возвращается как `null`** — бэкенд не вычисляет это значение. Колонку «Дней без заказа» **не отображать**. При необходимости фронтенд может вычислить: `Math.floor((Date.now() - new Date(last_order_date)) / 86400000)`.

**Footer:** `total_containers_at_clients` — общее количество тары у клиентов.

**Параметры:** `limit` (по умолчанию 10). Сортировка по `container_balance` DESC.

**Действия:** Клик на строку → `/clients/:id`.

### 6.13 TopClientsTable — Топ клиентов

**Источник данных:** EP-7 `TopClientsResponse`.

**Колонки:**

| Колонка | Поле API         | Формат                | Выравн. |
| ------- | ---------------- | --------------------- | ------- |
| #       | Порядковый номер | 1, 2, 3...            | Центр   |
| Клиент  | `client_name`    | Текст                 | Лево    |
| Тип     | `client_type`    | `<StatusTag>` B2C/B2B | Центр   |
| Заказов | `orders_count`   | Число                 | Право   |
| Сумма   | `total_amount`   | `formatMoney()`       | Право   |

**Управление:** Переключатель сортировки — `sort_by`: «По количеству» (`orders_count`) / «По сумме» (`total_amount`). Компонент: `Radio.Group` или `Segmented`.

**Параметры:** `limit` (по умолчанию 10), `date_from`, `date_to`, `sort_by`.

### 6.14 MovementStatsChart — Статистика перемещений

**Тип визуализации:** Horizontal Bar Chart (Recharts `<BarChart layout="vertical">`).

**Источник данных:** EP-16 `MovementStatsResponse`.

**Маппинг TransferType → русские подписи:**

| Enum value              | Подпись на графике      | Цвет      |
| ----------------------- | ----------------------- | --------- |
| `COURIER_LOAD`          | Загрузка курьера        | `#1677FF` |
| `COURIER_RETURN`        | Возврат курьера         | `#2F54EB` |
| `CLIENT_DELIVERY`       | Доставка клиенту        | `#52C41A` |
| `CLIENT_RETURN`         | Возврат тары от клиента | `#13C2C2` |
| `WAREHOUSE_SALE`        | Продажа со склада       | `#722ED1` |
| `WAREHOUSE_TARA_RETURN` | Возврат тары на склад   | `#9254DE` |
| `LOSS_WRITE_OFF`        | Списание                | `#FF4D4F` |
| `INVENTORY_FINDING`     | Находка                 | `#FAAD14` |
| `INITIAL_BALANCE`       | Начальный остаток       | `#8C8C8C` |

**Данные:** Две метрики на тип — `transfers_count` (количество перемещений) и `total_items` (единиц товара). Переключатель: показывать по количеству перемещений или по объёму товара.

**Footer:** `total_transfers`, `total_items`.

### 6.15 InventoryTrendChart — Тренды остатков

**Тип визуализации:** Multi-line Chart (Recharts `<LineChart>` с 3 линиями).

**Источник данных:** EP-18 `InventoryTrendResponse`.

**Серии:**

| Серия           | Поле API                | Цвет      | Подпись               |
| --------------- | ----------------------- | --------- | --------------------- |
| Вода на складах | `water_stock`           | `#1677FF` | Вода (склады+курьеры) |
| Тара на складах | `container_stock`       | `#FAAD14` | Тара (склады+курьеры) |
| Тара у клиентов | `containers_at_clients` | `#52C41A` | Тара у клиентов       |

**Управление:**

- `<PeriodFilter>` — пресеты 7д / 30д
- `product_type` filter (water / container / all) — `<Segmented>`

> **⚠ Дефолт API — 7 дней:** EP-18 — **единственный** эндпоинт, где `date_from` по умолчанию = `today - 7 дней` (не 30, как все остальные). Если пользователь выбирает 30д, фронтенд **обязан** отправить `date_from`/`date_to` явно. Без параметров API вернёт только 7 точек.

**Оси:** X = `date` (formatDate), Y = количество (единицы).

> **Сложность (PRD §EP-18):** Бэкенд строит тренд как «текущий баланс минус будущие изменения». До 30 точек.

### 6.16 CourierLoadChart — Загрузка курьеров по дням

**Тип визуализации:** Stacked Bar Chart или Grouped Bar Chart (Recharts `<BarChart>`).

**Источник данных:** EP-20 `CourierLoadResponse`.

**Оси:** X = `date`, Y = `deliveries_count`. Каждый курьер — отдельный цвет в стеке.

**Целевая зона:** Горизонтальная полоса 15-25 заказов/день (dashboard_orders.md §2.1) — `<ReferenceLine>` или shaded area. Выше 25 = перегрузка (красный), ниже 15 = недозагрузка.

**Метрики над графиком:**

- `total_deliveries` — всего доставок
- `avg_per_courier` — среднее на курьера
- `max_load` — максимальная загрузка одного курьера за один день

### 6.17 SegmentRevenueChart — Выручка B2B vs B2C

**Тип визуализации:** Side-by-side Bar Chart или Donut с двумя сегментами.

**Источник данных:** EP-21 `RevenueBySegmentResponse`.

**Сегменты:**

| Сегмент | Enum value   | Цвет      | Подпись |
| ------- | ------------ | --------- | ------- |
| B2B     | `client_b2b` | `#722ED1` | Бизнес  |
| B2C     | `client_b2c` | `#1677FF` | Розница |

**Данные на сегмент:** `orders_count`, `total_revenue` (formatMoney), `avg_order_value` (formatMoney).

**Дополнительно:** Под графиком — две `<Statistic>` карточки: «Средний чек B2B: X сум» / «Средний чек B2C: Y сум».

**Footer:** `total_orders`, `total_revenue` по всем сегментам.

### 6.18 OrderFunnelChart — Воронка статусов

**Тип визуализации:** Horizontal Bar Chart (Recharts `<BarChart layout="vertical">`), **не** классическая воронка.

**Источник данных:** EP-3 `OrderFunnelResponse`.

> **⚠ Ограничение (BRD BR-3):** Это **распределение по текущему статусу**, а не истинная конверсионная воронка. Для настоящей воронки необходима таблица `order_status_history`, которой пока нет. Визуализация показывает, сколько заказов **сейчас находится** в каждом статусе за выбранный период.

**Интерпретация для бизнеса:**

- Много в `new` → проблема назначения курьеров
- Много в `assigned` → курьеры не выезжают
- Высокий % `cancelled` → проблема качества/доступности

**Порядок строк:** FSM-порядок (§7.5). Цвета — по маппингу статусов (§7.4).

**Данные на статус:** `count` (число) + `percentage` (formatPercent) справа от полосы.

**Footer:** `total` — всего заказов за период.

---

## 7. Форматирование данных

### 7.1 Граница ответственности API / Frontend

API возвращает **raw-данные**. Вся трансформация — на фронтенде (BRD §NFR-5, dashboard_ui.md §9.5).

### 7.2 Справочник форматов

| Тип данных            | API возвращает                | Фронтенд показывает                         | Утилита            |
| --------------------- | ----------------------------- | ------------------------------------------- | ------------------ |
| Денежные суммы        | `12345600` (тийины, BIGINT)   | `123 456 сум` (пробел-разделитель)          | `formatMoney()`    |
| Суммы в таблицах      | `12345600`                    | `123 456,00 сум` или `(123 456 сум)` расход | `formatMoney()`    |
| Телефоны              | `"998901234567"`              | `+998 90 123-45-67`                         | `formatPhone()`    |
| Даты                  | `"2026-04-01"` (ISO 8601)     | `01.04.2026` (ДД.ММ.ГГГГ)                   | `formatDate()`     |
| Дата-время            | `"2026-04-01T14:30:00+05:00"` | `01.04.2026 14:30`                          | `formatDateTime()` |
| Проценты              | `0.125` (float 0.0-1.0)       | `+12.5%` или `▲ 12.5%`                      | `formatPercent()`  |
| Тренд (рост)          | `0.125`                       | `▲ +12.5%` зелёным                          | `<TrendIndicator>` |
| Тренд (падение)       | `-0.083`                      | `▼ -8.3%` красным                           | `<TrendIndicator>` |
| Тренд (без изменений) | `0.0`                         | `— 0.0%` серым                              | `<TrendIndicator>` |
| Выручка (Revenue)     | Инвертируется API             | Всегда положительное число                  | `formatMoney()`    |
| Долг клиента          | Положительный баланс          | Красным как «задолженность»                 | `formatMoney()`    |

### 7.3 formatMoney()

```javascript
/**
 * Конвертирует тийины в форматированную строку.
 * @param {number} tiyins - Сумма в тийинах (1 сум = 100 тийин)
 * @param {object} options
 * @param {boolean} options.showDecimals - Показывать копейки (для таблиц)
 * @param {boolean} options.showCurrency - Добавлять "сум"
 * @returns {string} "123 456 сум" или "123 456,00 сум"
 */
export function formatMoney(
  tiyins,
  { showDecimals = false, showCurrency = true } = {},
) {
  const sums = tiyins / 100;
  if (showDecimals) {
    const [intPart, decPart] = sums.toFixed(2).split(".");
    const withSpaces = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    const result = `${withSpaces},${decPart}`;
    return showCurrency ? `${result} сум` : result;
  }
  const withSpaces = Math.round(sums)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return showCurrency ? `${withSpaces} сум` : withSpaces;
}
```

### 7.4 Цветовая кодировка статусов

**Статусы заказов:**

| Статус             | Enum value         | Цвет      | Ant Design preset |
| ------------------ | ------------------ | --------- | ----------------- |
| Новый              | `new`              | `#1677FF` | `processing`      |
| Назначен           | `assigned`         | `#2F54EB` | `geekblue`        |
| В пути             | `in_transit`       | `#FAAD14` | `warning`         |
| Прибыл             | `arrived`          | `#722ED1` | `purple`          |
| Доставлен          | `delivered`        | `#52C41A` | `success`         |
| Самовывоз завершён | `pickup_completed` | `#13C2C2` | `cyan`            |
| Отменён            | `cancelled`        | `#FF4D4F` | `error`           |

**Статусы транзакций:**

| Статус    | Enum value  | Цвет      | Ant Design preset |
| --------- | ----------- | --------- | ----------------- |
| Ожидание  | `pending`   | `#FAAD14` | `warning`         |
| Завершена | `completed` | `#52C41A` | `success`         |
| Отклонена | `rejected`  | `#FF4D4F` | `error`           |

**Типы клиентов:**

| Тип | Enum value   | Цвет      | Подпись |
| --- | ------------ | --------- | ------- |
| B2C | `client_b2c` | `#1677FF` | Розница |
| B2B | `client_b2b` | `#722ED1` | Бизнес  |

### 7.5 Порядок FSM для сортировки

```javascript
export const ORDER_STATUS_ORDER = [
  "new",
  "assigned",
  "in_transit",
  "arrived",
  "delivered",
  "pickup_completed",
  "cancelled",
];
```

Используется в EP-3 (воронка) и везде, где статусы должны быть упорядочены.

---

## 8. Стратегия обновления данных (RTK Query)

### 8.1 Частота обновления по типам данных

| Тип данных                                   | Механизм RTK Query  | Интервал  | Обоснование                                          |
| -------------------------------------------- | ------------------- | --------- | ---------------------------------------------------- |
| KPI-карточки (EP-1 summary, EP-13 summary)   | `pollingInterval`   | 60 000 мс | Операционный мониторинг, минутная задержка допустима |
| Ожидающие подтверждения (PENDING-транзакции) | `pollingInterval`   | 30 000 мс | Рабочая очередь бухгалтера, критичнее графиков       |
| Карточки курьеров (EP-17)                    | `pollingInterval`   | 60 000 мс | Оперативный мониторинг в течение дня                 |
| Аналитические графики (EP-2, EP-8, EP-18)    | `keepUnusedDataFor` | 900 сек   | Исторические данные, кэш 15 мин                      |
| Aging-бакеты (EP-9)                          | On-demand           | —         | Бакеты не меняются чаще раза в сутки                 |
| Таблицы с пагинацией (EP-7, EP-10, EP-15)    | On-demand           | —         | Загружаются при навигации/фильтрации                 |

### 8.2 Polling только на активной вкладке

```javascript
// Отключаем polling когда вкладка неактивна
const isVisible = useDocumentVisibility();

useGetOrdersSummaryQuery(undefined, {
  pollingInterval: isVisible ? 60_000 : 0,
});
```

### 8.3 Инвалидация кэша

При выполнении мутации (подтверждение платежа, создание заказа и т.д.) — инвалидировать связанные dashboard-эндпоинты через RTK Query `invalidatesTags`.

Пример: после `confirmTransaction` инвалидировать `['FinanceDashboard', 'PendingTransactions']`.

---

## 9. Навигация и роутинг

### 9.1 Структура маршрутов

```
/login                           — Вход в систему
/dashboard                       — Ролевой домашний экран (см. §4)
/dashboard/orders                — Аналитика заказов (Фаза 3)
/dashboard/finances              — Финансовая аналитика (Фаза 2)
/dashboard/inventory             — Складская аналитика (Фаза 3)
/dashboard/couriers              — Аналитика курьеров (Фаза 3)
/orders                          — Список заказов (CRUD)
/orders/:id                      — Детали заказа
/clients                         — Список клиентов
/clients/:id                     — Карточка клиента
/couriers                        — Список курьеров
/couriers/:id                    — Карточка курьера
/inventory                       — Склады и остатки
/inventory/movements             — Журнал перемещений
/finances                        — Финансы (счета, транзакции)
/finances/accounts/:id           — Выписка по счёту
/catalog                         — Каталог товаров
/staff                           — Управление персоналом
/settings                        — Настройки
```

### 9.2 Фильтрация навигации по ролям

| Раздел навигации    | Админ | Бухгалтер  | Кладовщик  | Кассир     |
| ------------------- | ----- | ---------- | ---------- | ---------- |
| Главная (дашборд)   | +     | +          | +          | +          |
| Заказы              | +     | —          | —          | +          |
| Клиенты             | +     | + (чтение) | —          | —          |
| Курьеры             | +     | + (сводка) | —          | —          |
| Склад               | +     | —          | + (свой)   | + (чтение) |
| Финансы             | +     | +          | —          | + (касса)  |
| Каталог             | +     | + (чтение) | + (чтение) | + (чтение) |
| Персонал            | +     | + (чтение) | —          | —          |
| Настройки           | +     | —          | —          | —          |
| Аналитика заказов   | +     | —          | —          | +          |
| Финанс. аналитика   | +     | +          | —          | +          |
| Складская аналитика | +     | —          | +          | —          |
| Аналитика курьеров  | +     | +          | —          | —          |

**Реализация:** `ProLayout` с `menuDataRender` — фильтрация `routes` по ролевому конфигу.

### 9.3 Sidebar — Структура меню

```
🏠 Главная
📦 Заказы
   ├─ Все заказы
   └─ 📊 Аналитика          (Фаза 3)
👥 Клиенты
🚗 Курьеры
   ├─ Все курьеры
   ├─ Транспорт
   └─ 📊 Аналитика          (Фаза 3)
🏭 Склад
   ├─ Склады и остатки
   ├─ Перемещения
   └─ 📊 Аналитика          (Фаза 3)
💰 Финансы
   ├─ Дашборд                (сущ. /finances/dashboard)
   ├─ Счета
   ├─ Транзакции
   ├─ Должники
   └─ 📊 Аналитика          (Фаза 2)
📋 Каталог
⚙ Персонал
```

**Badge на пункте «Финансы»:** Количество ожидающих подтверждения транзакций (`pending_transactions_count` из существующего `GET /finances/dashboard`).

---

## 10. Макет и визуальный дизайн

### 10.1 Общая структура

```
+---------------------------------------------------+
|                    HEADER (64px)                    |
|  [Logo] [Breadcrumb]    [FreshnessIndicator] [Bell] [User]|
+--------+------------------------------------------+
|        |                                          |
| SIDEBAR|              CONTENT AREA                |
| (256px)|                                          |
| dark   |  +------+ +------+ +------+ +------+     |
| #001529|  |StatC1| |StatC2| |StatC3| |StatC4|     |
|        |  +------+ +------+ +------+ +------+     |
|        |                                          |
|        |  +-----------------+ +----------------+  |
|        |  | Chart / Grid    | | Chart / Table  |  |
|        |  +-----------------+ +----------------+  |
|        |                                          |
|        |  +------------------------------------+  |
|        |  |        Detail Table / List          |  |
|        |  +------------------------------------+  |
+--------+------------------------------------------+
```

### 10.2 Цветовая схема (Light Mode — основной)

| Элемент            | Hex       |
| ------------------ | --------- |
| Primary            | `#1677FF` |
| Page Background    | `#F5F7FA` |
| Card Surface       | `#FFFFFF` |
| Sidebar Background | `#001529` |
| Sidebar Text       | `#FFFFFF` |
| Primary Text       | `#1F1F1F` |
| Secondary Text     | `#8C8C8C` |
| Border             | `#F0F0F0` |
| Success            | `#52C41A` |
| Error              | `#FF4D4F` |
| Warning            | `#FAAD14` |
| Info               | `#1677FF` |
| Purple (прибыл)    | `#722ED1` |

> **Dark Mode** — опциональный, реализуется через `<ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>`. Отложен до post-MVP. Основной режим — Light Mode (dashboard_ui.md §5: 55% пользователей финансовых приложений предпочитают Light Mode; пользователи MunavvarA работают в офисе днём).

### 10.3 Типографика

| Уровень         | Размер  | Начертание | Применение                           |
| --------------- | ------- | ---------- | ------------------------------------ |
| H1              | 24px    | SemiBold   | Заголовок страницы                   |
| H2              | 20px    | SemiBold   | Заголовок секции                     |
| H3              | 16px    | Medium     | Заголовок карточки                   |
| Body            | 14px    | Regular    | Текст в таблицах, формах             |
| Small           | 12px    | Regular    | Подписи, даты, ID                    |
| KPI-число       | 30-36px | SemiBold   | Главная метрика на StatCard          |
| KPI-изменение   | 14px    | Medium     | Процент рядом с метрикой             |
| Суммы в таблице | 14px    | Medium     | `font-variant-numeric: tabular-nums` |

### 10.4 Адаптивная сетка KPI-карточек

```
Desktop (xl+):   4 колонки  → <Col xs={24} sm={12} lg={6}>
Tablet (md-lg):  2 колонки  → <Col xs={24} sm={12} lg={6}>
Mobile (xs-sm):  1 колонка  → <Col xs={24} sm={12} lg={6}>
```

---

## 11. Состояния компонентов

### 11.1 Загрузка (Loading)

- **Карточки StatCard:** `<Skeleton.Input active style={{ width: '100%' }} />` внутри ProCard
- **Графики:** `<Skeleton active paragraph={{ rows: 6 }} />` в контейнере графика
- **Таблицы:** ProTable нативный `loading={true}` (встроенный skeleton)
- **Навигация между страницами:** NProgress-бар в header

### 11.2 Пустое состояние (Empty)

- `<Empty description="Нет заказов за выбранный период" />` с контекстным сообщением
- CTA-кнопка: «Создать заказ» / «Изменить период»
- Разные иллюстрации для разных разделов

### 11.3 Ошибка (Error)

- **Полноэкранная:** `<Result status="500" title="Не удалось загрузить данные" />` с кнопкой «Повторить»
- **Секционная:** `<Alert type="error" message="..." />` в рамках одного виджета, остальные работают
- **Действие:** `message.error('Не удалось подтвердить платёж')` (toast)

### 11.4 Потеря соединения

- `FreshnessIndicator` переходит в красный
- `<Alert type="warning" banner message="Потеряно подключение к серверу. Данные могут быть устаревшими." />`
- Polling продолжает попытки, но визуально показано, что данные stale

---

## 12. Доступность (Accessibility)

- Все интерактивные элементы доступны с клавиатуры (Tab/Enter/Escape)
- Контраст текста >= 4.5:1 (WCAG AA) — обеспечивается палитрой Ant Design
- ARIA-labels для графиков: `<AreaChart aria-label="Динамика выручки за 30 дней">`
- Таблицы: нативные `<table>` через ProTable, корректная семантика
- Цветовая информация дублируется текстом/иконкой (для дальтоников): стрелка ▲/▼ + цвет

---

## 13. Фазирование реализации

Фронтенд-фазы синхронизированы с бэкенд-фазами (PRD §7).

> **Статус бэкенда (v1.3):** Все 20 endpoint-ов (EP-1..EP-5, EP-7..EP-21) **реализованы** и готовы к интеграции. Фронтенд-фазирование определяется только приоритетом UI-разработки, не бэкенд-зависимостями. EP-6 (частичные доставки) — единственный отложенный EP, требует schema change.

### Фаза 1: MVP (P0)

**Цель:** Домашние экраны 4 ролей с оперативными данными.

| Задача                                          | Компоненты                                                                    | API                           |
| ----------------------------------------------- | ----------------------------------------------------------------------------- | ----------------------------- |
| Базовый каркас: ProLayout + роутинг + auth      | ProLayout, sidebar, header, login                                             | Auth CRUD                     |
| RTK Query setup + baseApi                       | baseApi.js, store.js                                                          | —                             |
| AdminDashboard — KPI + статусы                  | StatCard x5, OrderStatusCounters, ActionItemsList                             | EP-1                          |
| AdminDashboard — курьеры                        | CourierFleetGrid, CourierCard                                                 | EP-17                         |
| AdminDashboard — тара                           | ContainerDonut + таблица per_product                                          | EP-14                         |
| AdminDashboard — целостность                    | VirtualAccountsPanel, IntegrityAlert                                          | EP-19                         |
| StorekeeperDashboard — остатки + тара           | StatCard x4, ContainerDonut                                                   | EP-13, EP-14                  |
| AccountantDashboard — KPI + PENDING + курьеры   | FinanceKPICards, PENDING-таблица, мини-курьеры                                | Сущ. finance dashboard, EP-17 |
| CashierDashboard — минимальная сводка           | StatCard x3                                                                   | EP-1, EP-13                   |
| Общие компоненты                                | MoneyCell, PhoneCell, StatusTag, FreshnessIndicator, PeriodFilter, EmptyState | —                             |
| formatMoney, formatPhone, formatDate, constants | utils/                                                                        | —                             |
| Ant Design theme + Recharts theme               | theme/                                                                        | —                             |

**Критерий завершения:** 4 ролевых домашних экрана работают, данные обновляются, drill-down по KPI.

### Фаза 2: Финансовая аналитика (P1)

| Задача                                      | Компоненты                                    | API   |
| ------------------------------------------- | --------------------------------------------- | ----- |
| FinanceAnalytics страница                   | Страница с табами/секциями                    | —     |
| Динамика выручки                            | RevenueTrendChart + GranularitySelector       | EP-8  |
| Aging-бакеты                                | DebtAgingChart                                | EP-9  |
| Топ должников                               | TopDebtorsTable                               | EP-10 |
| Способы оплаты (orders view)                | PaymentBreakdownChart                         | EP-5  |
| Финансовые KPI                              | FinanceKPICards (расширенный)                 | EP-12 |
| Выручка B2B/B2C                             | SegmentRevenueChart                           | EP-21 |
| AccountantDashboard — добавить RevenueTrend | Интеграция EP-8 на домашний экран бухгалтера  | EP-8  |
| AccountantDashboard — добавить TopDebtors   | Интеграция EP-10 на домашний экран бухгалтера | EP-10 |

**Критерий завершения:** Бухгалтер видит полную финансовую аналитику. Aging-бакеты, динамика выручки, KPI. Домашний экран бухгалтера дополнен графиком выручки и таблицей должников.

### Фаза 3: Полная аналитика (P2)

| Задача                        | Компоненты                      | API   |
| ----------------------------- | ------------------------------- | ----- |
| OrdersAnalytics страница      | Страница с графиками заказов    | —     |
| Тренды заказов                | RevenueTrendChart (orders mode) | EP-2  |
| Воронка статусов              | OrderFunnelChart                | EP-3  |
| Тепловая карта                | OrderHeatmap                    | EP-4  |
| Топ клиентов                  | TopClientsTable                 | EP-7  |
| Способы оплаты (finance view) | PaymentBreakdownChart           | EP-11 |
| InventoryAnalytics страница   | Страница складской аналитики    | —     |
| Должники по таре              | ContainerDebtorsTable           | EP-15 |
| Статистика перемещений        | MovementStatsChart              | EP-16 |
| Тренды остатков               | InventoryTrendChart             | EP-18 |
| CourierAnalytics страница     | Страница аналитики курьеров     | —     |
| Загрузка курьеров по дням     | CourierLoadChart                | EP-20 |

### Фаза 3+: Отложено

| Задача                     | Зависимость                                         |
| -------------------------- | --------------------------------------------------- |
| Метрики частичных доставок | EP-6 — требует `is_partial_delivery` в модели Order |

---

## 14. Ролевой доступ к Dashboard-страницам

Фронтенд проверяет роль из JWT и скрывает/показывает маршруты и компоненты.

| Страница / маршрут        | Админ | Бухгалтер | Кладовщик | Кассир |
| ------------------------- | ----- | --------- | --------- | ------ |
| `/dashboard` (свой экран) | +     | +         | +         | +      |
| `/dashboard/orders`       | +     | —         | —         | +      |
| `/dashboard/finances`     | +     | +         | —         | +      |
| `/dashboard/inventory`    | +     | —         | +         | —      |
| `/dashboard/couriers`     | +     | +         | —         | —      |

> **Примечание:** Кассир видит inventory summary (`EP-13`) на своём домашнем экране, но **не имеет доступа** к полной складской аналитике (`/dashboard/inventory`). По BUSINESS.md §4, кассир работает на точке продаж и нуждается только в просмотре остатков для оформления продаж.

**Защита маршрутов:** React Router `loader` или wrapper-компонент `<RequireScope scope="orders:read">`. При отсутствии доступа — `<Result status="403" title="Нет доступа" />`.

---

## 15. Нефункциональные требования (фронтенд)

### NFR-F1: Производительность

- Первый контентный рендер (FCP) — < 1.5 сек
- Time to Interactive (TTI) — < 3 сек
- Все dashboard-данные рендерятся за < 500 мс после получения от API
- Ленивая загрузка (`React.lazy`) для аналитических страниц (Фаза 2-3)

### NFR-F2: Размер бандла

- Ant Design — tree-shaking через Vite
- Recharts — импорт конкретных компонентов (`import { LineChart } from 'recharts'`)
- Code splitting по маршрутам
- Целевой размер: < 300 KB gzip (без шрифтов)

### NFR-F3: Совместимость

- Chrome 90+ (основной браузер для админ-панели)
- Firefox 90+
- Safari 15+
- Edge 90+
- ES2020+ target (Vite config)

### NFR-F4: Локализация

- Язык интерфейса: **русский** (единственный рынок — Узбекистан, деловой язык — русский)
- Валюта: узбекский сум (UZS), хранится в тийинах
- Часовой пояс: `Asia/Tashkent` (UTC+5) — единственный
- Формат даты: ДД.ММ.ГГГГ
- Разделитель тысяч: пробел
- Десятичный разделитель: запятая
- Формат телефона: +998 XX XXX-XX-XX

### NFR-F5: Offline resilience

- При потере сети — показывать последние кэшированные данные с `<FreshnessIndicator>` в красном
- Не показывать пустые состояния при потере сети — только stale-индикатор
- RTK Query автоматически ретраит при восстановлении соединения

---

## 16. Зависимости и блокеры

| Зависимость                             | Статус                   | Блокирует                |
| --------------------------------------- | ------------------------ | ------------------------ |
| Backend EP-1 (orders summary)           | ✅ Реализован            | Фаза 1: AdminDashboard   |
| Backend EP-13 (inventory summary)       | ✅ Реализован            | Фаза 1: StorekeeperDash  |
| Backend EP-14 (container distribution)  | ✅ Реализован            | Фаза 1: ContainerDonut   |
| Backend EP-17 (courier fleet)           | ✅ Реализован            | Фаза 1: CourierFleetGrid |
| Backend EP-19 (virtual accounts)        | ✅ Реализован            | Фаза 1: VirtualAccounts  |
| Существующий `GET /finances/dashboard`  | ✅ Реализован            | Фаза 1: AccountantDash   |
| Backend EP-5 (payment breakdown)        | ✅ Реализован            | Фаза 2                   |
| Backend EP-8 (revenue trend)            | ✅ Реализован            | Фаза 2                   |
| Backend EP-9 (debt aging)               | ✅ Реализован            | Фаза 2                   |
| Backend EP-10 (top debtors)             | ✅ Реализован            | Фаза 2                   |
| Backend EP-12 (finance KPIs)            | ✅ Реализован            | Фаза 2                   |
| Backend EP-21 (revenue by segment)      | ✅ Реализован            | Фаза 2                   |
| Backend EP-2 (order trends)             | ✅ Реализован            | Фаза 3                   |
| Backend EP-3 (order funnel)             | ✅ Реализован            | Фаза 3                   |
| Backend EP-4 (order heatmap)            | ✅ Реализован            | Фаза 3                   |
| Backend EP-7 (top clients)              | ✅ Реализован            | Фаза 3                   |
| Backend EP-11 (payment methods finance) | ✅ Реализован            | Фаза 3                   |
| Backend EP-15 (container debtors)       | ✅ Реализован            | Фаза 3                   |
| Backend EP-16 (movement stats)          | ✅ Реализован            | Фаза 3                   |
| Backend EP-18 (inventory trends)        | ✅ Реализован            | Фаза 3                   |
| Backend EP-20 (courier load by days)    | ✅ Реализован            | Фаза 3                   |
| Backend EP-6 (partial deliveries)       | 🔴 Требует schema change | Фаза 3+                  |
| Frontend scaffolding (Vite, Ant Design) | ❌ Не создан             | Все фазы                 |

---

## 17. Связь с исследованиями

| Раздел документа          | Источник                                     |
| ------------------------- | -------------------------------------------- |
| §4 Ролевые экраны         | dashboard_ux.md §2 (ролевые UX-рекомендации) |
| §6 Компоненты             | dashboard_ui.md §8 (ключевые UI-компоненты)  |
| §7 Форматирование         | dashboard_ui.md §9.5 (граница API/Frontend)  |
| §7.4 Цвета статусов       | dashboard_ui.md §5 (цветовая палитра)        |
| §8 Стратегия обновления   | dashboard_ux.md §8 (стратегия обновлений)    |
| §9 Навигация              | dashboard_ux.md §3 (навигация и ИА)          |
| §10 Макет                 | dashboard_ui.md §6 (макет и сетка)           |
| §10.3 Типографика         | dashboard_ui.md §7 (типографика)             |
| §11 Состояния компонентов | dashboard_ui.md §9.2 (состояния компонентов) |
| §12 Доступность           | dashboard_ux.md §10 (accessibility)          |
| §13 Фазирование           | DASHBOARD_PRD.md §7 (фазирование бэкенда)    |
| §14 Ролевой доступ        | DASHBOARD_BRD.md §5 (ролевой доступ)         |

---

## 18. Глоссарий (фронтенд-специфичный)

| Термин               | Определение                                                    |
| -------------------- | -------------------------------------------------------------- |
| **StatCard**         | KPI-карточка с числом, трендом и мини-графиком                 |
| **Drill-down**       | Клик по агрегированному числу → переход к детальному списку    |
| **Polling**          | Периодический запрос к API для обновления данных               |
| **Stale**            | Данные, которые устарели (давно не обновлялись)                |
| **ProLayout**        | Компонент Ant Design ProComponents для макета админ-панели     |
| **ProTable**         | Расширенная таблица с пагинацией, фильтрацией, toolbar         |
| **RTK Query**        | Библиотека серверного кэша из Redux Toolkit                    |
| **baseApi**          | Центральный API slice RTK Query с JWT-interceptor              |
| **API Slice**        | Набор endpoint-ов RTK Query для одного домена                  |
| **Tag Invalidation** | Механизм RTK Query для сброса кэша при мутациях                |
| **FCP**              | First Contentful Paint — время первого рендера контента        |
| **TTI**              | Time to Interactive — время до полной интерактивности          |
| **Тийин**            | Минимальная денежная единица (1 сум = 100 тийин), BIGINT в API |

---

## Приложение А: Полный реестр фронтенд-компонентов Dashboard

| #   | Компонент               | Тип        | API-источник | Фаза | Описание                                 |
| --- | ----------------------- | ---------- | ------------ | ---- | ---------------------------------------- |
| 1   | `StatCard`              | Виджет     | Различные    | 1    | KPI-карточка (число + тренд + sparkline) |
| 2   | `TrendIndicator`        | Примитив   | —            | 1    | Стрелка + процент изменения              |
| 3   | `OrderStatusCounters`   | Виджет     | EP-1         | 1    | 4 счётчика статусов заказов              |
| 4   | `ActionItemsList`       | Виджет     | EP-1 + сущ.  | 1    | Блок «Требуют внимания»                  |
| 5   | `CourierFleetGrid`      | Контейнер  | EP-17        | 1    | Сетка карточек курьеров                  |
| 6   | `CourierCard`           | Виджет     | EP-17        | 1    | Карточка одного курьера                  |
| 7   | `ContainerDonut`        | График     | EP-14        | 1    | Donut распределения тары                 |
| 8   | `VirtualAccountsPanel`  | Виджет     | EP-19        | 1    | Виртуальные счета + сводка               |
| 9   | `IntegrityAlert`        | Алерт      | EP-19        | 1    | Критический алерт целостности леджера    |
| 10  | `FinanceKPICards`       | Контейнер  | Сущ. + EP-12 | 1/2  | Группа финансовых KPI-карточек           |
| 11  | `PeriodFilter`          | Управление | —            | 1    | Фильтр периода с пресетами               |
| 12  | `GranularitySelector`   | Управление | —            | 2    | Переключатель day/week/month             |
| 13  | `FreshnessIndicator`    | Примитив   | —            | 1    | Индикатор свежести данных                |
| 14  | `MoneyCell`             | Примитив   | —            | 1    | Ячейка с форматированной суммой          |
| 15  | `PhoneCell`             | Примитив   | —            | 1    | Ячейка с форматированным телефоном       |
| 16  | `StatusTag`             | Примитив   | —            | 1    | Tag со статусом (цветовой)               |
| 17  | `EmptyState`            | Примитив   | —            | 1    | Контекстное пустое состояние             |
| 18  | `ErrorBoundary`         | Примитив   | —            | 1    | Обработка ошибок компонентов             |
| 19  | `RevenueTrendChart`     | График     | EP-8 / EP-2  | 2    | Линейный график выручки                  |
| 20  | `DebtAgingChart`        | График     | EP-9         | 2    | Stacked bar aging-бакетов                |
| 21  | `TopDebtorsTable`       | Таблица    | EP-10        | 2    | Таблица топ-должников                    |
| 22  | `PaymentBreakdownChart` | График     | EP-5 / EP-11 | 2    | Pie/Donut способов оплаты                |
| 23  | `SegmentRevenueChart`   | График     | EP-21        | 2    | Bar chart B2B vs B2C                     |
| 24  | `OrderFunnelChart`      | График     | EP-3         | 3    | Horizontal bar воронки статусов          |
| 25  | `OrderHeatmap`          | График     | EP-4         | 3    | Матрица 7x24 (дни x часы)                |
| 26  | `TopClientsTable`       | Таблица    | EP-7         | 3    | Таблица топ-клиентов по заказам          |
| 27  | `ContainerDebtorsTable` | Таблица    | EP-15        | 3    | Таблица должников по таре                |
| 28  | `MovementStatsChart`    | График     | EP-16        | 3    | Bar chart перемещений по типам           |
| 29  | `InventoryTrendChart`   | График     | EP-18        | 3    | Line chart трендов остатков              |
| 30  | `CourierLoadChart`      | График     | EP-20        | 3    | Stacked bar загрузки курьеров            |

**Итого: 30 компонентов, 4 страницы аналитики, 4 ролевых дашборда, 3 фазы**

> **Примечание v1.1:** Все 30 компонентов из Приложения А теперь имеют полные спецификации в §6 (§6.1–§6.18). 7 компонентов Фазы 3 (ContainerDebtorsTable, TopClientsTable, MovementStatsChart, InventoryTrendChart, CourierLoadChart, SegmentRevenueChart, OrderFunnelChart) добавлены в §6.12–§6.18.

---

## Приложение Б: Полный реестр API-контрактов (v1.4)

> Этот раздел — **единственный источник истины** для фронтенд-интеграции. Все поля, типы и дефолты сверены с бэкенд-кодом (`src/modules/*/dashboard_schemas.py`, `src/api/v1/backoffice/dashboard/*.py`). Базовый путь: `/api/v1/backoffice/dashboard`.

### Б.1 Глобальные правила

**Дефолт `date_from`/`date_to`:** Если не передано — API использует `today - 30 дней .. today` для всех EP, **кроме EP-18** (по умолчанию `today - 7 дней`).

**Дефолт `limit`:** 10 (диапазон 1-100).

**Дефолт `granularity`:** `"day"` (допустимо: `day`, `week`, `month`).

**Дефолт `sort_by`:** `"total_amount"` (допустимо: `total_amount`, `orders_count`).

**Суммы:** Все денежные поля — `int` в тийинах (BIGINT). Деление на 100 → сум.

**Проценты:** `float` в диапазоне `0.0-1.0`. Умножение на 100 → проценты.

**Даты в ответах:** `str` в формате ISO 8601 (`"2026-04-01"`).

**Исключённые пользователи:** SYSTEM_USER (`00..0001`) и WALKIN_USER (`00..0002`) автоматически исключаются из EP-7, EP-9, EP-10, EP-12 (overdue), EP-15, EP-21.

### Б.2 Orders Domain

#### EP-1: `GET /orders/summary` — scope: `orders:read`, params: нет

```
OrdersSummary {
  active_by_status:  [{status: str, count: int}, ...]  // NEW, ASSIGNED, IN_TRANSIT, ARRIVED
  unassigned_orders: int         // NEW + DELIVERY + courier_id IS NULL
  total_today:       int
  delivered_today:   int         // DELIVERED + PICKUP_COMPLETED сегодня
  cancelled_today:   int
  revenue_today:     int         // тийины
  by_sale_type:      {delivery: int, warehouse_pickup: int}
  active_couriers:   int
}
```

#### EP-2: `GET /orders/trends` — scope: `orders:read`

Params: `date_from?`, `date_to?`, `granularity?` (day|week|month), `sale_type?` (delivery|warehouse_pickup), `client_type?` (client_b2c|client_b2b)

```
OrderTrendResponse {
  points: [{
    period:          str    // "2026-03-15" | "2026-W12" | "2026-03"
    orders_count:    int
    revenue:         int    // тийины
    avg_order_value: int    // тийины (revenue // orders_count)
  }, ...]
  total_orders:  int
  total_revenue: int
}
```

#### EP-3: `GET /orders/funnel` — scope: `orders:read`

Params: `date_from?`, `date_to?`

```
OrderFunnelResponse {
  total:    int
  statuses: [{
    status:     str     // FSM-порядок: new → assigned → in_transit → arrived → delivered → pickup_completed → cancelled
    count:      int
    percentage: float   // 0.0-1.0, round(count/total, 4)
  }, ...]
}
```

#### EP-4: `GET /orders/heatmap` — scope: `orders:read`

Params: `date_from?`, `date_to?`

```
OrderHeatmapResponse {
  cells: [{
    day_of_week: int   // 1=Пн..7=Вс (ISO 8601, ISODOW)
    hour:        int   // 0-23 (Asia/Tashkent)
    count:       int
  }, ...]
  max_count: int       // для нормализации цвета
}
```

#### EP-5: `GET /orders/payment-breakdown` — scope: `orders:read`

Params: `date_from?`, `date_to?`

```
PaymentBreakdownResponse {
  methods: [{
    method:       str   // "cash" | "card" | "contract"
    orders_count: int   // ⚠ НЕ transactions_count (ср. EP-11)
    total_amount: int   // тийины
  }, ...]
  total_orders: int     // ⚠ есть на верхнем уровне (ср. EP-11)
  total_amount: int     // ⚠ есть на верхнем уровне (ср. EP-11)
}
```

#### EP-7: `GET /orders/top-clients` — scope: `orders:read`

Params: `date_from?`, `date_to?`, `limit?` (1-100, default 10), `sort_by?` (total_amount|orders_count)

```
TopClientsResponse {
  clients: [{
    client_id:    UUID
    client_name:  str
    client_type:  str   // "client_b2c" | "client_b2b"
    orders_count: int
    total_amount: int   // тийины
  }, ...]
}
```

### Б.3 Finance Domain

#### EP-8: `GET /finances/revenue-trend` — scope: `finances:read`

Params: `date_from?`, `date_to?`, `granularity?` (day|week|month)

```
RevenueTrendResponse {
  points: [{
    period:       str
    revenue:      int   // тийины
    orders_count: int
  }, ...]
  total_revenue:  int
  total_orders:   int
  change_percent: float | null  // % vs предыдущий аналогичный период, round(..., 4)
}
```

#### EP-9: `GET /finances/debt-aging` — scope: `finances:read`, params: нет

```
DebtAgingResponse {
  buckets: [{
    label:         str          // "0-7 дней", "8-14 дней", "15-30 дней", "31-60 дней", "60+ дней"
    min_days:      int          // 0, 8, 15, 31, 61
    max_days:      int | null   // 7, 14, 30, 60, null
    clients_count: int
    total_amount:  int          // тийины
  }, ...]
  total_debt:    int
  total_debtors: int
}
```

#### EP-10: `GET /finances/top-debtors` — scope: `finances:read`

Params: `limit?` (1-100, default 10)

```
TopDebtorsResponse {
  debtors: [{
    client_id:         UUID
    client_name:       str
    client_type:       str          // "client_b2c" | "client_b2b"
    phone:             str | null   // ⚠ ВСЕГДА null (N+1 avoidance)
    debt_amount:       int          // тийины
    last_payment_date: date | null  // ISO date или null
    days_overdue:      int          // 0 если не вычислен
  }, ...]
  total_debt: int
}
```

#### EP-11: `GET /finances/payment-methods` — scope: `finances:read`

Params: `date_from?`, `date_to?`

```
PaymentMethodsFinanceResponse {
  methods: [{
    method:             str   // "cash" | "card" | "contract"
    transactions_count: int   // ⚠ НЕ orders_count (ср. EP-5)
    total_amount:       int   // тийины
  }, ...]
  // ⚠ НЕТ total_orders, total_amount на верхнем уровне (ср. EP-5)
}
```

#### EP-12: `GET /finances/summary-kpis` — scope: `finances:read`

Params: `date_from?`, `date_to?`

```
FinanceSummaryKPIs {
  avg_order_value:             int          // тийины (AOV)
  total_orders:                int
  total_revenue:               int          // тийины
  card_confirmation_rate:      float        // 0.0-1.0
  card_rejection_rate:         float        // 0.0-1.0
  avg_card_confirmation_hours: float | null // часы, null если нет данных
  collection_rate:             float        // 0.0-1.0 (deposited/collected)
  overdue_debt_ratio:          float        // 0.0-1.0 (долг >7д / общий долг)
}
```

#### EP-21: `GET /finances/revenue-by-segment` — scope: `finances:read`

Params: `date_from?`, `date_to?`

```
RevenueBySegmentResponse {
  segments: [{
    segment:         str   // "client_b2b" | "client_b2c"
    orders_count:    int
    total_revenue:   int   // тийины
    avg_order_value: int   // тийины
  }, ...]
  total_orders:  int
  total_revenue: int
}
```

### Б.4 Inventory Domain

#### EP-13: `GET /inventory/summary` — scope: `inventory:read`, params: нет

> **Storekeeper-фильтрация:** Если роль = STOREKEEPER, показываются только остатки своих складов. `containers_at_clients`, `stock_on_couriers` будут 0.

```
InventorySummary {
  total_water_stock:     int   // полные бутыли (склады + курьеры)
  total_container_stock: int   // пустые бутыли (склады + курьеры)
  total_equipment_stock: int   // оборудование (склады + курьеры)
  containers_at_clients: int   // тара у клиентов
  stock_on_couriers:     int   // всего единиц на курьерах
  losses_today:          int   // списания за сегодня
  active_couriers_count: int
}
```

#### EP-14: `GET /inventory/container-distribution` — scope: `inventory:read`, params: нет

> **Без storekeeper-фильтрации:** Возвращает глобальные данные по всей системе.

```
ContainerDistribution {
  at_warehouses:   int
  at_couriers:     int
  at_clients:      int
  lost:            int          // VIRTUAL_LOSS balance
  total_in_system: int          // ABS(VIRTUAL_VENDOR)
  per_product: [{
    product_id:    UUID
    product_name:  str
    at_warehouses: int   // default 0
    at_couriers:   int   // default 0
    at_clients:    int   // default 0
    lost:          int   // default 0
    total:         int   // default 0 (сумма 4 полей выше)
  }, ...]
}
```

#### EP-15: `GET /inventory/container-debtors` — scope: `inventory:read`

Params: `limit?` (1-100, default 10)

```
ContainerDebtorsResponse {
  debtors: [{
    client_id:             UUID
    client_name:           str
    client_type:           str
    container_balance:     int
    last_order_date:       str | null  // ⚠ тип str, не date
    days_since_last_order: int | null  // ⚠ ВСЕГДА null (не вычисляется)
  }, ...]
  total_containers_at_clients: int
}
```

#### EP-16: `GET /inventory/movement-stats` — scope: `inventory:read`

Params: `date_from?`, `date_to?`

> **Storekeeper-фильтрация:** Показывает только перемещения, связанные со складами текущего кладовщика.

```
MovementStatsResponse {
  types: [{
    transfer_type:  str   // TransferType enum value
    transfers_count: int
    total_items:     int
  }, ...]
  total_transfers: int
  total_items:     int
}
```

#### EP-18: `GET /inventory/trends` — scope: `inventory:read`

Params: `date_from?` (**default: today - 7 дней**), `date_to?`

```
InventoryTrendResponse {
  points: [{
    date:                  str   // "2026-03-15"
    water_stock:           int   // склады + курьеры
    container_stock:       int   // склады + курьеры
    containers_at_clients: int
  }, ...]
}
```

#### EP-19: `GET /inventory/virtual-accounts` — scope: `inventory:read`, params: нет

```
VirtualAccountsResponse {
  vendor_total:   int         // ABS(SUM VIRTUAL_VENDOR)
  loss_total:     int         // SUM VIRTUAL_LOSS
  real_total:     int         // SUM (WAREHOUSE + COURIER + CLIENT)
  integrity_ok:   bool        // vendor_total == loss_total + real_total
  integrity_diff: int         // разница (0 если ok)
  per_product: [{
    product_id:     UUID
    product_name:   str
    vendor_balance: int       // отрицательный
    loss_balance:   int       // положительный
  }, ...]
  loss_trend_30d: [{          // default [] (пустой массив)
    date:     str
    quantity: int
  }, ...]
}
```

### Б.5 Courier Domain

#### EP-17: `GET /couriers/fleet` — scope: `users:read`, params: нет

```
CourierFleetResponse {
  couriers: [{
    courier_id:               UUID
    courier_name:             str
    vehicle_id:               UUID | null
    vehicle_name:             str | null
    is_active:                bool          // есть ли активный транспорт
    vehicle_balances: [{                    // default []
      product_id:   UUID
      product_name: str
      quantity:     int
    }, ...]
    orders_assigned_today:    int   // default 0
    orders_delivered_today:   int   // default 0
    cash_balance:             int   // default 0, тийины
    cash_collected_today:     int   // default 0, тийины
    containers_collected_today: int // default 0
  }, ...]
  total_active:            int
  total_stock_on_couriers: int
  total_courier_cash:      int    // тийины
}
```

#### EP-20: `GET /couriers/load-by-days` — scope: `users:read`

Params: `date_from?`, `date_to?`

```
CourierLoadResponse {
  data: [{
    date:             str    // "2026-03-15"
    courier_id:       UUID
    courier_name:     str
    deliveries_count: int
  }, ...]
  total_deliveries: int
  avg_per_courier:  float   // round(..., 2)
  max_load:         int     // максимум одного курьера за один день
}
```

### Б.6 Сводная таблица Storekeeper-фильтрации

| EP    | Storekeeper-фильтрация | Эффект                                                                      |
| ----- | ---------------------- | --------------------------------------------------------------------------- |
| EP-13 | ✅ Да                  | Видит только свои склады; `containers_at_clients` и `stock_on_couriers` = 0 |
| EP-14 | ❌ Нет                 | Глобальные данные по всей системе                                           |
| EP-15 | ❌ Нет                 | Все должники по таре                                                        |
| EP-16 | ✅ Да                  | Только перемещения, связанные со своими складами                            |
| EP-18 | ❌ Нет                 | Глобальные тренды                                                           |
| EP-19 | ❌ Нет                 | Глобальные виртуальные счета (только для Админа по UI-решению)              |
