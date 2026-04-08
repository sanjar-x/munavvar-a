# HOD Platform — Contracts Module

## Frontend Integration Specification

---

| Реквизит             | Значение                                      |
| -------------------- | --------------------------------------------- |
| **Версия документа** | 3.2.0                                         |
| **Статус**           | APPROVED                                      |
| **Аудитория**        | Frontend-разработчики, QA-инженеры, Tech Lead |
| **Формат**           | BRD + FLOW + API SPEC                         |
| **Base URL**         | `{API_BASE}/api/v1`                           |
| **Источник истины**  | Backend-код: `src/modules/contracts/` + смежные модули |

> **Для Frontend-разработчика.** Данный документ объединяет бизнес-требования,
> диаграммы процессов и полную спецификацию API. Каждый endpoint включает
> TypeScript-типы, примеры запросов/ответов, таблицы валидации полей
> и карту ошибок. Копируйте типы «как есть» — они сгенерированы из
> Pydantic-схем backend'а.
>
> **v3.2+:** Помимо модуля Contracts, документ покрывает
> платформенные изменения API (авторизация, инвентарь, финансы,
> накладные), затрагивающие frontend-интеграцию. См. §19.26–19.28 и §20.9.

## Changelog v2.0.0 → v3.2.0

> **⚠️ Внимание Frontend-разработчиков!** Данная секция перечисляет все
> изменения между коммитами `19c2ccc` и `41c14e1`. Изменения сгруппированы
> по типу: ломающие (breaking), новые возможности и исправления.
> Начиная с v3.2.0 документ также покрывает **платформенные изменения API**,
> влияющие на frontend-интеграцию за пределами модуля Contracts.

### 🔴 Breaking Changes

| #   | Изменение                                      | Было              | Стало                                      | Раздел |
| --- | ---------------------------------------------- | ----------------- | ------------------------------------------ | ------ |
| 1   | Ответ `GET /backoffice/orders/`                | `OrderResponse[]` | `OrdersResponse` (обёртка с `total_count`) | §18.2  |
| 2   | Лимит `GET /backoffice/orders/`                | `le=500`          | `le=100`                                   | —      |
| 3   | Лимит `GET /backoffice/contracts/`             | `le=200`          | `le=100`                                   | §19.2  |
| 4   | Лимит `GET /{id}/orders`                       | `le=200`          | `le=100`                                   | §19.12 |
| 5   | Scope `POST /backoffice/orders/`               | `orders:edit`     | `orders:create`                            | —      |
| 6   | Scope `POST /backoffice/orders/warehouse-sale` | `orders:edit`     | `orders:create`                            | —      |
| 7   | Ответ `GET /client/orders/history`             | `OrderResponse[]` | `OrdersResponse`                           | §20.5  |
| 8   | Scope `DELETE /client/orders/{id}/items/{pid}` | `orders:create`   | `orders:cancel`                            | —      |
| 9   | Scope `GET /backoffice/clients/`               | `users:write`     | `users:read`                               | —      |
| 10  | Scope `GET /backoffice/clients/{id}`           | `users:write`     | `users:read`                               | —      |
| 11  | **Валюта: тийинов нет**                        | Описания ссылались на «тийины» | **Все суммы — целые числа в сумах (UZS)** | §💰 |
| 12  | `POST /client/login` — формат запроса          | `phone` как query-параметр | Request body `LocalLogin` `{phone, password}` | §18.3 |
| 13  | `GET /health` — проверка БД                    | `{"status":"ok","environment":"..."}` | `{"status":"ok"}` / 503 `{"status":"db_unavailable"}` | — |
| 14  | `POST /backoffice/shifts/close` **удалён**     | Роутер `/shifts` существовал | Роутер удалён полностью | — |
| 15  | `PATCH /backoffice/users/{id}` — валидация     | Без ограничений на self-edit | Запрет self-edit (`SELF_MODIFICATION_FORBIDDEN`) и назначения роли SYSTEM (`SYSTEM_ROLE_FORBIDDEN`) | §21 |

### 🟢 New Features

| #   | Что добавлено                                                                                           | Раздел               |
| --- | ------------------------------------------------------------------------------------------------------- | -------------------- |
| 1   | `OrderResponse` — 4 новых поля: `contract_id`, `reserved_credit_amount`, `notes`, `cancellation_reason` | §18.2                |
| 2   | Новый тип `OrdersResponse` (`total_count` + `orders[]`)                                                 | §18.2                |
| 3   | Новый тип `CancelOrderRequest` с полем `reason`                                                         | §18.3                |
| 4   | Новый тип `OrderStatus` enum                                                                            | §18.1                |
| 5   | `POST /backoffice/orders/jobs/expire-stale` — автоочистка устаревших заказов                            | §19.25               |
| 6   | `POST /client/orders/{id}/cancel` — отмена заказа клиентом                                              | §20.6                |
| 7   | `GET /client/orders/history` — пагинированная история с фильтром `status`                               | §20.5                |
| 8   | `GET /client/inventory/balance` — баланс тары клиента                                                   | §20.7                |
| 9   | `GET /courier/inventory/my-stock` — остатки товаров в машине курьера                                    | §20.8                |
| 10  | `GET /backoffice/finances/b2b-debts` — дебиторка B2B по договорам                                       | —                    |
| 11  | Suspend/Terminate/Expire контракта автоматически отменяют NEW/ASSIGNED заказы                           | §19.6, §19.8, §19.24 |
| 12  | `OrderCreate.notes` — заметки к доставке (код домофона, этаж и т.д.)                                    | §18.3                |
| 13  | Секция «Валютная конвенция» — `formatMoney()` утилита, полный перечень денежных полей                    | §💰                  |
| 14  | Фильтры накладных: `type`, `from_date`, `to_date`, `warehouse_id` на `GET /backoffice/transfers/`      | §19.28               |
| 15  | `GET /backoffice/inventories/search` — поиск инвентарей по названию и типу                              | §19.27               |
| 16  | `CourierCreate.password` теперь требует `min_length=8`                                                  | —                    |
| 17  | `DashboardTotals` — 2 новых B2B поля: `total_b2b_credit_used`, `total_b2b_settled_debt`                | §18.2                |
| 18  | `POST /backoffice/orders/` теперь возвращает `OrderResponse` (201)                                      | —                    |
| 19  | `GET /backoffice/finances/b2b-debts` — дебиторка B2B по договорам (полная спецификация)                 | §19.26               |

### 🔧 Fixes

| #   | Исправление                                                                                         | Влияние на Frontend                                     |
| --- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| 1   | Исправлен баг `bulk_cancel_by_contract`: кредит по отменённым заказам теперь корректно возвращается | `credit_used` обновляется правильно при массовой отмене |
| 2   | `expire-stale` теперь очищает и ASSIGNED заказы (72ч по `updated_at`)                               | Заказы в ASSIGNED не зависают бесконечно                |
| 3   | Фактуры за оплату с отсутствующим платежом генерируют предупреждение (аудит)                        | Нет изменения API, внутренний лог                       |
| 4   | `response_model` добавлен на все финансовые эндпоинты                                               | Ответы теперь строго типизированы                       |
| 5   | `POST /backoffice/system/seed` заблокирован в production                                            | 403 `SEEDER_DISABLED_IN_PROD` в prod-среде              |

---

# ЧАСТЬ I — BRD (Business Requirements Document)

## 1. Резюме проекта (Executive Summary)

Модуль «Договоры» автоматизирует полный цикл управления B2B-контрактами
на платформе HOD: от создания черновика до расторжения, включая
кредитное ценообразование, выставление счетов-фактур и финансовую сверку.

Ключевое ограничение: **один клиент = один активный договор**.
Это обеспечивается PostgreSQL partial unique index на уровне базы данных
и валидацией на уровне сервиса.

## 2. Бизнес-контекст

| Параметр              | Значение                                                           |
| --------------------- | ------------------------------------------------------------------ |
| Тип клиентов          | Юридические лица (B2B), role = `client_b2b`                        |
| Предмет договора      | Поставка бутилированной воды с отсрочкой платежа                   |
| Денежная единица      | Целые числа в сумах (UZS). Тийинов нет — дробная часть отсутствует |
| Кредитная модель      | `credit_limit = 0` → безлимитный; `> 0`                            |
| Ценообразование       | Индивидуальный прайс-лист → fallback на каталог                    |
| Биллинговый цикл      | По запросу: оператор генерирует счёт за произвольный период        |
| Сверка                | Акт сверки за период: DELIVERED заказы vs банковские платежи       |
| Инвариант целостности | `credit_used ≤ credit_limit` (или `credit_limit = 0`)              |

## 3. Матрица стейкхолдеров

| Роль            | Scope в JWT                                             | Область ответственности                              |
| --------------- | ------------------------------------------------------- | ---------------------------------------------------- |
| **Admin**       | `contracts:read`, `contracts:write`, `contracts:manage` | Полный CRUD, смена статусов, управление ценами, jobs |
| **Accountant**  | `contracts:read`                                        | Просмотр договоров, сверка, выгрузка документов      |
| **CLIENT_B2B**  | `contracts:read`                                        | Просмотр своего договора, прайс-листа, счетов        |
| **Storekeeper** | —                                                       | Нет доступа к договорам                              |
| **Cashier**     | —                                                       | Нет доступа к договорам                              |
| **Courier**     | —                                                       | Нет доступа к договорам                              |
| **CLIENT_B2C**  | —                                                       | Нет доступа к договорам                              |

## 4. Глоссарий

| Термин                          | Определение                                                                               |
| ------------------------------- | ----------------------------------------------------------------------------------------- |
| **Договор (Contract)**          | Юридическое соглашение между HOD и B2B-клиентом на поставку продукции с отсрочкой платежа |
| **Черновик (Draft)**            | Начальный статус договора; условия согласовываются, заказы запрещены                      |
| **Активация (Activate)**        | Перевод DRAFT → ACTIVE; фиксация `signed_at` и `signed_by_id`                             |
| **Приостановка (Suspend)**      | Перевод ACTIVE → SUSPENDED; требует `reason`; заказы блокируются                          |
| **Восстановление (Reinstate)**  | Перевод SUSPENDED → ACTIVE; проверяет отсутствие другого ACTIVE                           |
| **Расторжение (Terminate)**     | Перевод ACTIVE/SUSPENDED → TERMINATED; терминальный статус                                |
| **Истечение (Expire)**          | Автоматический ACTIVE → EXPIRED при `end_date < today`                                    |
| **Кредитный лимит**             | Максимальная сумма одновременных неоплаченных заказов; `0` = без ограничений              |
| **credit_used**                 | Сумма in-flight заказов (статусы NEW → ARRIVED); обновляется приложением                  |
| **Прайс-лист**                  | Индивидуальные цены по договору; при отсутствии — fallback на каталожную цену             |
| **Счёт-фактура (Invoice)**      | Документ биллинга за период; генерируется из DELIVERED заказов                            |
| **Акт сверки (Reconciliation)** | Сопоставление DELIVERED заказов и банковских платежей за период                           |
| **ДС (Amendment)**              | Дополнительное соглашение, фиксирующее изменения условий договора                         |
| **IDOR**                        | Insecure Direct Object Reference — атака через подстановку чужого ID                      |
| **Snapshot pricing**            | Цена фиксируется в `OrderItem.unit_price` на момент создания заказа                       |

## 5. Бизнес-цели

| ID   | Цель                                      | Метрика успеха                                      |
| ---- | ----------------------------------------- | --------------------------------------------------- |
| BO-1 | Автоматизировать жизненный цикл договоров | 100% переходов через API (не ручные SQL)            |
| BO-2 | Контролировать кредитные риски            | Ноль случаев превышения лимита                      |
| BO-3 | Индивидуальное ценообразование            | Прайс-лист на уровне договора с fallback на каталог |
| BO-4 | Автоматический биллинг                    | Генерация счетов из DELIVERED заказов за период     |
| BO-5 | Финансовая прозрачность                   | Акт сверки = разница DELIVERED vs оплата            |
| BO-6 | Юридическая трассируемость                | Каждый переход статуса зафиксирован в аудит-логе    |

## 6. User Stories

### 6.1 Admin Stories

| ID     | Story                                                       | Acceptance Criteria                                                |
| ------ | ----------------------------------------------------------- | ------------------------------------------------------------------ |
| US-A01 | Как Admin, я создаю черновик договора для B2B-клиента       | Договор создаётся в статусе DRAFT; при наличии ACTIVE — ошибка 409 |
| US-A02 | Как Admin, я активирую согласованный черновик               | Статус → ACTIVE; `signed_at` и `signed_by_id` заполняются          |
| US-A03 | Как Admin, я приостанавливаю договор при просрочке          | Статус → SUSPENDED; `reason` обязателен; заказы блокируются        |
| US-A04 | Как Admin, я восстанавливаю приостановленный договор        | Статус → ACTIVE; коллизия с другим ACTIVE — ошибка 409             |
| US-A05 | Как Admin, я расторгаю договор досрочно                     | Статус → TERMINATED; терминальный, необратимый                     |
| US-A06 | Как Admin, я устанавливаю индивидуальные цены на товары     | Upsert по `(contract_id, product_id)`                              |
| US-A07 | Как Admin, я генерирую счёт-фактуру за период               | Черновик с суммой DELIVERED заказов; дубли запрещены               |
| US-A08 | Как Admin, я выставляю счёт клиенту (DRAFT → ISSUED)        | `issued_at` заполняется; `due_date` рассчитан                      |
| US-A09 | Как Admin, я отмечаю счёт как оплаченный                    | ISSUED/OVERDUE → PAID; `paid_at` заполняется                       |
| US-A10 | Как Admin, я формирую акт сверки за произвольный период     | Заказы + платежи + баланс                                          |
| US-A11 | Как Admin, я запускаю job для пометки просроченных инвойсов | ISSUED → OVERDUE для `due_date < today`                            |
| US-A12 | Как Admin, я запускаю job для истечения договоров           | ACTIVE → EXPIRED для `end_date < today`                            |

### 6.2 Accountant Stories

| ID     | Story                                                  | Acceptance Criteria                         |
| ------ | ------------------------------------------------------ | ------------------------------------------- |
| US-B01 | Как Бухгалтер, я просматриваю список всех договоров    | Фильтрация по `clientId`, `status`          |
| US-B02 | Как Бухгалтер, я смотрю детали договора с прайс-листом | ContractDetailResponse с `price_items[]`    |
| US-B03 | Как Бухгалтер, я формирую акт сверки за период         | Reconciliation: orders + payments + balance |

### 6.3 CLIENT_B2B Stories

| ID     | Story                                                     | Acceptance Criteria                        |
| ------ | --------------------------------------------------------- | ------------------------------------------ |
| US-C01 | Как B2B-клиент, я вижу свой активный договор              | IDOR-safe: `/my-contract` без ID в пути    |
| US-C02 | Как B2B-клиент, я просматриваю свой прайс-лист            | `/my-contract/prices` — только мои цены    |
| US-C03 | Как B2B-клиент, я просматриваю свои счета-фактуры         | `/my-contract/invoices` — только мои счета |
| US-C04 | Как B2B-клиент, если у меня нет договора — вижу сообщение | 403 `CONTRACT_REQUIRED` с текстом          |

## 7. Бизнес-правила

### 7.1 Правила договоров

| ID    | Правило                                        | Обоснование                        | Контроль                                       |
| ----- | ---------------------------------------------- | ---------------------------------- | ---------------------------------------------- |
| BR-01 | Один ACTIVE договор на клиента                 | Исключить конфликт условий         | Partial unique index + проверка в сервисе      |
| BR-02 | DRAFT разрешает дубликаты                      | Параллельное согласование условий  | Index не затрагивает DRAFT                     |
| BR-03 | Расторжение и истечение — терминальные статусы | Юридическая необратимость          | Машина состояний в сервисе                     |
| BR-04 | Приостановка требует `reason` (3–512 символов) | Юридическое обоснование            | Pydantic `min_length=3, max_length=512`        |
| BR-05 | `end_date IS NULL` = бессрочный договор        | Контракты без фиксированного срока | NULL-able поле, CHECK: `end_date > start_date` |
| BR-06 | Восстановление проверяет коллизию              | Защита от параллельной активации   | `SELECT FOR UPDATE` + проверка existing        |

### 7.2 Правила кредитования

| ID    | Правило                                         | Обоснование               | Контроль                                      |
| ----- | ----------------------------------------------- | ------------------------- | --------------------------------------------- |
| BR-07 | `credit_limit = 0` → безлимитный                | Доверенные клиенты        | Условная проверка в коде                      |
| BR-08 | `credit_used ≤ credit_limit` (при `limit > 0`)  | Контроль рисков           | CHECK constraint + приложение                 |
| BR-09 | `credit_used` увеличивается при создании заказа | Резервирование кредита    | `+= order.total_amount` с `SELECT FOR UPDATE` |
| BR-10 | `credit_used` уменьшается при доставке/отмене   | Высвобождение кредита     | `-= order.total_amount`                       |
| BR-11 | Нельзя уменьшить `credit_limit < credit_used`   | Защита от нарушения CHECK | Проверка в `update_contract`                  |

### 7.3 Правила ценообразования

| ID    | Правило                                        | Обоснование               | Контроль                                 |
| ----- | ---------------------------------------------- | ------------------------- | ---------------------------------------- |
| BR-12 | Прайс-лист — upsert по `(contract, product)`   | Упрощение API             | `PUT /{id}/prices/{product_id}`          |
| BR-13 | Удаление позиции → fallback на каталожную цену | Гарантия цены при заказе  | `DELETE /{id}/prices/{product_id}`       |
| BR-14 | Snapshot pricing при создании заказа           | Юридическая фиксация цены | `OrderItem.unit_price` копирует значение |

### 7.4 Правила инвойсов

| ID    | Правило                                              | Обоснование               | Контроль                               |
| ----- | ---------------------------------------------------- | ------------------------- | -------------------------------------- |
| BR-15 | Один не-CANCELLED инвойс за период                   | Исключить дубли           | Проверка в `generate_invoice`          |
| BR-16 | `due_date = period_to + payment_due_days`            | Автоматический расчёт     | Сервис вычисляет при создании          |
| BR-17 | Номер: `{contract.number}/{YYYY}-{MM}-{seq:03d}`     | Уникальная нумерация      | Генерация в сервисе, UNIQUE constraint |
| BR-18 | `partially_paid` существует в enum, но НЕ реализован | Зарезервировано для v2    | **Не показывать в UI**                 |
| BR-19 | PAID и OVERDUE нельзя аннулировать                   | Защита финансовых записей | Проверка в `cancel_invoice`            |

## 8. Ограничения и допущения

| Тип         | Описание                                                                                        |
| ----------- | ----------------------------------------------------------------------------------------------- |
| Ограничение | Все суммы — целые числа в сумах (UZS), без тийинов. Отображать как есть: `12500` → `12 500 сум` |
| Ограничение | `credit_used` обновляется приложением, не триггерами. Возможна кратковременная десинхронизация  |
| Ограничение | `partially_paid` присутствует в enum, но **не имеет** серверной реализации. Не рендерить в UI   |
| Допущение   | Один клиент имеет не более одного ACTIVE договора в любой момент времени                        |
| Допущение   | Все даты — ISO 8601 (`YYYY-MM-DD`), все timestamps — ISO 8601 с timezone                        |
| Допущение   | Job-эндпоинты идемпотентны: повторный вызов безопасен (`updated: 0`)                            |

## 9. Out of Scope (v1)

| Функция                           | Причина исключения                           | Статус         |
| --------------------------------- | -------------------------------------------- | -------------- |
| Частичная оплата инвойсов         | `partially_paid` зарезервирован в enum       | Планируется v2 |
| Автоматическая генерация инвойсов | Cron/Celery не настроен                      | Планируется v2 |
| Электронная подпись (ЭЦП)         | Требует интеграции с ГНСК                    | Вне скоупа     |
| PDF-генерация документов          | Требует шаблонизатор (WeasyPrint)            | Планируется v2 |
| Мультивалютность                  | Все операции в UZS (целые сумы, без тийинов) | Вне скоупа     |
| Уведомления (email/SMS)           | Сервис уведомлений не реализован             | Планируется v2 |

---

# ЧАСТЬ II — FLOW (Business Process Flows)

## 10. Машина состояний: Договор (Contract)

### 10.1 Диаграмма переходов

```
                    ┌──────────┐
                    │  DRAFT   │
                    └────┬─────┘
                         │ activate
                         ▼
          ┌──────── ACTIVE ────────┐
          │         │    │         │
          │suspend  │    │terminate│
          │         │    │         │
          ▼         │    │         ▼
     SUSPENDED      │    │    TERMINATED
          │         │    │
          │reinstate│    │ expire (auto)
          │         │    │
          └─────────┘    ▼
                      EXPIRED
```

### 10.2 Матрица переходов

| Из / В         | DRAFT | ACTIVE | SUSPENDED | TERMINATED | EXPIRED |
| -------------- | :---: | :----: | :-------: | :--------: | :-----: |
| **DRAFT**      |   —   |   ✅   |    ❌     |     ❌     |   ❌    |
| **ACTIVE**     |  ❌   |   —    |    ✅     |     ✅     |   ✅¹   |
| **SUSPENDED**  |  ❌   |   ✅   |     —     |     ✅     |   ❌    |
| **TERMINATED** |  ❌   |   ❌   |    ❌     |     —      |   ❌    |
| **EXPIRED**    |  ❌   |   ❌   |    ❌     |     ❌     |    —    |

> ¹ EXPIRED — только автоматический переход (job).

### 10.3 Семантика состояний

| Статус       | Заказы разрешены | Условия редактируемы | Терминальный | API-триггер                   |
| ------------ | :--------------: | :------------------: | :----------: | ----------------------------- |
| `draft`      |        ❌        |          ✅          |      ❌      | `POST /`                      |
| `active`     |        ✅        |          ✅          |      ❌      | `POST /{id}/activate`         |
| `suspended`  |        ❌        |          ❌          |      ❌      | `POST /{id}/suspend`          |
| `terminated` |        ❌        |          ❌          |      ✅      | `POST /{id}/terminate`        |
| `expired`    |        ❌        |          ❌          |      ✅      | `POST /jobs/expire-contracts` |

### 10.4 Блокирующие условия переходов

| Переход            | Блокирующее условие                      | Ошибка                             |
| ------------------ | ---------------------------------------- | ---------------------------------- |
| DRAFT → ACTIVE     | Текущий статус ≠ DRAFT                   | `CONTRACT_STATUS_TRANSITION_ERROR` |
| DRAFT → ACTIVE     | У клиента уже есть ACTIVE договор        | `CONTRACT_ALREADY_ACTIVE`          |
| ACTIVE → SUSPENDED | Текущий статус ≠ ACTIVE                  | `CONTRACT_STATUS_TRANSITION_ERROR` |
| SUSPENDED → ACTIVE | Текущий статус ≠ SUSPENDED               | `CONTRACT_STATUS_TRANSITION_ERROR` |
| SUSPENDED → ACTIVE | У клиента уже есть другой ACTIVE договор | `CONTRACT_ALREADY_ACTIVE`          |
| → TERMINATED       | Текущий статус ∉ {ACTIVE, SUSPENDED}     | `CONTRACT_STATUS_TRANSITION_ERROR` |

## 11. Машина состояний: Счёт-фактура (Invoice)

### 11.1 Диаграмма переходов

```
    ┌──────────┐
    │  DRAFT   │──────────────┐
    └────┬─────┘              │
         │ issue              │ cancel
         ▼                    ▼
    ┌──────────┐        ┌───────────┐
    │  ISSUED  │────────│ CANCELLED │
    └────┬──┬──┘        └───────────┘
         │  │
  overdue │  │ mark-paid
  (auto)  │  │
         ▼  ▼
    OVERDUE  PAID
      │
      │ mark-paid
      ▼
     PAID
```

### 11.2 Матрица переходов

| Из / В        | DRAFT | ISSUED | PAID | OVERDUE | CANCELLED |
| ------------- | :---: | :----: | :--: | :-----: | :-------: |
| **DRAFT**     |   —   |   ✅   |  ❌  |   ❌    |    ✅     |
| **ISSUED**    |  ❌   |   —    |  ✅  |   ✅¹   |    ✅     |
| **PAID**      |  ❌   |   ❌   |  —   |   ❌    |    ❌     |
| **OVERDUE**   |  ❌   |   ❌   |  ✅  |    —    |    ❌     |
| **CANCELLED** |  ❌   |   ❌   |  ❌  |   ❌    |     —     |

> ¹ OVERDUE — только автоматический переход (job).

### 11.3 Семантика статусов инвойсов

| Статус      | Описание                            | Терминальный | Можно аннулировать |
| ----------- | ----------------------------------- | ------------ | ------------------ |
| `draft`     | Черновик, формируется автоматически | ❌           | ✅                 |
| `issued`    | Выставлен клиенту, ожидает оплаты   | ❌           | ✅                 |
| `paid`      | Полностью оплачен                   | ✅           | ❌                 |
| `overdue`   | Срок оплаты истёк                   | ❌           | ❌                 |
| `cancelled` | Аннулирован                         | ✅           | —                  |

> ⚠️ `partially_paid` существует в enum, но **НЕ реализован** на сервере.
> **Не отображать** этот статус в UI.

## 12. Жизненный цикл кредита

### 12.1 Формулы

```
available_credit = credit_limit == 0
    ? Infinity
    : credit_limit - credit_used

can_place_order = credit_limit == 0
    ? true
    : credit_used + order_amount <= credit_limit
```

### 12.2 Диаграмма потока

```
Создание заказа:
  ┌─ Проверить: contract.status == "active" ─── нет → CONTRACT_NOT_ACTIVE
  ├─ Проверить: end_date == null || end_date >= today ─── нет → CONTRACT_EXPIRED
  ├─ Проверить: credit_limit == 0 || credit_used + amount ≤ credit_limit
  │      └── нет → CREDIT_LIMIT_EXCEEDED
  ├─ SELECT FOR UPDATE contract (TOCTOU protection)
  ├─ credit_used += order.total_amount
  └─ Создать заказ

Доставка (DELIVERED) / Забор (PICKUP_COMPLETED):
  ├─ credit_used -= order.total_amount
  └─ Commit

Отмена (CANCELLED):
  ├─ credit_used -= order.total_amount
  └─ Commit
```

### 12.3 Race Condition Protection

Backend использует `SELECT FOR UPDATE` на строке `contracts` при:

- Активации договора (проверка коллизии ACTIVE)
- Восстановлении из SUSPENDED (проверка коллизии ACTIVE)
- Создании заказа (проверка кредитного лимита)

Frontend **не должен** реализовывать свою блокировку — достаточно
обработать ошибки `CONTRACT_ALREADY_ACTIVE` и `CREDIT_LIMIT_EXCEEDED`.

## 13. Процессные потоки

### 13.1 Создание и активация договора

```
Admin                     API                           DB
  │                        │                             │
  ├── POST / ────────────► │                             │
  │   {clientId, data}     ├── check ACTIVE exists ────► │
  │                        │◄──── null / existing ───── │
  │                        │                             │
  │   [existing?] ◄────── 409 CONTRACT_ALREADY_ACTIVE    │
  │                        │                             │
  │                        ├── INSERT contract ────────► │
  │   ◄── 201 Contract ── │◄──── OK ─────────────────── │
  │                        │                             │
  │  ... согласование ...  │                             │
  │                        │                             │
  ├── POST /{id}/activate ► │                             │
  │                        ├── SELECT FOR UPDATE ──────► │
  │                        ├── check ACTIVE collision ──► │
  │                        ├── UPDATE status=active ───► │
  │                        ├── INSERT status_log ──────► │
  │   ◄── 200 Contract ── │◄──── COMMIT ───────────── │
```

#### Ошибки создания и активации

| Шаг       | Условие                          | HTTP | Код ошибки                         |
| --------- | -------------------------------- | ---- | ---------------------------------- |
| Создание  | У клиента есть ACTIVE договор    | 409  | `CONTRACT_ALREADY_ACTIVE`          |
| Активация | Договор не в статусе DRAFT       | 409  | `CONTRACT_STATUS_TRANSITION_ERROR` |
| Активация | У клиента появился другой ACTIVE | 409  | `CONTRACT_ALREADY_ACTIVE`          |

### 13.2 Приостановка и восстановление

```
Admin                      API                          DB
  │                         │                            │
  ├── POST /{id}/suspend ──► │                            │
  │   {reason: "..."}       ├── SELECT FOR UPDATE ─────► │
  │                         ├── status != ACTIVE? ──► 409│
  │                         ├── UPDATE suspended ──────► │
  │                         ├── INSERT status_log ─────► │
  │   ◄── 200 Contract ─── │◄──── COMMIT ──────────── │
  │                         │                            │
  │  ... устранение ...     │                            │
  │                         │                            │
  ├── POST /{id}/reinstate ► │                            │
  │                         ├── SELECT FOR UPDATE ─────► │
  │                         ├── check ACTIVE collision ─► │
  │                         ├── UPDATE active ──────────► │
  │                         ├── INSERT status_log ─────► │
  │   ◄── 200 Contract ─── │◄──── COMMIT ──────────── │
```

### 13.3 Биллинговый цикл

```
Admin                      API                          DB
  │                         │                            │
  ├── POST /{id}/invoices ─► │                            │
  │   {period_from, to}     ├── check duplicate ───────► │
  │                         │   [duplicate?] → 409       │
  │                         ├── SUM(DELIVERED orders) ──► │
  │                         ├── INSERT invoice DRAFT ───► │
  │   ◄── 201 Invoice ──── │◄──── COMMIT ──────────── │
  │                         │                            │
  ├── POST /.../issue ─────► │                            │
  │                         ├── DRAFT? → UPDATE ISSUED ─► │
  │   ◄── 200 Invoice ──── │◄──── COMMIT ──────────── │
  │                         │                            │
  │  ... клиент оплачивает ...                           │
  │                         │                            │
  ├── POST /.../mark-paid ─► │                            │
  │                         ├── ISSUED|OVERDUE? → PAID ─► │
  │   ◄── 200 Invoice ──── │◄──── COMMIT ──────────── │
```

### 13.4 Автоматические jobs

```
Scheduler (Admin)           API                         DB
  │                          │                           │
  ├── POST /jobs/mark-overdue ► │                         │
  │                          ├── WHERE status=ISSUED    │
  │                          │   AND due_date < today ──► │
  │                          ├── UPDATE → OVERDUE ──────► │
  │   ◄── {updated: N} ──── │◄──── COMMIT ─────────── │
  │                          │                           │
  ├── POST /jobs/expire-contracts ►                       │
  │                          ├── WHERE status=ACTIVE     │
  │                          │   AND end_date < today ──► │
  │                          ├── UPDATE → EXPIRED ──────► │
  │                          ├── INSERT status_log ─────► │
  │                          ├─ CANCEL in-flight orders ► │  ← NEW v3.0
  │                          │  (NEW/ASSIGNED → CANCELLED) │
  │                          │  + INSERT OrderStatusLog ─► │
  │                          │  + credit_used -= amount ─► │
  │   ◄── {updated: N} ──── │◄──── COMMIT ─────────── │
  │                          │                           │
  ├── POST /orders/jobs/expire-stale ►                    │  ← NEW v3.0
  │   {maxAgeHours, assignedMaxAgeHours}                  │
  │                          ├── NEW: created_at < X ──► │
  │                          ├── ASSIGNED: updated_at<Y ► │
  │                          ├── CANCEL + credit return ► │
  │   ◄── {cancelled: N} ── │◄──── COMMIT ─────────── │
```

### 13.5 Клиентский портал (B2B)

```
CLIENT_B2B                   API                         DB
  │                           │                           │
  ├── GET /my-contract ──────► │                           │
  │                           ├── find ACTIVE by          │
  │                           │   current_user.id ──────► │
  │                           │                           │
  │   [no contract?] ◄── 403 CONTRACT_REQUIRED           │
  │   [found] ◄── 200 ContractDetailResponse             │
  │                           │                           │
  ├── GET /my-contract/prices ► │                          │
  │   ◄── 200 PriceItem[] ── │                           │
  │                           │                           │
  ├── GET /my-contract/invoices ►│                         │
  │   ◄── 200 Invoice[] ──── │                           │
  │                           │                           │
  ├── GET /my-contract/invoices/{id} ►│              ← NEW v3.0
  │   ◄── 200 Invoice ────── │  (IDOR-safe)              │
```

### 13.6 Клиентское управление заказами (NEW v3.0)

```
CLIENT (B2B/B2C)              API                         DB
  │                            │                           │
  ├── GET /client/orders/history ►│                        │
  │   ?skip=0&limit=20&status=.. ├── filter by user_id ──► │
  │   ◄── OrdersResponse ──── │  {total_count, orders[]}  │
  │                            │                           │
  ├── GET /client/orders/{id} ─► │                          │
  │                            ├── check owner (IDOR) ───► │
  │   ◄── 200 OrderResponse ── │                           │
  │                            │                           │
  ├── POST /client/orders/{id}/cancel ►│                   │
  │   {reason?: "..."} ◄────── ├── check owner (IDOR) ──► │
  │                            ├── status ∈ {NEW,ASSIGNED}│
  │                            ├── cancel + credit return ►│
  │   ◄── 200 OrderResponse ── │◄──── COMMIT ─────────── │
  │                            │                           │
  ├── GET /client/inventory/balance ►│                      │
  │   ◄── BalanceResponse[] ── │  (тара на адресах)        │
```

## 14. Интеграция: Contracts ↔ Orders

### 14.1 При создании заказа (Orders module)

```typescript
// Логика на стороне Orders service (НЕ Contracts):
// 1. Определить payment_method
// 2. Если payment_method === 'contract':
//    a. Загрузить активный договор клиента
//    b. Проверить contract.status === 'active'
//    c. Проверить end_date
//    d. Проверить credit ceiling
//    e. Получить цены: contract_price ?? catalog_price
//    f. credit_used += total_amount (SELECT FOR UPDATE)
//    g. Snapshot price → OrderItem.unit_price
```

### 14.2 При завершении/отмене заказа

```
Order DELIVERED / PICKUP_COMPLETED / CANCELLED:
  → contract.credit_used -= order.reserved_credit_amount
```

> **NEW v3.0:** При отмене заказа поле `cancellation_reason` записывается
> в заказ. Если отмена произошла автоматически (expire/suspend/terminate
> контракта), причина устанавливается системой. При ручной отмене клиентом
> или бэкофисом — берётся из `CancelOrderRequest.reason`.

---

# ЧАСТЬ III — API SPEC (Technical Specification)

## 15. Аутентификация

### 15.1 Схема

```
Authorization: Bearer <JWT>
```

JWT содержит:

```json
{
  "sub": "019...", // user_id (UUIDv7)
  "scopes": ["contracts:read", "contracts:write", "contracts:manage"],
  "role": "admin",
  "exp": 1735689600
}
```

### 15.2 Матрица скоупов для Contracts

| Scope              | Операции                                                                                                    |
| ------------------ | ----------------------------------------------------------------------------------------------------------- |
| `contracts:read`   | GET list, GET detail, GET prices, GET orders, GET invoices, GET reconciliation, GET history, GET amendments |
| `contracts:write`  | POST create, PATCH update, PUT price, DELETE price                                                          |
| `contracts:manage` | POST activate/suspend/reinstate/terminate, POST invoice ops, POST amendments, POST jobs                     |

### 15.3 Ошибки аутентификации

| HTTP | Код ошибки           | Причина                           |
| ---- | -------------------- | --------------------------------- |
| 401  | `NOT_AUTHENTICATED`  | Отсутствует или невалидный токен  |
| 403  | `INSUFFICIENT_SCOPE` | Токен не содержит требуемый scope |

## 16. Base Paths

| Аудитория      | Base Path                      | Авторизация        |
| -------------- | ------------------------------ | ------------------ |
| **Backoffice** | `/api/v1/backoffice/contracts` | Admin / Accountant |
| **Client B2B** | `/api/v1/client/contracts`     | CLIENT_B2B         |

### Среды

| Среда       | URL                            |
| ----------- | ------------------------------ |
| Development | `http://localhost:8000/api/v1` |
| Production  | `https://api.hod.uz/api/v1`    |

## 17. Конверт ответа (Response Envelope)

### Успешный ответ

```json
// Одиночный объект — 200/201:
{ "id": "...", "status": "active", ... }

// Список — 200:
[ { "id": "...", ... }, { "id": "...", ... } ]

// Без тела — 204:
(пустой ответ)
```

### Ответ с ошибкой

```json
{
  "error": {
    "code": "CONTRACT_NOT_FOUND",
    "message": "Договор не найден",
    "details": {
      "contract_id": "019..."
    }
  }
}
```

## 💰 Валютная конвенция (Currency Convention)

> **⚠️ КРИТИЧЕСКИ ВАЖНО для Frontend-разработчиков**

### Основное правило

**Все денежные значения — целые числа в сумах (UZS). Тийинов нет.**

| Параметр               | Значение                                                   |
| ---------------------- | ---------------------------------------------------------- |
| Единица измерения      | 1 = 1 сум (UZS)                                            |
| Тип данных             | `int` (целое число)                                        |
| Минимальная единица    | 1 сум (дробной части нет)                                  |
| Формат отображения     | `12 500 сум` (разделитель тысяч — пробел)                  |
| Десятичные знаки       | **Нет.** Никогда не делить/умножать на 100                 |
| Отрицательные значения | Допустимы для `balance` (означает долг)                    |
| Ноль                   | `credit_limit = 0` → безлимитный; `amount = 0` → нет суммы |

### Какие поля являются денежными

```typescript
// ✅ Все эти поля — целые числа в сумах (UZS):
type MoneyField =
  | "price" // Цена товара / позиции прайс-листа
  | "unit_price" // Историческая цена в OrderItem
  | "total" // quantity × unit_price в OrderItem
  | "total_amount" // Сумма заказа
  | "amount" // Сумма инвойса / транзакции / платежа
  | "credit_limit" // Кредитный лимит договора
  | "credit_used" // Использованный кредит
  | "reserved_credit_amount" // Зарезервированный кредит заказа
  | "balance" // Баланс счёта / сверки
  | "opening_balance" // Начальное сальдо
  | "closing_balance" // Конечное сальдо
  | "running_balance" // Текущее сальдо
  | "debt_amount" // Сумма долга
  | "revenue" // Выручка
  | "avg_order_value" // Средний чек
  | "cash_balance"; // Касса курьера
```

### Утилита форматирования

```typescript
/**
 * Форматирует сумму в сумах (UZS).
 * Backend отдаёт целое число — никакого деления на 100!
 *
 * @example formatMoney(12500)  → "12 500 сум"
 * @example formatMoney(0)      → "0 сум"
 * @example formatMoney(-3000)  → "−3 000 сум"
 */
function formatMoney(amount: number): string {
  const formatted = Math.abs(amount)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const sign = amount < 0 ? "−" : "";
  return `${sign}${formatted} сум`;
}

/**
 * Форматирует кредитный лимит.
 * 0 = без ограничений (особый случай).
 */
function formatCreditLimit(limit: number): string {
  return limit === 0 ? "Без ограничений" : formatMoney(limit);
}
```

### Частые ошибки (Anti-patterns)

```typescript
// ❌ НЕПРАВИЛЬНО — тийинов нет, не надо делить на 100
const display = (amount / 100).toFixed(2) + " сум";

// ❌ НЕПРАВИЛЬНО — не использовать toFixed
const display = amount.toFixed(2) + " сум";

// ❌ НЕПРАВИЛЬНО — не использовать parseFloat
const parsed = parseFloat(response.price);

// ✅ ПРАВИЛЬНО — значение уже в сумах, целое число
const display = formatMoney(response.price);
```

---

## 18. TypeScript типы

### 18.1 Enums

```typescript
/** Статус договора. Значения совпадают с backend enum. */
enum ContractStatus {
  DRAFT = "draft",
  ACTIVE = "active",
  SUSPENDED = "suspended",
  TERMINATED = "terminated",
  EXPIRED = "expired",
}

/**
 * Статус счёта-фактуры.
 * ⚠️ PARTIALLY_PAID существует в backend enum,
 *    но НЕ РЕАЛИЗОВАН. Не использовать в UI.
 */
enum InvoiceStatus {
  DRAFT = "draft",
  ISSUED = "issued",
  PAID = "paid",
  OVERDUE = "overdue",
  CANCELLED = "cancelled",
  // PARTIALLY_PAID = 'partially_paid' — NOT IMPLEMENTED
}

/** Статус заказа. NEW v3.0 */
enum OrderStatus {
  NEW = "new",
  ASSIGNED = "assigned",
  IN_TRANSIT = "in_transit",
  ARRIVED = "arrived",
  DELIVERED = "delivered",
  PICKUP_READY = "pickup_ready",
  PICKUP_COMPLETED = "pickup_completed",
  CANCELLED = "cancelled",
}

/** Способ оплаты. NEW v3.0 */
enum PaymentMethod {
  CASH = "cash",
  CARD = "card",
  CONTRACT = "contract",
}

/** Тип продажи. NEW v3.0 */
enum SaleType {
  DELIVERY = "delivery",
  WAREHOUSE_PICKUP = "warehouse_pickup",
}

/** Тип инвентаря. NEW v3.2 */
enum InventoryType {
  WAREHOUSE = "WAREHOUSE",
  COURIER = "COURIER",
  CLIENT = "CLIENT",
  VIRTUAL_LOSS = "VIRTUAL_LOSS",
  VIRTUAL_VENDOR = "VIRTUAL_VENDOR",
}

/** Тип накладной. NEW v3.2 */
enum TransferType {
  COURIER_LOAD = "COURIER_LOAD",
  COURIER_RETURN = "COURIER_RETURN",
  CLIENT_DELIVERY = "CLIENT_DELIVERY",
  CLIENT_RETURN = "CLIENT_RETURN",
  LOSS_WRITE_OFF = "LOSS_WRITE_OFF",
  INVENTORY_FINDING = "INVENTORY_FINDING",
  INITIAL_BALANCE = "INITIAL_BALANCE",
  WAREHOUSE_SALE = "WAREHOUSE_SALE",
  WAREHOUSE_TARA_RETURN = "WAREHOUSE_TARA_RETURN",
}

/** Статус накладной. NEW v3.2 */
enum TransferStatus {
  DRAFT = "DRAFT",
  COMPLETED = "COMPLETED",
  CANCELLED = "CANCELLED",
}
```

### 18.2 Response Types

```typescript
/** Краткий ответ договора (список, создание, обновление) */
interface ContractResponse {
  id: string; // UUIDv7
  client_id: string; // UUIDv7
  number: string; // "HOD-2025-001"
  status: ContractStatus;
  start_date: string; // "2025-01-01" (ISO date)
  end_date: string | null; // null = бессрочный
  credit_limit: number; // сум (UZS), 0 = безлимитный
  credit_used: number; // сум (UZS), in-flight сумма
  payment_due_days: number; // 1–365
  legal_name: string;
  inn: string; // 9–14 символов
  legal_address: string | null;
  bank_account_number: string | null;
  bank_name: string | null;
  notes: string | null;
  signed_at: string | null; // ISO datetime
  signed_by_id: string | null; // UUIDv7
  suspended_at: string | null;
  suspension_reason: string | null;
  terminated_at: string | null;
  termination_reason: string | null;
  is_active: boolean;
  created_at: string; // ISO datetime
  updated_at: string; // ISO datetime
}

/** Детальный ответ с прайс-листом */
interface ContractDetailResponse extends ContractResponse {
  price_items: PriceItemResponse[];
}

/** Позиция прайс-листа */
interface PriceItemResponse {
  id: string;
  contract_id: string;
  product_id: string;
  price: number; // сум (UZS)
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** Счёт-фактура */
interface InvoiceResponse {
  id: string;
  contract_id: string;
  number: string; // "HOD-2025-001/2025-03-001"
  status: InvoiceStatus;
  period_from: string; // ISO date
  period_to: string; // ISO date
  amount: number; // сум (UZS)
  due_date: string | null; // ISO date
  issued_at: string | null; // ISO datetime
  paid_at: string | null; // ISO datetime
  created_at: string;
  updated_at: string;
}

/** Запись аудит-лога */
interface ContractStatusLogResponse {
  id: string;
  contract_id: string;
  from_status: ContractStatus | null; // null = создание
  to_status: ContractStatus;
  changed_by_id: string | null; // null = системное действие
  reason: string | null;
  created_at: string;
}

/** Дополнительное соглашение */
interface AmendmentResponse {
  id: string;
  contract_id: string;
  number: string; // "ДС-001"
  description: string;
  effective_date: string; // ISO date
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
}

/** Элемент акта сверки — заказ */
interface ReconciliationOrderItem {
  order_id: string;
  created_at: string;
  total_amount: number;
}

/** Элемент акта сверки — платёж */
interface ReconciliationPaymentItem {
  transaction_id: string;
  created_at: string;
  amount: number;
  reason: string | null;
}

/** Полный акт сверки */
interface ReconciliationResponse {
  contract_id: string;
  contract_number: string;
  client_name: string;
  period_from: string; // ISO date
  period_to: string; // ISO date
  orders: ReconciliationOrderItem[];
  total_billed: number; // сум (UZS)
  payments: ReconciliationPaymentItem[];
  total_paid: number; // сум (UZS)
  balance: number; // сум (UZS), total_billed - total_paid; >0 = клиент должен
}

/** Ответ job-эндпоинтов */
interface JobResponse {
  updated: number;
}

/**
 * Полная модель заказа. NEW v3.0
 * ⚠️ Используется в интеграции Contracts ↔ Orders.
 * Поля contract_id и reserved_credit_amount присутствуют
 * только при payment_method === 'contract'.
 */
interface OrderResponse {
  id: string;
  client_id: string;
  client: UserResponse;
  client_inventory_id: string;
  client_inventory: InventoryResponse;
  courier_id: string | null;
  courier: UserResponse | null;
  status: OrderStatus;
  payment_method: PaymentMethod;
  total_amount: number; // сум (UZS)
  capitalization_applied: boolean;
  sale_type: SaleType;
  warehouse_id: string | null;
  contract_id: string | null; // NEW v3.0 — ID договора
  reserved_credit_amount: number | null; // сум (UZS), NEW v3.0
  notes: string | null; // NEW v3.0 — заметки к доставке
  cancellation_reason: string | null; // NEW v3.0 — причина отмены
  items: OrderItemResponse[];
  stock_transfers: TransferResponse[];
  created_at: string; // ISO datetime
  updated_at: string; // ISO datetime
}

/**
 * Обёртка для пагинированного списка заказов. NEW v3.0
 * ⚠️ BREAKING: заменяет OrderResponse[] во всех list-эндпоинтах.
 */
interface OrdersResponse {
  total_count: number;
  orders: OrderResponse[];
}

/** Позиция заказа */
interface OrderItemResponse {
  id: string;
  product_id: string;
  product: ProductResponse;
  quantity: number;
  unit_price: number; // сум (UZS), историческая цена
  total: number; // сум (UZS), quantity × unit_price
}

// ─── Платформенные типы (NEW v3.2) ──────────────────────────

/**
 * Краткое представление пользователя.
 * Вкладывается в WarehouseDetailResponse, TransferResponse и др.
 */
interface UserShortResponse {
  id: string;
  username: string;
  phone: string | null;
}

/** Краткий ответ инвентаря (вложение в TransferResponse) */
interface InventoryShortResponse {
  id: string;
  name: string;
  type: InventoryType;
}

/** Упрощённый продукт (вложение в TransferItemResponse) */
interface ProductSimpleResponse {
  id: string;
  name: string;
  type: string; // ProductType
  price: number; // сум (UZS), NEW v3.2
  is_active: boolean;
}

/** Позиция накладной */
interface TransferItemResponse {
  product: ProductSimpleResponse;
  quantity: number;
}

/** Накладная (полная модель). NEW v3.2 */
interface TransferResponse {
  id: string;
  from_id: string;
  to_id: string;
  from_inventory: InventoryShortResponse | null;
  to_inventory: InventoryShortResponse | null;
  created_by_id: string;
  created_by: UserShortResponse | null; // NEW v3.2
  accepted_by_id: string | null;
  accepted_by: UserShortResponse | null; // NEW v3.2
  status: TransferStatus;
  type: TransferType;
  items: TransferItemResponse[];
  reason: string | null;
  route_sheet_id: string | null;
  created_at: string; // ISO datetime
}

/** Детали склада. NEW v3.2 */
interface WarehouseDetailResponse {
  id: string;
  name: string;
  user_id: string;
  user: UserShortResponse | null; // NEW v3.2
  balances: BalanceItem[];
}

/** Результат поиска инвентаря. NEW v3.2 */
interface InventorySearchResult {
  id: string;
  name: string;
  type: InventoryType;
  user_id: string;
}

/** Итоги финансового дашборда. NEW v3.2 — 2 новых B2B поля */
interface DashboardTotals {
  total_revenue: number; // сум (UZS)
  total_cash_in_hand: number; // сум (UZS)
  total_card_pending: number; // сум (UZS)
  total_client_debt: number; // сум (UZS)
  total_courier_cash: number; // сум (UZS)
  total_b2b_credit_used: number; // сум (UZS), NEW v3.2 — in-flight B2B кредит
  total_b2b_settled_debt: number; // сум (UZS), NEW v3.2 — погашённый долг B2B
}

/** Дебиторка по одному B2B-договору. NEW v3.2 */
interface B2BContractDebt {
  client_id: string;
  client_name: string;
  contract_id: string;
  contract_number: string;
  credit_limit: number; // сум (UZS), 0 = безлимитный
  credit_used: number; // сум (UZS)
  account_balance: number; // сум (UZS)
  total_exposure: number; // сум (UZS), credit_used + |account_balance|
  limit_utilization_pct: number; // 0.0–1.0 (float)
  due_date_status: "ok" | "overdue" | "no_limit";
}

/** Список B2B-дебиторки с итогом. NEW v3.2 */
interface B2BContractDebtsResponse {
  items: B2BContractDebt[];
  total_exposure: number; // сум (UZS), сумма по всем договорам
}
```

### 18.3 Request Types

```typescript
/**
 * Вход клиента. NEW v3.2 (BREAKING: ранее phone был query-параметром)
 * ⚠️ Теперь отправляется как JSON body, НЕ query string.
 */
interface LocalLogin {
  phone: string;
  password: string; // min_length=1
}

/** Создание договора */
interface ContractCreateRequest {
  number: string; // 1–50 символов; "HOD-2025-001"
  start_date: string; // "2025-01-01"
  end_date?: string | null; // null = бессрочный
  credit_limit?: number; // ≥ 0; default 0 (безлимитный)
  payment_due_days?: number; // > 0, ≤ 365; default 30
  legal_name: string; // 1–255 символов
  inn: string; // 9–14 символов
  legal_address?: string | null; // ≤ 500 символов
  bank_account_number?: string | null; // ≤ 25 символов
  bank_name?: string | null; // ≤ 255 символов
  notes?: string | null; // ≤ 2000 символов
}

/** Обновление договора (partial) */
interface ContractUpdateRequest {
  credit_limit?: number; // ≥ 0
  payment_due_days?: number; // > 0, ≤ 365
  end_date?: string | null;
  legal_address?: string | null;
  bank_account_number?: string | null;
  bank_name?: string | null;
  notes?: string | null;
}

/** Приостановка договора */
interface ContractSuspendRequest {
  reason: string; // 3–512 символов
}

/** Расторжение договора */
interface ContractTerminateRequest {
  reason: string; // 3–512 символов
}

/** Установка договорной цены */
interface PriceItemCreateRequest {
  price: number; // ≥ 0,
}

/** Генерация счёта-фактуры */
interface InvoiceGenerateRequest {
  period_from: string; // ISO date
  period_to: string; // ISO date; must be > period_from
}

/** Создание доп. соглашения */
interface AmendmentCreateRequest {
  number: string; // 1–50 символов; "ДС-001"
  description: string; // 3–2000 символов
  effective_date: string; // ISO date
}

/** Отмена заказа (клиент или бэкофис). NEW v3.0 */
interface CancelOrderRequest {
  reason?: string | null; // ≤ 500 символов; опциональная причина
}
```

### 18.4 Типы ошибок

```typescript
/** Стандартный формат ошибки API */
interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}
```

## 19. Backoffice API — Endpoints

### 19.1 Создание договора

```
POST /api/v1/backoffice/contracts/?clientId={uuid}
```

| Параметр   | Тип  | Расположение | Обязательный | Описание         |
| ---------- | ---- | ------------ | :----------: | ---------------- |
| `clientId` | UUID | Query        |      ✅      | ID клиента (B2B) |

**Scope:** `contracts:write`

**Request Body:** `ContractCreateRequest`

**Валидация полей:**

| Поле                  | Тип            | Ограничения               | Default |
| --------------------- | -------------- | ------------------------- | ------- |
| `number`              | string         | `min: 1`, `max: 50`       | —       |
| `start_date`          | date           | ISO format                | —       |
| `end_date`            | date \| null   | `> start_date` если задан | null    |
| `credit_limit`        | integer        | `≥ 0`                     | 0       |
| `payment_due_days`    | integer        | `> 0`, `≤ 365`            | 30      |
| `legal_name`          | string         | `min: 1`, `max: 255`      | —       |
| `inn`                 | string         | `min: 9`, `max: 14`       | —       |
| `legal_address`       | string \| null | `max: 500`                | null    |
| `bank_account_number` | string \| null | `max: 25`                 | null    |
| `bank_name`           | string \| null | `max: 255`                | null    |
| `notes`               | string \| null | `max: 2000`               | null    |

**Пример запроса:**

```http
POST /api/v1/backoffice/contracts/?clientId=01961a2b-3c4d-7000-8000-000000000001
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "number": "HOD-2025-001",
  "start_date": "2025-04-01",
  "end_date": "2026-03-31",
  "credit_limit": 5000000,
  "payment_due_days": 30,
  "legal_name": "ООО «Акватория»",
  "inn": "123456789",
  "legal_address": "г. Ташкент, ул. Навои, 42",
  "bank_account_number": "20208000123456789012",
  "bank_name": "НБУ",
  "notes": "VIP-клиент, приоритетная доставка"
}
```

**Пример ответа — 201 Created:**

```json
{
  "id": "01961a2b-4e5f-7001-8000-000000000002",
  "client_id": "01961a2b-3c4d-7000-8000-000000000001",
  "number": "HOD-2025-001",
  "status": "draft",
  "start_date": "2025-04-01",
  "end_date": "2026-03-31",
  "credit_limit": 5000000,
  "credit_used": 0,
  "payment_due_days": 30,
  "legal_name": "ООО «Акватория»",
  "inn": "123456789",
  "legal_address": "г. Ташкент, ул. Навои, 42",
  "bank_account_number": "20208000123456789012",
  "bank_name": "НБУ",
  "notes": "VIP-клиент, приоритетная доставка",
  "signed_at": null,
  "signed_by_id": null,
  "suspended_at": null,
  "suspension_reason": null,
  "terminated_at": null,
  "termination_reason": null,
  "is_active": true,
  "created_at": "2025-04-01T10:00:00.000000+00:00",
  "updated_at": "2025-04-01T10:00:00.000000+00:00"
}
```

**Ошибки:**

| HTTP | Код                       | Ситуация                                |
| ---- | ------------------------- | --------------------------------------- |
| 409  | `CONTRACT_ALREADY_ACTIVE` | У клиента уже есть ACTIVE договор       |
| 409  | `CONFLICT`                | Договор с таким `number` уже существует |
| 422  | Validation Error          | Невалидные поля                         |

---

### 19.2 Список договоров

```
GET /api/v1/backoffice/contracts/?skip=0&limit=50&clientId={uuid}&status={status}
```

| Параметр   | Тип            | Обязательный | Default | Описание                |
| ---------- | -------------- | :----------: | ------- | ----------------------- |
| `skip`     | integer        |      ❌      | 0       | Смещение (≥ 0)          |
| `limit`    | integer        |      ❌      | 50      | Размер страницы (1–100) |
| `clientId` | UUID \| null   |      ❌      | null    | Фильтр по клиенту       |
| `status`   | ContractStatus |      ❌      | null    | Фильтр по статусу       |

**Scope:** `contracts:read`

**Ответ — 200:** `ContractResponse[]`

**Пример запроса:**

```http
GET /api/v1/backoffice/contracts/?status=active&limit=10
Authorization: Bearer eyJhbGci...
```

**Пример ответа:**

```json
[
  {
    "id": "01961a2b-4e5f-7001-8000-000000000002",
    "client_id": "01961a2b-3c4d-7000-8000-000000000001",
    "number": "HOD-2025-001",
    "status": "active",
    "start_date": "2025-04-01",
    "end_date": "2026-03-31",
    "credit_limit": 5000000,
    "credit_used": 1250000,
    "payment_due_days": 30,
    "legal_name": "ООО «Акватория»",
    "inn": "123456789",
    "legal_address": "г. Ташкент, ул. Навои, 42",
    "bank_account_number": "20208000123456789012",
    "bank_name": "НБУ",
    "notes": "VIP-клиент",
    "signed_at": "2025-04-01T12:00:00+00:00",
    "signed_by_id": "01961a2b-1111-7000-8000-000000000099",
    "suspended_at": null,
    "suspension_reason": null,
    "terminated_at": null,
    "termination_reason": null,
    "is_active": true,
    "created_at": "2025-04-01T10:00:00+00:00",
    "updated_at": "2025-04-01T12:00:00+00:00"
  }
]
```

---

### 19.3 Детали договора

```
GET /api/v1/backoffice/contracts/{contract_id}
```

**Scope:** `contracts:read`

**Ответ — 200:** `ContractDetailResponse` (включает `price_items[]`)

**Пример ответа:**

```json
{
  "id": "01961a2b-4e5f-7001-8000-000000000002",
  "client_id": "01961a2b-3c4d-7000-8000-000000000001",
  "number": "HOD-2025-001",
  "status": "active",
  "start_date": "2025-04-01",
  "end_date": "2026-03-31",
  "credit_limit": 5000000,
  "credit_used": 1250000,
  "payment_due_days": 30,
  "legal_name": "ООО «Акватория»",
  "inn": "123456789",
  "legal_address": "г. Ташкент, ул. Навои, 42",
  "bank_account_number": "20208000123456789012",
  "bank_name": "НБУ",
  "notes": null,
  "signed_at": "2025-04-01T12:00:00+00:00",
  "signed_by_id": "01961a2b-1111-7000-8000-000000000099",
  "suspended_at": null,
  "suspension_reason": null,
  "terminated_at": null,
  "termination_reason": null,
  "is_active": true,
  "created_at": "2025-04-01T10:00:00+00:00",
  "updated_at": "2025-04-01T12:00:00+00:00",
  "price_items": [
    {
      "id": "01961a2b-5555-7001-8000-000000000010",
      "contract_id": "01961a2b-4e5f-7001-8000-000000000002",
      "product_id": "01961a2b-6666-7001-8000-000000000020",
      "price": 1200000,
      "is_active": true,
      "created_at": "2025-04-02T09:00:00+00:00",
      "updated_at": "2025-04-02T09:00:00+00:00"
    }
  ]
}
```

**Ошибки:**

| HTTP | Код                  | Ситуация          |
| ---- | -------------------- | ----------------- |
| 404  | `CONTRACT_NOT_FOUND` | Договор не найден |

---

### 19.4 Обновление условий договора

```
PATCH /api/v1/backoffice/contracts/{contract_id}
```

**Scope:** `contracts:write`

**Request Body:** `ContractUpdateRequest` (partial — только переданные поля обновляются)

**Валидация полей:**

| Поле                  | Ограничения                                    |
| --------------------- | ---------------------------------------------- |
| `credit_limit`        | `≥ 0`; не может быть `< credit_used` (при > 0) |
| `payment_due_days`    | `> 0`, `≤ 365`                                 |
| `end_date`            | `> start_date` если задан                      |
| `legal_address`       | `max: 500`                                     |
| `bank_account_number` | `max: 25`                                      |
| `bank_name`           | `max: 255`                                     |
| `notes`               | `max: 2000`                                    |

**Пример запроса:**

```http
PATCH /api/v1/backoffice/contracts/01961a2b-4e5f-7001-8000-000000000002
Authorization: Bearer eyJhbGci...
Content-Type: application/json

{
  "credit_limit": 10000000,
  "notes": "Лимит увеличен по запросу менеджера"
}
```

**Ответ — 200:** `ContractResponse`

**Ошибки:**

| HTTP | Код                       | Ситуация                                    |
| ---- | ------------------------- | ------------------------------------------- |
| 400  | `CREDIT_LIMIT_BELOW_USED` | `new_limit > 0` и `new_limit < credit_used` |
| 404  | `CONTRACT_NOT_FOUND`      | Договор не найден                           |

---

### 19.5 Активация договора

```
POST /api/v1/backoffice/contracts/{contract_id}/activate
```

**Scope:** `contracts:manage`

**Request Body:** нет

**Ответ — 200:** `ContractResponse` с `status: "active"`

**Побочные эффекты:**

- `signed_at` ← текущее время (UTC)
- `signed_by_id` ← `current_user.id`
- Запись в `contract_status_logs`: `{from: "draft", to: "active"}`

**Ошибки:**

| HTTP | Код                                | Ситуация                                 |
| ---- | ---------------------------------- | ---------------------------------------- |
| 404  | `CONTRACT_NOT_FOUND`               | Договор не найден                        |
| 409  | `CONTRACT_STATUS_TRANSITION_ERROR` | Текущий статус ≠ `draft`                 |
| 409  | `CONTRACT_ALREADY_ACTIVE`          | У клиента уже есть другой ACTIVE договор |

---

### 19.6 Приостановка договора

```
POST /api/v1/backoffice/contracts/{contract_id}/suspend
```

**Scope:** `contracts:manage`

**Request Body:**

```json
{
  "reason": "Просрочка платежа более 60 дней"
}
```

| Поле     | Тип    | Ограничения    | Обязательный |
| -------- | ------ | -------------- | :----------: |
| `reason` | string | 3–512 символов |      ✅      |

**Ответ — 200:** `ContractResponse` с `status: "suspended"`

**Побочные эффекты:**

- `suspended_at` ← текущее время (UTC)
- `suspension_reason` ← переданный `reason`
- Запись в `contract_status_logs`
- **NEW v3.0:** Автоматическая отмена in-flight заказов (NEW/ASSIGNED → CANCELLED)
  - Каждый заказ получает `cancellation_reason: "Договор приостановлен"`
  - Создаётся `OrderStatusLog` для каждого отменённого заказа
  - `credit_used` уменьшается на `reserved_credit_amount` каждого заказа

**Ошибки:**

| HTTP | Код                                | Ситуация                  |
| ---- | ---------------------------------- | ------------------------- |
| 404  | `CONTRACT_NOT_FOUND`               | Договор не найден         |
| 409  | `CONTRACT_STATUS_TRANSITION_ERROR` | Текущий статус ≠ `active` |

---

### 19.7 Восстановление договора

```
POST /api/v1/backoffice/contracts/{contract_id}/reinstate
```

**Scope:** `contracts:manage`

**Request Body:** нет

**Ответ — 200:** `ContractResponse` с `status: "active"`

**Побочные эффекты:**

- `suspended_at` ← null
- `suspension_reason` ← null
- Запись в `contract_status_logs`

**Ошибки:**

| HTTP | Код                                | Ситуация                                 |
| ---- | ---------------------------------- | ---------------------------------------- |
| 404  | `CONTRACT_NOT_FOUND`               | Договор не найден                        |
| 409  | `CONTRACT_STATUS_TRANSITION_ERROR` | Текущий статус ≠ `suspended`             |
| 409  | `CONTRACT_ALREADY_ACTIVE`          | У клиента уже есть другой ACTIVE договор |

---

### 19.8 Расторжение договора

```
POST /api/v1/backoffice/contracts/{contract_id}/terminate
```

**Scope:** `contracts:manage`

**Request Body:**

```json
{
  "reason": "Систематическое нарушение условий поставки"
}
```

| Поле     | Тип    | Ограничения    | Обязательный |
| -------- | ------ | -------------- | :----------: |
| `reason` | string | 3–512 символов |      ✅      |

**Ответ — 200:** `ContractResponse` с `status: "terminated"`

**Побочные эффекты:**

- `terminated_at` ← текущее время (UTC)
- `termination_reason` ← переданный `reason`
- Запись в `contract_status_logs`
- **NEW v3.0:** Автоматическая отмена in-flight заказов (NEW/ASSIGNED → CANCELLED)
  - Каждый заказ получает `cancellation_reason: "Договор расторгнут"`
  - Создаётся `OrderStatusLog` для каждого отменённого заказа
  - `credit_used` уменьшается на `reserved_credit_amount` каждого заказа

**Ошибки:**

| HTTP | Код                                | Ситуация                                 |
| ---- | ---------------------------------- | ---------------------------------------- |
| 404  | `CONTRACT_NOT_FOUND`               | Договор не найден                        |
| 409  | `CONTRACT_STATUS_TRANSITION_ERROR` | Текущий статус ∉ {`active`, `suspended`} |

---

### 19.9 Прайс-лист договора

```
GET /api/v1/backoffice/contracts/{contract_id}/prices
```

**Scope:** `contracts:read`

**Ответ — 200:** `PriceItemResponse[]`

---

### 19.10 Установить / обновить цену

```
PUT /api/v1/backoffice/contracts/{contract_id}/prices/{product_id}
```

**Scope:** `contracts:write`

**Семантика:** Upsert — создаёт новую позицию или обновляет существующую.

**Request Body:**

```json
{
  "price": 1200000
}
```

| Поле    | Тип     | Ограничения | Описание |
| ------- | ------- | ----------- | -------- |
| `price` | integer | `≥ 0`       | Цена     |

**Ответ — 200:** `PriceItemResponse`

---

### 19.11 Удалить цену

```
DELETE /api/v1/backoffice/contracts/{contract_id}/prices/{product_id}
```

**Scope:** `contracts:write`

**Ответ — 204:** Без тела

> После удаления для данного товара будет использоваться каталожная цена.

**Ошибки:**

| HTTP | Код                             | Ситуация                       |
| ---- | ------------------------------- | ------------------------------ |
| 404  | `CONTRACT_PRICE_ITEM_NOT_FOUND` | Позиция прайс-листа не найдена |

---

### 19.12 Заказы по договору

```
GET /api/v1/backoffice/contracts/{contract_id}/orders?skip=0&limit=50
```

**Scope:** `contracts:read`

| Параметр | Тип     | Default | Ограничения |
| -------- | ------- | ------- | ----------- |
| `skip`   | integer | 0       | `≥ 0`       |
| `limit`  | integer | 50      | `1–100`     |

**Ответ — 200:** `OrderResponse[]`

> **Примечание v3.0:** `OrderResponse` теперь включает поля `contract_id`,
> `reserved_credit_amount`, `notes` и `cancellation_reason`.

---

### 19.13 Генерация счёта-фактуры

```
POST /api/v1/backoffice/contracts/{contract_id}/invoices
```

**Scope:** `contracts:manage`

**Request Body:**

```json
{
  "period_from": "2025-03-01",
  "period_to": "2025-03-31"
}
```

| Поле          | Тип  | Ограничения     |
| ------------- | ---- | --------------- |
| `period_from` | date | ISO format      |
| `period_to`   | date | `> period_from` |

**Ответ — 201:** `InvoiceResponse` в статусе `draft`

**Бизнес-логика:**

1. Подсчёт суммы DELIVERED заказов за период → `amount`
2. `due_date = period_to + payment_due_days`
3. `number = "{contract.number}/{YYYY}-{MM}-{seq:03d}"`

**Пример ответа:**

```json
{
  "id": "01961a2b-7777-7001-8000-000000000030",
  "contract_id": "01961a2b-4e5f-7001-8000-000000000002",
  "number": "HOD-2025-001/2025-03-001",
  "status": "draft",
  "period_from": "2025-03-01",
  "period_to": "2025-03-31",
  "amount": 3600000,
  "due_date": "2025-04-30",
  "issued_at": null,
  "paid_at": null,
  "created_at": "2025-04-01T10:00:00+00:00",
  "updated_at": "2025-04-01T10:00:00+00:00"
}
```

**Ошибки:**

| HTTP | Код                        | Ситуация                                    |
| ---- | -------------------------- | ------------------------------------------- |
| 404  | `CONTRACT_NOT_FOUND`       | Договор не найден                           |
| 409  | `DUPLICATE_INVOICE_PERIOD` | Не-CANCELLED инвойс за этот период уже есть |

---

### 19.14 Список счетов-фактур

```
GET /api/v1/backoffice/contracts/{contract_id}/invoices
```

**Scope:** `contracts:read`

**Ответ — 200:** `InvoiceResponse[]`

---

### 19.15 Получить счёт-фактуру

```
GET /api/v1/backoffice/contracts/{contract_id}/invoices/{invoice_id}
```

**Scope:** `contracts:read`

**Ответ — 200:** `InvoiceResponse`

**Ошибки:**

| HTTP | Код                 | Ситуация                                             |
| ---- | ------------------- | ---------------------------------------------------- |
| 404  | `INVOICE_NOT_FOUND` | Инвойс не найден или не принадлежит данному договору |

---

### 19.16 Выставить счёт (DRAFT → ISSUED)

```
POST /api/v1/backoffice/contracts/{contract_id}/invoices/{invoice_id}/issue
```

**Scope:** `contracts:manage`

**Request Body:** нет

**Ответ — 200:** `InvoiceResponse` с `status: "issued"`

**Побочные эффекты:**

- `issued_at` ← текущее время (UTC)

**Ошибки:**

| HTTP | Код                          | Ситуация                 |
| ---- | ---------------------------- | ------------------------ |
| 404  | `INVOICE_NOT_FOUND`          | Инвойс не найден         |
| 409  | `INVALID_INVOICE_TRANSITION` | Текущий статус ≠ `draft` |

---

### 19.17 Отметить оплаченным (ISSUED/OVERDUE → PAID)

```
POST /api/v1/backoffice/contracts/{contract_id}/invoices/{invoice_id}/mark-paid
```

**Scope:** `contracts:manage`

**Request Body:** нет

**Ответ — 200:** `InvoiceResponse` с `status: "paid"`

**Побочные эффекты:**

- `paid_at` ← текущее время (UTC)

**Ошибки:**

| HTTP | Код                          | Ситуация                       |
| ---- | ---------------------------- | ------------------------------ |
| 404  | `INVOICE_NOT_FOUND`          | Инвойс не найден               |
| 409  | `INVALID_INVOICE_TRANSITION` | Статус ∉ {`issued`, `overdue`} |

---

### 19.18 Аннулировать счёт (DRAFT/ISSUED → CANCELLED)

```
DELETE /api/v1/backoffice/contracts/{contract_id}/invoices/{invoice_id}
```

**Scope:** `contracts:manage`

**Ответ — 200:** `InvoiceResponse` с `status: "cancelled"`

> ⚠️ HTTP-метод DELETE, но ответ **200 с телом** (не 204).
> Это логическое аннулирование, не физическое удаление.

**Ошибки:**

| HTTP | Код                          | Ситуация                     |
| ---- | ---------------------------- | ---------------------------- |
| 404  | `INVOICE_NOT_FOUND`          | Инвойс не найден             |
| 409  | `INVALID_INVOICE_TRANSITION` | Статус ∉ {`draft`, `issued`} |

---

### 19.19 Акт сверки

```
GET /api/v1/backoffice/contracts/{contract_id}/reconciliation?dateFrom=2025-03-01&dateTo=2025-03-31
```

**Scope:** `contracts:read`

| Параметр   | Тип  | Alias      | Обязательный |
| ---------- | ---- | ---------- | :----------: |
| `dateFrom` | date | `dateFrom` |      ✅      |
| `dateTo`   | date | `dateTo`   |      ✅      |

**Ответ — 200:** `ReconciliationResponse`

**Пример ответа:**

```json
{
  "contract_id": "01961a2b-4e5f-7001-8000-000000000002",
  "contract_number": "HOD-2025-001",
  "client_name": "ООО Акватория",
  "period_from": "2025-03-01",
  "period_to": "2025-03-31",
  "orders": [
    {
      "order_id": "01961a2b-8888-7001-8000-000000000040",
      "created_at": "2025-03-05T14:30:00+00:00",
      "total_amount": 1800000
    },
    {
      "order_id": "01961a2b-8888-7001-8000-000000000041",
      "created_at": "2025-03-15T09:00:00+00:00",
      "total_amount": 1800000
    }
  ],
  "total_billed": 3600000,
  "payments": [
    {
      "transaction_id": "01961a2b-9999-7001-8000-000000000050",
      "created_at": "2025-03-20T16:00:00+00:00",
      "amount": 2000000,
      "reason": "Частичная оплата по договору"
    }
  ],
  "total_paid": 2000000,
  "balance": 1600000
}
```

> `balance > 0` — клиент должен HOD. `balance < 0` — переплата.

---

### 19.20 История статусов

```
GET /api/v1/backoffice/contracts/{contract_id}/history
```

**Scope:** `contracts:read`

**Ответ — 200:** `ContractStatusLogResponse[]` (хронологически)

**Пример ответа:**

```json
[
  {
    "id": "01961a2b-aaaa-7001-8000-000000000060",
    "contract_id": "01961a2b-4e5f-7001-8000-000000000002",
    "from_status": null,
    "to_status": "draft",
    "changed_by_id": "01961a2b-1111-7000-8000-000000000099",
    "reason": null,
    "created_at": "2025-04-01T10:00:00+00:00"
  },
  {
    "id": "01961a2b-aaaa-7001-8000-000000000061",
    "contract_id": "01961a2b-4e5f-7001-8000-000000000002",
    "from_status": "draft",
    "to_status": "active",
    "changed_by_id": "01961a2b-1111-7000-8000-000000000099",
    "reason": null,
    "created_at": "2025-04-01T12:00:00+00:00"
  }
]
```

---

### 19.21 Создание доп. соглашения

```
POST /api/v1/backoffice/contracts/{contract_id}/amendments
```

**Scope:** `contracts:manage`

**Request Body:**

```json
{
  "number": "ДС-001",
  "description": "Увеличение кредитного лимита до 10 000 000",
  "effective_date": "2025-05-01"
}
```

| Поле             | Тип    | Ограничения     |
| ---------------- | ------ | --------------- |
| `number`         | string | 1–50 символов   |
| `description`    | string | 3–2000 символов |
| `effective_date` | date   | ISO format      |

**Ответ — 201:** `AmendmentResponse`

**Ошибки:**

| HTTP | Код                          | Ситуация                                       |
| ---- | ---------------------------- | ---------------------------------------------- |
| 404  | `CONTRACT_NOT_FOUND`         | Договор не найден                              |
| 409  | `DUPLICATE_AMENDMENT_NUMBER` | ДС с таким номером уже есть для этого договора |

---

### 19.22 Список доп. соглашений

```
GET /api/v1/backoffice/contracts/{contract_id}/amendments
```

**Scope:** `contracts:read`

**Ответ — 200:** `AmendmentResponse[]`

---

### 19.23 Job: пометить просроченные инвойсы

```
POST /api/v1/backoffice/contracts/jobs/mark-overdue
```

**Scope:** `contracts:manage`

**Request Body:** нет

**Ответ — 200:**

```json
{
  "updated": 3
}
```

> Переводит ISSUED инвойсы с `due_date < today` в OVERDUE. Идемпотентен.

---

### 19.24 Job: истечение договоров

```
POST /api/v1/backoffice/contracts/jobs/expire-contracts
```

**Scope:** `contracts:manage`

**Request Body:** нет

**Ответ — 200:**

```json
{
  "updated": 1
}
```

> Переводит ACTIVE договоры с `end_date < today` в EXPIRED.
> Логирует каждый переход в аудит-лог. Идемпотентен.
>
> **NEW v3.0:** Автоматически отменяет все in-flight заказы (NEW/ASSIGNED)
> по каждому истёкшему договору. Каждый заказ получает
> `cancellation_reason: "Договор истёк"` и запись в `OrderStatusLog`.
> `credit_used` уменьшается на сумму `reserved_credit_amount`.

---

### 19.25 Job: очистка устаревших заказов (NEW v3.0)

```
POST /api/v1/backoffice/orders/jobs/expire-stale
```

**Scope:** `orders:edit`

| Параметр              | Тип     | Default | Описание                              |
| --------------------- | ------- | ------- | ------------------------------------- |
| `maxAgeHours`         | integer | 48      | Макс. возраст NEW заказов (часы)      |
| `assignedMaxAgeHours` | integer | 72      | Макс. возраст ASSIGNED заказов (часы) |

**Ответ — 200:**

```json
{
  "cancelled": 5,
  "details": "Отменено NEW: 3, ASSIGNED: 2"
}
```

**Бизнес-логика:**

- **NEW** заказы: отменяются если `created_at < now() - maxAgeHours`
- **ASSIGNED** заказы: отменяются если `updated_at < now() - assignedMaxAgeHours`
  (используется `updated_at`, чтобы не отменять недавно назначенные заказы)
- Кредит по CONTRACT-заказам возвращается
- Каждый заказ получает `cancellation_reason` и `OrderStatusLog`

---

### 19.26 Дебиторка B2B по договорам (NEW v3.2)

```
GET /api/v1/backoffice/finances/b2b-debts
```

**Scope:** `contracts:read`

**Параметры:** нет (возвращает все активные договоры)

**Ответ — 200:** `B2BContractDebtsResponse`

```json
{
  "items": [
    {
      "client_id": "...",
      "client_name": "ООО «Акватех»",
      "contract_id": "...",
      "contract_number": "HOD-2025-001",
      "credit_limit": 5000000,
      "credit_used": 3200000,
      "account_balance": -1500000,
      "total_exposure": 4700000,
      "limit_utilization_pct": 0.64,
      "due_date_status": "ok"
    }
  ],
  "total_exposure": 4700000
}
```

**Поля `B2BContractDebt`:**

| Поле                    | Тип    | Описание                                          |
| ----------------------- | ------ | ------------------------------------------------- |
| `credit_limit`          | int    | Кредитный лимит (0 = безлимитный)                 |
| `credit_used`           | int    | In-flight кредит (зарезервированный заказами)     |
| `account_balance`       | int    | Баланс финансового счёта (< 0 = задолженность)    |
| `total_exposure`        | int    | `credit_used + |account_balance|`                 |
| `limit_utilization_pct` | float  | 0.0–1.0 (для шкалы в UI)                         |
| `due_date_status`       | string | `ok` / `overdue` / `no_limit`                     |

**UI-рекомендации:**

- Цветовая индикация: `ok` → зелёный, `overdue` → красный, `no_limit` → серый
- Шкала утилизации: `limit_utilization_pct × 100%`
- Итого: отображать `total_exposure` из корня ответа

---

### 19.27 Поиск инвентарей (NEW v3.2)

```
GET /api/v1/backoffice/inventories/search
```

**Scope:** `inventory:read`

**Параметры:**

| Параметр | Тип           | Default | Описание                                         |
| -------- | ------------- | ------- | ------------------------------------------------ |
| `q`      | string        | `""`    | Поисковый запрос по названию                     |
| `type`   | InventoryType | —       | Фильтр по типу (CLIENT, WAREHOUSE, COURIER, …) |
| `limit`  | integer       | 50      | Макс. результатов (1–200)                        |

**Ответ — 200:** `InventorySearchResult[]`

```json
[
  {
    "id": "...",
    "name": "Клиент: ООО «Акватех»",
    "type": "CLIENT",
    "user_id": "..."
  }
]
```

**Использование:** Autocomplete / поиск при выборе инвентаря
(например, при ручном создании накладной).

---

### 19.28 Фильтры журнала накладных (NEW v3.2)

```
GET /api/v1/backoffice/transfers/
```

**Scope:** `logistics:transfer`

**Новые параметры (добавлены к существующим `page`, `size`):**

| Параметр       | Тип           | Default | Описание                         |
| -------------- | ------------- | ------- | -------------------------------- |
| `type`         | TransferType  | —       | Фильтр по типу накладной        |
| `from_date`    | date          | —       | Начальная дата (включительно)    |
| `to_date`      | date          | —       | Конечная дата (включительно)     |
| `warehouse_id` | UUID          | —       | Склад (from или to)             |

---

## 20. Client B2B API — Endpoints

> Все клиентские эндпоинты **IDOR-safe**: ID договора не передаётся
> в URL — сервер определяет его из `current_user.id`.

### 20.1 Мой активный договор

```
GET /api/v1/client/contracts/my-contract
```

**Scope:** `contracts:read`

**Ответ — 200:** `ContractDetailResponse`

**Ошибки:**

| HTTP | Код                 | Ситуация                         |
| ---- | ------------------- | -------------------------------- |
| 403  | `CONTRACT_REQUIRED` | У клиента нет активного договора |

---

### 20.2 Мой прайс-лист

```
GET /api/v1/client/contracts/my-contract/prices
```

**Scope:** `contracts:read`

**Ответ — 200:** `PriceItemResponse[]`

**Ошибки:**

| HTTP | Код                 | Ситуация                         |
| ---- | ------------------- | -------------------------------- |
| 403  | `CONTRACT_REQUIRED` | У клиента нет активного договора |

---

### 20.3 Мои счета-фактуры

```
GET /api/v1/client/contracts/my-contract/invoices
```

**Scope:** `contracts:read`

**Ответ — 200:** `InvoiceResponse[]`

**Ошибки:**

| HTTP | Код                 | Ситуация                         |
| ---- | ------------------- | -------------------------------- |
| 403  | `CONTRACT_REQUIRED` | У клиента нет активного договора |

---

### 20.4 Мой счёт-фактура по ID

```
GET /api/v1/client/contracts/my-contract/invoices/{invoice_id}
```

**Scope:** `contracts:read`

**Ответ — 200:** `InvoiceResponse`

**Ошибки:**

| HTTP | Код                 | Ситуация                                             |
| ---- | ------------------- | ---------------------------------------------------- |
| 403  | `CONTRACT_REQUIRED` | У клиента нет активного договора                     |
| 404  | `INVOICE_NOT_FOUND` | Инвойс не найден или не принадлежит договору клиента |

---

### 20.5 Моя история заказов (NEW v3.0)

```
GET /api/v1/client/orders/history?skip=0&limit=20&status=delivered
```

**Scope:** `orders:read`

| Параметр | Тип         | Default | Ограничения  | Описание          |
| -------- | ----------- | ------- | ------------ | ----------------- |
| `skip`   | integer     | 0       | `≥ 0`        | Смещение          |
| `limit`  | integer     | 20      | `1–100`      | Размер страницы   |
| `status` | OrderStatus | null    | опциональный | Фильтр по статусу |

**Ответ — 200:** `OrdersResponse`

```json
{
  "total_count": 42,
  "orders": [
    {
      "id": "019...",
      "status": "delivered",
      "payment_method": "contract",
      "total_amount": 1800000,
      "contract_id": "019...",
      "reserved_credit_amount": 1800000,
      "notes": "3 этаж, код 4512",
      "cancellation_reason": null,
      "items": [...],
      "created_at": "2025-04-01T10:00:00+00:00",
      "updated_at": "2025-04-01T14:30:00+00:00"
    }
  ]
}
```

> **⚠️ BREAKING:** Ответ изменился с `OrderResponse[]` на `OrdersResponse`.
> Используйте `response.orders` вместо прямого массива.
> Поле `total_count` позволяет реализовать правильную пагинацию.

> **IDOR-safe:** Сервер фильтрует заказы по `current_user.id` автоматически.

---

### 20.6 Отмена заказа клиентом (NEW v3.0)

```
POST /api/v1/client/orders/{order_id}/cancel
```

**Scope:** `orders:cancel`

**Request Body:** `CancelOrderRequest` (опциональный)

```json
{
  "reason": "Передумал, заказ больше не нужен"
}
```

| Поле     | Тип            | Ограничения    | Обязательный |
| -------- | -------------- | -------------- | :----------: |
| `reason` | string \| null | ≤ 500 символов |      ❌      |

**Ответ — 200:** `OrderResponse` с `status: "cancelled"`

**Бизнес-логика:**

- Только заказы в статусе `NEW` или `ASSIGNED` могут быть отменены клиентом
- `cancellation_reason` записывается в заказ
- Для CONTRACT-заказов: `credit_used` уменьшается на `reserved_credit_amount`
- Создаётся запись `OrderStatusLog`
- IDOR-safe: сервер проверяет, что заказ принадлежит `current_user`

**Ошибки:**

| HTTP | Код                        | Ситуация                     |
| ---- | -------------------------- | ---------------------------- |
| 404  | `ORDER_NOT_FOUND`          | Заказ не найден или чужой    |
| 409  | `ORDER_CANCEL_NOT_ALLOWED` | Статус ∉ {`new`, `assigned`} |

---

### 20.7 Баланс тары клиента (NEW v3.0)

```
GET /api/v1/client/inventory/balance
```

**Scope:** `catalog:read`

**Ответ — 200:** `BalanceResponse[]`

```json
[
  {
    "product": {
      "id": "019...",
      "name": "Бутыль 19л",
      "sku": "BOTTLE-19L",
      "type": "tara",
      "price": 0
    },
    "quantity": 5
  }
]
```

> Показывает остатки тары на всех адресах клиента. Отрицательное значение
> `quantity` означает тарный долг (клиент должен вернуть бутыли).

---

### 20.8 Остатки в машине курьера (NEW v3.0)

```
GET /api/v1/courier/inventory/my-stock
```

**Scope:** `catalog:read` (через `get_current_courier`)

**Ответ — 200:** `BalanceResponse[]`

> Показывает текущие остатки товаров в машине курьера. Только ненулевые позиции.

---

### 20.9 Платформенные изменения API (NEW v3.2)

> Ниже перечислены изменения API за пределами модуля Contracts,
> затрагивающие frontend-интеграцию.

#### 20.9.1 Авторизация клиента — BREAKING

```
POST /api/v1/client/login
```

**Было:** `phone` передавался как query-параметр.

**Стало:** JSON body `LocalLogin`:

```json
{ "phone": "+998901234567", "password": "client_password" }
```

**Ответ — 200:** `TokenResponse` `{ access_token, token_type }`

#### 20.9.2 Health Check — BREAKING

```
GET /health
```

**Было:** `{"status": "ok", "environment": "dev"}`

**Стало:**
- 200 — `{"status": "ok"}` (поле `environment` удалено)
- 503 — `{"status": "db_unavailable"}` (БД недоступна)

#### 20.9.3 Shifts — роутер удалён

Эндпоинт `POST /backoffice/shifts/close` и связанные схемы
(`CloseShiftRequest`, `ShiftReconciliationResponse`) **полностью удалены**.
Если frontend использовал этот эндпоинт — удалите интеграцию.

#### 20.9.4 Обновление пользователя — новые валидации

`PATCH /backoffice/users/{user_id}` теперь проверяет:

| Проверка           | Ошибка                         | HTTP |
| ------------------ | ------------------------------ | ---- |
| Self-edit          | `SELF_MODIFICATION_FORBIDDEN`  | 400  |
| Назначение SYSTEM  | `SYSTEM_ROLE_FORBIDDEN`        | 403  |

#### 20.9.5 Создание курьера — пароль

`CourierCreate.password` теперь требует `min_length=8`.
Frontend должен валидировать длину пароля ≥ 8 символов.

#### 20.9.6 Создание заказа — ответ

`POST /backoffice/orders/` теперь возвращает `OrderResponse` (201).
Ранее эндпоинт не возвращал тело ответа.

---

## 21. Каталог ошибок (Error Code Catalog)

| Код ошибки                         | HTTP | Триггер                                             | Ключи `details`                                                              |
| ---------------------------------- | ---- | --------------------------------------------------- | ---------------------------------------------------------------------------- |
| `CONTRACT_NOT_FOUND`               | 404  | GET/PATCH/POST по несуществующему `contract_id`     | `contract_id`                                                                |
| `CONTRACT_NOT_ACTIVE`              | 400  | Создание заказа при `status ≠ active`               | `contract_id`, `status`                                                      |
| `CONTRACT_EXPIRED`                 | 400  | Создание заказа при истёкшем `end_date`             | `contract_id`                                                                |
| `CREDIT_LIMIT_EXCEEDED`            | 400  | `credit_used + amount > credit_limit` (при limit>0) | `contract_id`, `credit_limit`, `current_exposure`, `order_amount`, `overage` |
| `CONTRACT_ALREADY_ACTIVE`          | 409  | Активация/восстановление при существующем ACTIVE    | `client_id`, `existing_contract_id`                                          |
| `CONTRACT_STATUS_TRANSITION_ERROR` | 409  | Недопустимый переход статуса                        | `contract_id`, `current_status`, `target_status`                             |
| `CONTRACT_REQUIRED`                | 403  | B2B-клиент без активного договора                   | `client_id`                                                                  |
| `CONTRACT_PRICE_ITEM_NOT_FOUND`    | 404  | DELETE несуществующей позиции прайс-листа           | `contract_id`, `product_id`                                                  |
| `CONTRACT_ACCESS_DENIED`           | 403  | IDOR: клиент обращается к чужому договору           | `client_id`, `contract_id`                                                   |
| `INVOICE_NOT_FOUND`                | 404  | GET/POST по несуществующему `invoice_id`            | `invoice_id`                                                                 |
| `INVALID_INVOICE_TRANSITION`       | 409  | Недопустимый переход статуса инвойса                | `invoice_id`, `current_status`, `expected_statuses`                          |
| `DUPLICATE_INVOICE_PERIOD`         | 409  | Генерация инвойса за период с активным инвойсом     | `contract_id`, `period_from`, `period_to`                                    |
| `DUPLICATE_AMENDMENT_NUMBER`       | 409  | Создание ДС с дублирующимся номером                 | `contract_id`, `number`                                                      |
| `CREDIT_LIMIT_BELOW_USED`          | 400  | Уменьшение `credit_limit` ниже `credit_used`        | `new_limit`, `credit_used`                                                   |
| `ORDER_NOT_FOUND`                  | 404  | Заказ не найден или не принадлежит пользователю     | `order_id`                                                                   |
| `ORDER_CANCEL_NOT_ALLOWED`         | 409  | Отмена невозможна (статус ≠ new/assigned)           | `order_id`, `current_status`                                                 |
| `SELF_MODIFICATION_FORBIDDEN`      | 400  | Попытка изменить собственный аккаунт                | —                                                                            |
| `SYSTEM_ROLE_FORBIDDEN`            | 403  | Попытка назначить роль SYSTEM через API             | —                                                                            |
| `SEEDER_DISABLED_IN_PROD`          | 403  | Вызов `POST /system/seed` в production              | —                                                                            |

---

## 22. Руководство по реализации UI

### 22.2 Конфигурация бейджей статуса договора

```typescript
interface StatusBadgeConfig {
  label: string;
  color: "gray" | "green" | "orange" | "red" | "blue";
  icon: string; // Имя иконки из UI-библиотеки
  actionable: boolean; // Показывать кнопки действий
}

const CONTRACT_STATUS_CONFIG: Record<ContractStatus, StatusBadgeConfig> = {
  [ContractStatus.DRAFT]: {
    label: "Черновик",
    color: "gray",
    icon: "FileEdit",
    actionable: true, // Кнопка "Активировать"
  },
  [ContractStatus.ACTIVE]: {
    label: "Активный",
    color: "green",
    icon: "CheckCircle",
    actionable: true, // Кнопки "Приостановить", "Расторгнуть"
  },
  [ContractStatus.SUSPENDED]: {
    label: "Приостановлен",
    color: "orange",
    icon: "PauseCircle",
    actionable: true, // Кнопки "Восстановить", "Расторгнуть"
  },
  [ContractStatus.TERMINATED]: {
    label: "Расторгнут",
    color: "red",
    icon: "XCircle",
    actionable: false,
  },
  [ContractStatus.EXPIRED]: {
    label: "Истёк",
    color: "blue",
    icon: "Clock",
    actionable: false,
  },
};
```

### 22.3 Конфигурация бейджей статуса инвойса

```typescript
const INVOICE_STATUS_CONFIG: Record<InvoiceStatus, StatusBadgeConfig> = {
  [InvoiceStatus.DRAFT]: {
    label: "Черновик",
    color: "gray",
    icon: "FileEdit",
    actionable: true, // "Выставить", "Аннулировать"
  },
  [InvoiceStatus.ISSUED]: {
    label: "Выставлен",
    color: "blue",
    icon: "Send",
    actionable: true, // "Оплачен", "Аннулировать"
  },
  [InvoiceStatus.PAID]: {
    label: "Оплачен",
    color: "green",
    icon: "CheckCircle",
    actionable: false,
  },
  [InvoiceStatus.OVERDUE]: {
    label: "Просрочен",
    color: "red",
    icon: "AlertTriangle",
    actionable: true, // "Оплачен"
  },
  [InvoiceStatus.CANCELLED]: {
    label: "Аннулирован",
    color: "gray",
    icon: "Slash",
    actionable: false,
  },
};
```

### 22.4 Компонент кредитной шкалы (Credit Bar)

```typescript
interface CreditBarProps {
  creditLimit: number; // 0 = безлимитный
  creditUsed: number;
}

function getCreditInfo(props: CreditBarProps) {
  const { creditLimit, creditUsed } = props;

  // Безлимитный договор
  if (creditLimit === 0) {
    return {
      isUnlimited: true,
      percentage: 0,
      available: Infinity,
      label: "Без ограничений",
      variant: "default" as const,
    };
  }

  const percentage = Math.round((creditUsed / creditLimit) * 100);
  const available = creditLimit - creditUsed;

  let variant: "success" | "warning" | "danger";
  if (percentage < 70) {
    variant = "success";
  } else if (percentage < 90) {
    variant = "warning";
  } else {
    variant = "danger";
  }

  return {
    isUnlimited: false,
    percentage,
    available,
    label: creditUsed / creditLimit,
    variant,
  };
}
```

### 22.5 Предварительная проверка кредита

```typescript
/**
 * Проверяет, может ли клиент оформить заказ на сумму amount.
 * Вызывается ДО отправки запроса на создание заказа.
 *
 * ⚠️ Это предварительная проверка на стороне клиента.
 * Финальная проверка — на сервере (SELECT FOR UPDATE).
 */
function canPlaceOrder(
  contract: ContractResponse,
  orderAmount: number,
): { allowed: boolean; reason?: string } {
  if (contract.status !== ContractStatus.ACTIVE) {
    return {
      allowed: false,
      reason: `Договор в статусе "${CONTRACT_STATUS_CONFIG[contract.status].label}". Заказы запрещены.`,
    };
  }

  if (contract.end_date && new Date(contract.end_date) < new Date()) {
    return {
      allowed: false,
      reason: "Срок действия договора истёк.",
    };
  }

  // Безлимитный
  if (contract.credit_limit === 0) {
    return { allowed: true };
  }

  const available = contract.credit_limit - contract.credit_used;
  if (orderAmount > available) {
    return {
      allowed: false,
      reason: `Сумма заказа (${orderAmount}) превышает доступный кредит (${available}).`,
    };
  }

  return { allowed: true };
}
```

### 22.6 Логика слияния цен

```typescript
/**
 * Определяет цену товара для B2B-клиента.
 * Приоритет: договорная цена → каталожная цена.
 */
function resolvePrice(
  productId: string,
  contractPrices: PriceItemResponse[],
  catalogPrice: number,
): { price: number; source: "contract" | "catalog" } {
  const contractPrice = contractPrices.find(
    (p) => p.product_id === productId && p.is_active,
  );
  if (contractPrice) {
    return { price: contractPrice.price, source: "contract" };
  }
  return { price: catalogPrice, source: "catalog" };
}
```

> **В UI:** выделяйте цены по договору (например, иконкой или бейджем
> «Договорная цена»), чтобы клиент видел разницу с каталожной ценой.

### 22.7 Стратегия пагинации

```typescript
// Backoffice: offset-based пагинация
interface PaginationParams {
  skip: number; // offset, ≥ 0
  limit: number; // page size, 1–100
}

// Рекомендуемые размеры страниц:
const PAGE_SIZES = {
  contracts: 20, // Список договоров
  orders: 25, // Заказы по договору
  invoices: 50, // Счета (обычно меньше)
  amendments: 50, // ДС (обычно мало)
};

// Пример загрузки с пагинацией:
async function loadContracts(page: number, pageSize = 20) {
  const skip = (page - 1) * pageSize;
  const response = await api.get("/backoffice/contracts/", {
    params: { skip, limit: pageSize },
  });
  return response.data;
}
```

> **Примечание v3.0:** Для заказов (`OrdersResponse`) API возвращает
> `total_count` — используйте его для пагинации. Для остальных сущностей
> (договоры, инвойсы, ДС) по-прежнему применяется правило
> `hasNextPage = items.length === limit`.

### 22.8 Форматирование дат

```typescript
/** Формат для отображения дат */
function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
  // "01.04.2025"
}

/** Формат для отображения даты и времени */
function formatDateTime(isoDatetime: string): string {
  return new Date(isoDatetime).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  // "01.04.2025, 15:30"
}

/** ISO дата для отправки на backend */
function toIsoDate(date: Date): string {
  return date.toISOString().split("T")[0];
  // "2025-04-01"
}
```

### 22.9 Scope-gated UI Elements

```typescript
/**
 * Проверяет наличие scope в JWT-токене.
 * Используйте для показа/скрытия кнопок и секций.
 */
function hasScope(userScopes: string[], required: string): boolean {
  return userScopes.includes(required);
}

// Пример использования в компоненте:
const canWrite = hasScope(user.scopes, "contracts:write");
const canManage = hasScope(user.scopes, "contracts:manage");
const canRead = hasScope(user.scopes, "contracts:read");

// Условный рендеринг:
// ✅ Показывать кнопку "Активировать" только при contracts:manage
// ✅ Показывать форму создания только при contracts:write
// ✅ Скрывать вкладку "Договоры" при отсутствии contracts:read
// ✅ NEW v3.0: Кнопка "Новый заказ" требует orders:create (не orders:edit!)
// ✅ NEW v3.0: Кнопка "Отменить заказ" требует orders:cancel

// Матрица видимости элементов UI:
const UI_VISIBILITY = {
  createContractButton: canWrite,
  editContractForm: canWrite,
  activateButton: canManage,
  suspendButton: canManage,
  reinstateButton: canManage,
  terminateButton: canManage,
  priceEditControls: canWrite,
  generateInvoiceButton: canManage,
  issueInvoiceButton: canManage,
  markPaidButton: canManage,
  cancelInvoiceButton: canManage,
  createAmendmentButton: canManage,
  runJobsSection: canManage,
  contractsList: canRead,
  contractDetail: canRead,
  reconciliationTab: canRead,
  historyTab: canRead,
};
```

### 22.10 Кнопки действий по состоянию договора

```typescript
interface ActionButton {
  label: string;
  action: string; // Идентификатор действия
  variant: "primary" | "warning" | "danger";
  confirmMessage: string;
  requiresInput?: "reason";
  scope: string; // Требуемый scope
}

function getContractActions(status: ContractStatus): ActionButton[] {
  switch (status) {
    case ContractStatus.DRAFT:
      return [
        {
          label: "Активировать",
          action: "activate",
          variant: "primary",
          confirmMessage:
            "Активировать договор? Это разрешит оформление заказов.",
          scope: "contracts:manage",
        },
      ];
    case ContractStatus.ACTIVE:
      return [
        {
          label: "Приостановить",
          action: "suspend",
          variant: "warning",
          confirmMessage:
            "Приостановить договор? Новые заказы будут заблокированы.",
          requiresInput: "reason",
          scope: "contracts:manage",
        },
        {
          label: "Расторгнуть",
          action: "terminate",
          variant: "danger",
          confirmMessage: "Расторгнуть договор? Это действие необратимо.",
          requiresInput: "reason",
          scope: "contracts:manage",
        },
      ];
    case ContractStatus.SUSPENDED:
      return [
        {
          label: "Восстановить",
          action: "reinstate",
          variant: "primary",
          confirmMessage: "Восстановить договор? Заказы снова будут разрешены.",
          scope: "contracts:manage",
        },
        {
          label: "Расторгнуть",
          action: "terminate",
          variant: "danger",
          confirmMessage: "Расторгнуть договор? Это действие необратимо.",
          requiresInput: "reason",
          scope: "contracts:manage",
        },
      ];
    case ContractStatus.TERMINATED:
    case ContractStatus.EXPIRED:
      return []; // Терминальные статусы — нет действий
  }
}
```

### 22.11 Кнопки действий по состоянию инвойса

```typescript
function getInvoiceActions(status: InvoiceStatus): ActionButton[] {
  switch (status) {
    case InvoiceStatus.DRAFT:
      return [
        {
          label: "Выставить",
          action: "issue",
          variant: "primary",
          confirmMessage: "Выставить счёт клиенту?",
          scope: "contracts:manage",
        },
        {
          label: "Аннулировать",
          action: "cancel",
          variant: "danger",
          confirmMessage: "Аннулировать черновик счёта?",
          scope: "contracts:manage",
        },
      ];
    case InvoiceStatus.ISSUED:
      return [
        {
          label: "Отметить оплаченным",
          action: "mark-paid",
          variant: "primary",
          confirmMessage: "Подтвердить оплату счёта?",
          scope: "contracts:manage",
        },
        {
          label: "Аннулировать",
          action: "cancel",
          variant: "danger",
          confirmMessage: "Аннулировать выставленный счёт?",
          scope: "contracts:manage",
        },
      ];
    case InvoiceStatus.OVERDUE:
      return [
        {
          label: "Отметить оплаченным",
          action: "mark-paid",
          variant: "primary",
          confirmMessage: "Подтвердить оплату просроченного счёта?",
          scope: "contracts:manage",
        },
      ];
    case InvoiceStatus.PAID:
    case InvoiceStatus.CANCELLED:
      return []; // Терминальные статусы
  }
}
```

---

## 23. Чек-лист тестирования Frontend

### 23.1 Договоры — CRUD

- [ ] Создание договора с минимальными полями (number, start_date, legal_name, inn)
- [ ] Создание договора со всеми полями включая optional
- [ ] Создание договора — ошибка 409 при существующем ACTIVE договоре
- [ ] Создание договора — ошибка 409 при дублировании `number`
- [ ] Создание договора — ошибка 422 при невалидных полях
- [ ] Список договоров без фильтров
- [ ] Список договоров с фильтром `status=active`
- [ ] Список договоров с фильтром `clientId`
- [ ] Список договоров с пагинацией (skip/limit)
- [ ] Пустой список — пагинация: `items.length < limit → hasNextPage = false`
- [ ] Детали договора — `price_items[]` присутствуют
- [ ] Обновление договора — partial update (только `credit_limit`)
- [ ] Обновление — ошибка 400 при `credit_limit < credit_used`

### 23.2 Жизненный цикл статусов

- [ ] DRAFT → ACTIVE (activate)
- [ ] ACTIVE → SUSPENDED (suspend с `reason`)
- [ ] SUSPENDED → ACTIVE (reinstate)
- [ ] ACTIVE → TERMINATED (terminate с `reason`)
- [ ] SUSPENDED → TERMINATED (terminate с `reason`)
- [ ] Ошибка: попытка активировать не-DRAFT
- [ ] Ошибка: попытка suspend не-ACTIVE
- [ ] Ошибка: попытка reinstate не-SUSPENDED
- [ ] Ошибка: попытка terminate DRAFT / TERMINATED / EXPIRED
- [ ] Ошибка: активация при существующем другом ACTIVE
- [ ] Ошибка: reinstate при существующем другом ACTIVE
- [ ] Кнопки действий соответствуют текущему статусу
- [ ] Терминальные статусы (TERMINATED, EXPIRED) — кнопки отсутствуют

### 23.3 Прайс-лист

- [ ] Получение прайс-листа (GET /prices)
- [ ] Создание новой позиции (PUT /prices/{product_id})
- [ ] Обновление существующей позиции (PUT — upsert)
- [ ] Удаление позиции (DELETE /prices/{product_id}) → 204
- [ ] Удаление — ошибка 404 для несуществующей позиции
- [ ] Цена отображается в UZS

### 23.4 Счета-фактуры

- [ ] Генерация инвойса с корректным периодом → 201
- [ ] Ошибка 409 при дубликате периода
- [ ] Список инвойсов по договору
- [ ] Получение инвойса по ID
- [ ] DRAFT → ISSUED (issue)
- [ ] ISSUED → PAID (mark-paid)
- [ ] OVERDUE → PAID (mark-paid)
- [ ] DRAFT → CANCELLED (cancel)
- [ ] ISSUED → CANCELLED (cancel)
- [ ] Ошибка: issue не-DRAFT
- [ ] Ошибка: mark-paid не-ISSUED и не-OVERDUE
- [ ] Ошибка: cancel PAID или OVERDUE
- [ ] `partially_paid` НЕ отображается в UI

### 23.5 Акт сверки

- [ ] Запрос с корректными `dateFrom`/`dateTo`
- [ ] Корректное отображение `orders[]` и `payments[]`
- [ ] `balance > 0` — клиент должен
- [ ] `balance < 0` — переплата
- [ ] `balance == 0` — взаиморасчёты закрыты
- [ ] Суммы отображаются в UZS без дробной части (целые числа, разделитель тысяч — пробел)

### 23.6 Кредитная шкала

- [ ] `credit_limit = 0` → отображение «Без ограничений»
- [ ] `credit_used / credit_limit < 70%` → зелёный
- [ ] `70% ≤ usage < 90%` → жёлтый/оранжевый
- [ ] `≥ 90%` → красный
- [ ] Корректный расчёт `available = limit - used`
- [ ] Предварительная проверка кредита при оформлении заказа

### 23.7 Клиентский портал (B2B)

- [ ] GET /my-contract — 200 при наличии ACTIVE договора
- [ ] GET /my-contract — 403 `CONTRACT_REQUIRED` при отсутствии
- [ ] GET /my-contract/prices — список договорных цен
- [ ] GET /my-contract/invoices — список счетов
- [ ] GET /my-contract/invoices/{id} — конкретный счёт
- [ ] IDOR: невозможно получить чужой договор/инвойс

### 23.8 Клиентские заказы (NEW v3.0)

- [ ] GET /client/orders/history — `OrdersResponse` с `total_count`
- [ ] GET /client/orders/history?status=delivered — фильтр по статусу
- [ ] GET /client/orders/history — пагинация (skip/limit)
- [ ] GET /client/orders/{id} — IDOR: нельзя получить чужой заказ
- [ ] POST /client/orders/{id}/cancel — отмена NEW заказа → 200
- [ ] POST /client/orders/{id}/cancel — отмена ASSIGNED заказа → 200
- [ ] POST /client/orders/{id}/cancel — отмена DELIVERED → 409
- [ ] POST /client/orders/{id}/cancel — `cancellation_reason` записывается
- [ ] POST /client/orders/{id}/cancel — credit_used уменьшается (CONTRACT)
- [ ] GET /client/inventory/balance — список тары с количеством
- [ ] Отрицательный `quantity` — тарный долг (визуальный индикатор)

### 23.9 Доп. соглашения

- [ ] Создание ДС → 201
- [ ] Ошибка 409 при дубликате номера
- [ ] Список ДС по договору (хронологически)

### 23.10 Jobs

- [ ] mark-overdue → `{updated: N}` (N ≥ 0)
- [ ] expire-contracts → `{updated: N}` (N ≥ 0)
- [ ] expire-contracts → in-flight заказы отменяются автоматически (NEW v3.0)
- [ ] expire-stale → `{cancelled: N}` с NEW и ASSIGNED заказами (NEW v3.0)
- [ ] Повторный вызов → `{updated: 0}` (идемпотентность)

### 23.11 Авторизация

- [ ] `contracts:read` — доступ к GET-эндпоинтам
- [ ] `contracts:write` — доступ к POST/PATCH/PUT/DELETE CRUD
- [ ] `contracts:manage` — доступ к операциям смены статуса и jobs
- [ ] `orders:create` — создание заказов (NEW v3.0: раньше был `orders:edit`)
- [ ] `orders:cancel` — отмена заказов (NEW v3.0)
- [ ] Без scope → 403 `INSUFFICIENT_SCOPE`
- [ ] Без токена → 401 `NOT_AUTHENTICATED`
- [ ] UI-элементы скрыты/заблокированы при отсутствии scope

### 23.12 Edge Cases

- [ ] Длинный `reason` (512 символов) — отображается корректно
- [ ] Длинный `legal_name` (255 символов) — не ломает layout
- [ ] `credit_limit = 0` (безлимитный) — шкала не показывает процент
- [ ] `end_date = null` (бессрочный) — отображается «Бессрочный»
- [ ] Нулевая сумма инвойса (`amount = 0`) — за период не было заказов
- [ ] Пустой прайс-лист — все товары по каталожным ценам
- [ ] Пустой акт сверки — `orders: [], payments: [], balance: 0`
- [ ] `cancellation_reason` отображается в карточке отменённого заказа (NEW v3.0)
- [ ] `notes` отображается в карточке заказа (NEW v3.0)
- [ ] `OrdersResponse.total_count = 0` при пустом списке (NEW v3.0)
- [ ] Отмена CONTRACT-заказа → `credit_used` корректно уменьшается (NEW v3.0)
- [ ] Suspend/Terminate → проверить что in-flight заказы отменены (NEW v3.0)

### 23.13 Платформенные изменения (NEW v3.2)

- [ ] `POST /client/login` — отправляет JSON body `{phone, password}`, а НЕ query params
- [ ] `GET /health` → 200 `{"status":"ok"}` (поле `environment` отсутствует)
- [ ] `GET /health` → 503 `{"status":"db_unavailable"}` при недоступной БД
- [ ] Shifts endpoints — удалены, код не обращается к `/backoffice/shifts/`
- [ ] `PATCH /backoffice/users/{id}` — self-edit возвращает 400
- [ ] `PATCH /backoffice/users/{id}` — role=system возвращает 403
- [ ] Courier password ≥ 8 символов — валидация на frontend
- [ ] `POST /backoffice/orders/` — ответ содержит `OrderResponse`
- [ ] `GET /backoffice/finances/b2b-debts` — список дебиторки B2B
- [ ] `GET /backoffice/inventories/search?q=…` — поиск инвентарей
- [ ] `GET /backoffice/transfers/?type=…&from_date=…` — фильтры работают
- [ ] `DashboardTotals` — отображение `total_b2b_credit_used`, `total_b2b_settled_debt`
- [ ] `limit ≤ 100` на contracts/orders list (запрос с limit=200 → ошибка)

---

_Конец документа_
