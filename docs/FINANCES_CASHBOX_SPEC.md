# SPEC: Финансы + Касса (Finances & Cashbox)

> Версия: 1.0 | Дата: 2026-04-01
> Автор: Senior HOD Business Finance API Designer

---

## 1. Контекст и цели

### 1.1 Что уже есть

Фундамент финансовой системы готов:

- **Двойная запись** — каждая операция = перевод с одного счёта на другой
- **Append-only леджер** — PG-триггер блокирует DELETE/UPDATE на `transactions`
- **Атомарные балансы** — триггер `update_account_balances()` с row-level locking
- **7 типов счетов** — REVENUE, CASH, CARD, BANK, DISCOUNT, CLIENT, COURIER
- **3 статуса транзакций** — PENDING → COMPLETED / REJECTED
- **Автосеттлмент** — при DELIVERED и PICKUP_COMPLETED транзакции создаются автоматически
- **BillingService** — пустая заглушка, ни одного метода
- **finances.py роутер** — пустой файл, ноль эндпоинтов

### 1.2 Что нужно построить

Полноценный раздел **«Финансы + Касса»** для backoffice:

| Цель | Описание |
|------|---------|
| **Обзор денег** | Дашборд: балансы всех системных счетов, итого по ролям |
| **Верификация платежей** | Бухгалтер подтверждает/отклоняет PENDING-транзакции (карта) |
| **Ручные проводки** | Инкассация, возврат, корректировка, пополнение |
| **Касса** | Приём наличных кассиром при самовывозе |
| **Выписки** | История транзакций по любому счёту с фильтрами |
| **Сверка курьеров** | Баланс кассы курьера vs фактическая наличка |
| **CONTRACT-оплата** | B2B-отсрочка: начисление долга, выставление счёта |
| **Скидки** | Применение скидок через счёт DISCOUNT |

---

## 2. Финансовая модель (Business Domain)

### 2.1 Карта счетов

```
СИСТЕМНЫЕ (user_id = SYSTEM_USER_ID):
┌─────────────────────────────────────────────────────────────┐
│  REVENUE    — Выручка (sink для дохода от продаж)           │
│  CASH       — Центральная касса (наличные на складе/офисе)  │
│  CARD       — Карточный счёт (переводы/QR/Payme/Click)      │
│  BANK       — Банковский счёт (расчётный счёт компании)     │
│  DISCOUNT   — Счёт скидок (списание стоимости скидки)       │
└─────────────────────────────────────────────────────────────┘

ПОЛЬЗОВАТЕЛЬСКИЕ:
┌─────────────────────────────────────────────────────────────┐
│  CLIENT     — Лицевой счёт клиента (1 на клиента)          │
│               Положительный баланс = долг клиента           │
│               Отрицательный баланс = переплата / кредит     │
│                                                             │
│  COURIER    — Касса курьера (1 на курьера)                  │
│               Положительный баланс = наличные на руках      │
│               Нулевой = всё сдано в центральную кассу       │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Проводки по бизнес-операциям

#### Доставка — оплата наличными (CASH)

```
Триггер: order.status → DELIVERED

Проводка 1: REVENUE → CLIENT   (COMPLETED)  "Задолженность за заказ"
  Эффект: CLIENT.balance += total  (долг клиента)
  Эффект: REVENUE.balance -= total (зафиксирована выручка)

Проводка 2: CLIENT → COURIER   (COMPLETED)  "Оплата наличными курьеру"
  Эффект: CLIENT.balance -= total  (долг погашен)
  Эффект: COURIER.balance += total (курьер держит наличные)

Итог: CLIENT.balance = 0, COURIER.balance += total
```

#### Доставка — оплата картой (CARD)

```
Триггер: order.status → DELIVERED

Проводка 1: REVENUE → CLIENT   (COMPLETED)  "Задолженность за заказ"
Проводка 2: CLIENT → CARD      (PENDING)    "Перевод на карту"
  Эффект: балансы НЕ меняются (PENDING не трогает триггер)

→ Бухгалтер верифицирует:
  PATCH /finances/transactions/{id}/verify  → status: COMPLETED
  Эффект: CLIENT.balance -= total, CARD.balance += total

→ Или отклоняет:
  PATCH /finances/transactions/{id}/reject  → status: REJECTED
  Эффект: нет изменений, долг клиента остаётся
```

#### Доставка — оплата по договору (CONTRACT) [НОВОЕ]

```
Триггер: order.status → DELIVERED

Проводка 1: REVENUE → CLIENT   (COMPLETED)  "Задолженность по договору"
  Эффект: CLIENT.balance += total (B2B-долг зафиксирован)

Проводка 2: НЕ создаётся — клиент оплатит позже.

→ Когда B2B-клиент оплачивает (банковский перевод):
  POST /finances/transactions  (ручная проводка бухгалтера)
  CLIENT → BANK (COMPLETED)  "Оплата по договору, счёт №..."
  Эффект: CLIENT.balance -= amount, BANK.balance += amount
```

#### Самовывоз — наличные (WAREHOUSE_PICKUP)

```
Триггер: order.status → PICKUP_COMPLETED

Проводка 1: REVENUE → CLIENT   (COMPLETED)  "Задолженность (самовывоз)"
Проводка 2: CLIENT → CASH      (COMPLETED)  "Оплата наличными на складе"

Итог: деньги сразу в CASH, CLIENT.balance = 0
```

#### Самовывоз — оплата картой [НОВОЕ]

```
Триггер: order.status → PICKUP_COMPLETED

Проводка 1: REVENUE → CLIENT   (COMPLETED)  "Задолженность (самовывоз)"
Проводка 2: CLIENT → CARD      (PENDING)    "Оплата картой на складе"

→ Бухгалтер верифицирует PENDING → COMPLETED
```

#### Инкассация — курьер сдаёт наличные

```
Триггер: закрытие смены ИЛИ ручная проводка

Проводка: COURIER → CASH  (COMPLETED)  "Инкассация при закрытии смены"
  Эффект: COURIER.balance -= amount, CASH.balance += amount
```

#### Внесение на банковский счёт

```
Триггер: ручная проводка бухгалтера

Проводка: CASH → BANK  (COMPLETED)  "Инкассация в банк"
  Эффект: CASH.balance -= amount, BANK.balance += amount
```

#### Возврат денег клиенту

```
Триггер: ручная проводка бухгалтера

Проводка: CASH → CLIENT  (COMPLETED)  "Возврат по заказу #..."
  Эффект: CLIENT.balance -= amount (уменьшение долга или создание кредита)
```

#### Скидка на заказ [НОВОЕ]

```
Триггер: при создании заказа (если скидка применена)

Проводка: DISCOUNT → CLIENT  (COMPLETED)  "Скидка на заказ"
  Эффект: CLIENT.balance -= discount_amount (часть долга погашена скидкой)
```

### 2.3 Матрица допустимых проводок

| from → to | REVENUE | CASH | CARD | BANK | DISCOUNT | CLIENT | COURIER |
|-----------|---------|------|------|------|----------|--------|---------|
| **REVENUE** | — | — | — | — | — | auto: долг | — |
| **CASH** | — | — | — | manual: инкассация в банк | — | manual: возврат | — |
| **CARD** | — | — | — | manual: вывод | — | manual: возврат | — |
| **BANK** | — | manual: снятие | — | — | — | manual: возврат | — |
| **DISCOUNT** | — | — | — | — | — | auto: скидка | — |
| **CLIENT** | — | auto: самовывоз | auto/pending: карта | manual: B2B оплата | — | — | auto: наличные |
| **COURIER** | — | auto/manual: инкассация | — | — | — | — | — |

---

## 3. API Спецификация

### 3.1 Backoffice — Финансовый дашборд

```
GET /api/v1/backoffice/finances/dashboard
Scope: FINANCES_READ
```

**Response 200:**
```json
{
  "system_accounts": {
    "revenue": { "id": "...", "balance": -15200000, "name": "Выручка" },
    "cash":    { "id": "...", "balance": 8500000,   "name": "Кассовый счёт" },
    "card":    { "id": "...", "balance": 3200000,   "name": "Карта" },
    "bank":    { "id": "...", "balance": 2500000,   "name": "Банковский счёт" },
    "discount":{ "id": "...", "balance": -100000,   "name": "Счёт скидок" }
  },
  "totals": {
    "total_revenue": 15200000,
    "total_cash_in_hand": 8500000,
    "total_card_pending": 450000,
    "total_client_debt": 1200000,
    "total_courier_cash": 750000
  },
  "pending_transactions_count": 12
}
```

**Бизнес-логика:**
- `total_revenue` = `-revenue.balance` (revenue всегда отрицательный)
- `total_card_pending` = сумма PENDING-транзакций, где `to_id = CARD`
- `total_client_debt` = сумма `balance` по всем CLIENT-счетам, где `balance > 0`
- `total_courier_cash` = сумма `balance` по всем COURIER-счетам, где `balance > 0`

---

### 3.2 Счета — CRUD + список

```
GET /api/v1/backoffice/finances/accounts
Scope: FINANCES_READ
Query: ?type=client&search=Иванов&page=1&size=50
```

**Response 200:**
```json
{
  "total_count": 134,
  "accounts": [
    {
      "id": "...",
      "user_id": "...",
      "user_name": "Иван Иванов",
      "type": "client",
      "name": "Лицевой счет клиента: Иван Иванов",
      "balance": 450000,
      "is_active": true,
      "created_at": "2026-03-15T10:00:00Z",
      "updated_at": "2026-04-01T14:30:00Z"
    }
  ]
}
```

**Фильтры:**
- `type: AccountType | None` — фильтр по типу (client, courier, etc.)
- `search: str | None` — поиск по `name` или `user.username`
- `min_balance / max_balance: int | None` — диапазон баланса
- `has_debt: bool | None` — `True` = balance > 0 для CLIENT-счетов

---

```
GET /api/v1/backoffice/finances/accounts/{account_id}
Scope: FINANCES_READ
```

**Response 200:**
```json
{
  "id": "...",
  "user_id": "...",
  "user_name": "Курьер Азиз",
  "type": "courier",
  "name": "Касса курьера: Курьер Азиз",
  "balance": 750000,
  "is_active": true,
  "created_at": "...",
  "updated_at": "...",
  "recent_transactions": [
    {
      "id": "...",
      "direction": "incoming",
      "counterparty": { "id": "...", "name": "Иван Иванов", "type": "client" },
      "amount": 250000,
      "status": "completed",
      "reason": "Оплата наличными курьеру",
      "order_id": "...",
      "created_at": "..."
    }
  ]
}
```

---

### 3.3 Транзакции — просмотр и фильтрация

```
GET /api/v1/backoffice/finances/transactions
Scope: FINANCES_READ
Query: ?status=pending&account_id=...&date_from=...&date_to=...&page=1&size=50
```

**Response 200:**
```json
{
  "total_count": 340,
  "transactions": [
    {
      "id": "...",
      "from_account": { "id": "...", "name": "Лицевой счет: Иванов", "type": "client" },
      "to_account":   { "id": "...", "name": "Карта", "type": "card" },
      "amount": 450000,
      "status": "pending",
      "reason": "Перевод на карту",
      "order_id": "...",
      "verified_by": null,
      "created_at": "2026-04-01T14:30:00Z"
    }
  ]
}
```

**Фильтры:**
- `status: TransactionStatus | None` — pending / completed / rejected
- `account_id: UUID | None` — транзакции ОТ или К этому счёту
- `order_id: UUID | None` — транзакции по конкретному заказу
- `date_from / date_to: datetime | None` — диапазон дат
- `min_amount / max_amount: int | None` — диапазон сумм
- `from_account_type / to_account_type: AccountType | None` — фильтр по типу счёта

---

### 3.4 Верификация транзакций (Бухгалтер)

```
PATCH /api/v1/backoffice/finances/transactions/{id}/verify
Scope: FINANCES_WRITE
```

**Request body:** нет (verified_by берётся из JWT)

**Response 200:**
```json
{
  "id": "...",
  "status": "completed",
  "verified_by_id": "...",
  "verified_by_name": "Бухгалтер Марина",
  "verified_at": "2026-04-01T15:00:00Z"
}
```

**Бизнес-правила:**
- Можно верифицировать только `status = PENDING`
- Триггер автоматически обновит балансы обоих счетов
- `verified_by_id` = ID текущего пользователя из JWT
- Запись в лог

---

```
PATCH /api/v1/backoffice/finances/transactions/{id}/reject
Scope: FINANCES_WRITE
```

**Request body:**
```json
{
  "reason": "Клиент не подтвердил оплату"
}
```

**Response 200:**
```json
{
  "id": "...",
  "status": "rejected",
  "verified_by_id": "...",
  "reject_reason": "Клиент не подтвердил оплату"
}
```

**Бизнес-правила:**
- Можно отклонить только `status = PENDING`
- Балансы не меняются (REJECTED не трогает триггер)
- Долг клиента остаётся — нужно создать новую транзакцию или повторить оплату

---

### 3.5 Ручные проводки

```
POST /api/v1/backoffice/finances/transactions
Scope: FINANCES_WRITE
```

**Request body:**
```json
{
  "from_id": "uuid-courier-account",
  "to_id": "uuid-system-cash",
  "amount": 750000,
  "reason": "Инкассация наличных от курьера Азиза",
  "order_id": null
}
```

**Response 201:**
```json
{
  "id": "...",
  "from_account": { "id": "...", "name": "Касса курьера: Азиз", "type": "courier" },
  "to_account":   { "id": "...", "name": "Кассовый счёт", "type": "cash" },
  "amount": 750000,
  "status": "completed",
  "reason": "Инкассация наличных от курьера Азиза",
  "created_at": "..."
}
```

**Бизнес-правила:**
- Ручные проводки создаются со `status = COMPLETED` (сразу влияют на балансы)
- Валидация: `from_id != to_id` (SelfTransferError)
- Валидация: `amount > 0` (InvalidTransactionAmountError)
- Валидация: оба счёта существуют и активны (AccountNotFoundError)
- `created_by_id` = ID текущего пользователя (аудит)

**Типичные ручные проводки:**

| Сценарий | from → to | Кто делает |
|----------|-----------|------------|
| Инкассация курьера | COURIER → CASH | Бухгалтер / Кассир |
| Инкассация в банк | CASH → BANK | Бухгалтер |
| Возврат клиенту (наличные) | CASH → CLIENT | Бухгалтер |
| B2B-оплата по договору | CLIENT → BANK | Бухгалтер |
| Снятие с банка в кассу | BANK → CASH | Бухгалтер |
| Корректировка (переплата) | CLIENT → CASH | Бухгалтер |

---

### 3.6 Выписка по счёту

```
GET /api/v1/backoffice/finances/accounts/{account_id}/statement
Scope: FINANCES_READ
Query: ?date_from=2026-03-01&date_to=2026-03-31&page=1&size=100
```

**Response 200:**
```json
{
  "account": {
    "id": "...",
    "name": "Касса курьера: Азиз",
    "type": "courier",
    "current_balance": 750000
  },
  "period": {
    "from": "2026-03-01",
    "to": "2026-03-31",
    "opening_balance": 0,
    "closing_balance": 750000,
    "total_incoming": 2500000,
    "total_outgoing": 1750000
  },
  "transactions": [
    {
      "id": "...",
      "direction": "incoming",
      "counterparty": { "id": "...", "name": "Иван Иванов", "type": "client" },
      "amount": 250000,
      "running_balance": 250000,
      "status": "completed",
      "reason": "Оплата наличными курьеру",
      "order_id": "...",
      "created_at": "2026-03-15T10:00:00Z"
    }
  ]
}
```

**Бизнес-логика:**
- `direction`: `incoming` если `to_id = account_id`, `outgoing` если `from_id = account_id`
- `counterparty`: другой счёт в транзакции
- `running_balance`: накопительный баланс (пересчитывается от opening_balance)
- `opening_balance`: баланс на начало периода (сумма всех COMPLETED-транзакций до `date_from`)
- Только `status = COMPLETED` транзакции учитываются в running_balance

---

### 3.7 Сверка курьеров

```
GET /api/v1/backoffice/finances/couriers/summary
Scope: FINANCES_READ
```

**Response 200:**
```json
{
  "couriers": [
    {
      "courier_id": "...",
      "courier_name": "Курьер Азиз",
      "account_id": "...",
      "cash_balance": 750000,
      "today_collected": 1200000,
      "today_deposited": 450000,
      "pending_deposit": 750000,
      "active_orders_count": 3
    }
  ],
  "total_courier_cash": 2100000,
  "total_pending_deposit": 1500000
}
```

**Бизнес-логика:**
- `cash_balance` = текущий `COURIER.balance`
- `today_collected` = сумма COMPLETED-транзакций CLIENT → COURIER за сегодня
- `today_deposited` = сумма COMPLETED-транзакций COURIER → CASH за сегодня
- `pending_deposit` = `cash_balance` (что ещё не сдано)

---

### 3.8 Долги клиентов

```
GET /api/v1/backoffice/finances/clients/debts
Scope: FINANCES_READ
Query: ?min_debt=100000&sort=balance_desc&page=1&size=50
```

**Response 200:**
```json
{
  "total_debt": 4500000,
  "debtors_count": 23,
  "clients": [
    {
      "client_id": "...",
      "client_name": "Ресторан Чайхона",
      "role": "client_b2b",
      "phone": "+998901234567",
      "account_id": "...",
      "balance": 1500000,
      "last_order_date": "2026-03-28",
      "last_payment_date": "2026-03-20",
      "overdue_days": 11
    }
  ]
}
```

---

### 3.9 Касса — приём оплаты кассиром

```
POST /api/v1/backoffice/finances/cashbox/accept-payment
Scope: PAYMENTS_CREATE
```

**Request body:**
```json
{
  "client_id": "uuid",
  "amount": 500000,
  "payment_method": "cash",
  "reason": "Оплата за заказ",
  "order_id": "uuid | null"
}
```

**Бизнес-логика:**
- `payment_method = cash`: CLIENT → CASH (COMPLETED)
- `payment_method = card`: CLIENT → CARD (PENDING, ожидает верификации)
- Кассир (`PAYMENTS_CREATE`) может принимать оплату, но не может делать произвольные проводки
- `order_id` опционален — оплата может быть привязана к заказу или быть "свободной" (погашение долга)

---

### 3.10 Профиль курьера — его касса

```
GET /api/v1/courier/finances/my-balance
Scope: PAYMENTS_CREATE (у курьера есть)
```

**Response 200:**
```json
{
  "account_id": "...",
  "balance": 750000,
  "today_collected": 1200000,
  "today_deposited": 450000,
  "transactions_today": [
    {
      "direction": "incoming",
      "amount": 250000,
      "reason": "Оплата наличными курьеру",
      "order_id": "...",
      "time": "14:30"
    }
  ]
}
```

---

### 3.11 Клиентский профиль — баланс и история

```
GET /api/v1/client/finances/my-balance
Scope: ORDERS_READ (у клиента есть)
```

**Response 200:**
```json
{
  "account_id": "...",
  "balance": 450000,
  "balance_label": "Задолженность: 4 500 сум",
  "recent_payments": [
    {
      "amount": 250000,
      "status": "completed",
      "reason": "Оплата наличными курьеру",
      "date": "2026-03-28"
    }
  ]
}
```

---

## 4. CONTRACT-оплата (B2B отсрочка)

### 4.1 Флоу

```
1. B2B-клиент создаёт заказ (payment_method = CONTRACT)
2. При доставке:
   - REVENUE → CLIENT (COMPLETED) — долг зафиксирован
   - Вторая проводка НЕ создаётся (отсрочка)
3. CLIENT.balance растёт с каждым заказом
4. Раз в месяц (или по запросу):
   - Бухгалтер формирует акт сверки
   - Клиент оплачивает банковским переводом
   - Бухгалтер создаёт проводку: CLIENT → BANK (COMPLETED)
5. CLIENT.balance обнуляется
```

### 4.2 Изменения в `_process_financial_settlement`

```python
# Текущий код: CONTRACT не обрабатывается
# Добавить:

elif order.payment_method == PaymentMethod.CONTRACT:
    # B2B-отсрочка: только фиксируем долг
    # Вторая проводка не создаётся
    # CLIENT.balance += total (долг растёт)
    pass  # Первая проводка REVENUE → CLIENT уже создана выше
```

---

## 5. Скидки

### 5.1 Механизм

Счёт `DISCOUNT` — системный источник для покрытия скидок. Работает аналогично `REVENUE` — баланс уходит в минус (компания "тратит" на скидки).

```
Заказ на 500 000 со скидкой 10% (50 000):

Проводка 1: REVENUE  → CLIENT  (450 000, COMPLETED)  "Задолженность"
Проводка 2: DISCOUNT → CLIENT  (50 000,  COMPLETED)  "Скидка 10%"
Проводка 3: CLIENT   → COURIER (500 000, COMPLETED)  "Оплата наличными"

Итог:
  CLIENT.balance  = +450 000 + 50 000 - 500 000 = 0 (долг погашен)
  COURIER.balance += 500 000 (получил полную сумму)
  REVENUE.balance -= 450 000 (выручка за вычетом скидки)
  DISCOUNT.balance -= 50 000 (учтена скидка)
```

### 5.2 API скидок

В текущей версии скидки применяются через поле в заказе:

```
POST /api/v1/backoffice/orders/
{
  "items": [...],
  "payment_method": "cash",
  "discount_amount": 50000  // Новое поле
}
```

Применение скидки создаёт дополнительную проводку DISCOUNT → CLIENT при сеттлменте.

---

## 6. Изменения в существующем коде

### 6.1 `_process_financial_settlement` — полная версия

```python
async def _process_financial_settlement(self, order: Order) -> None:
    client_account = await self.uow.accounts.get_client_account(order.client_id)
    revenue_account = await self.uow.accounts.get_system_revenue_account()

    effective_amount = order.total_amount - (order.discount_amount or 0)

    financial_txns = []

    # 1. Долг (выручка)
    if effective_amount > 0:
        financial_txns.append({
            "from_id": revenue_account.id,
            "to_id": client_account.id,
            "amount": effective_amount,
            "order_id": order.id,
            "status": TransactionStatus.COMPLETED,
            "reason": "Задолженность за заказ",
        })

    # 2. Скидка (если есть)
    if order.discount_amount and order.discount_amount > 0:
        discount_account = await self.uow.accounts.get_system_account(AccountType.DISCOUNT)
        financial_txns.append({
            "from_id": discount_account.id,
            "to_id": client_account.id,
            "amount": order.discount_amount,
            "order_id": order.id,
            "status": TransactionStatus.COMPLETED,
            "reason": f"Скидка на заказ",
        })

    # 3. Оплата — зависит от payment_method
    if order.payment_method == PaymentMethod.CASH:
        if order.courier_id:
            courier_account = await self.uow.accounts.get_courier_account(order.courier_id)
            if courier_account:
                financial_txns.append({
                    "from_id": client_account.id,
                    "to_id": courier_account.id,
                    "amount": order.total_amount,
                    "order_id": order.id,
                    "status": TransactionStatus.COMPLETED,
                    "reason": "Оплата наличными курьеру",
                })

    elif order.payment_method == PaymentMethod.CARD:
        card_account = await self.uow.accounts.get_system_card_account()
        financial_txns.append({
            "from_id": client_account.id,
            "to_id": card_account.id,
            "amount": order.total_amount,
            "order_id": order.id,
            "status": TransactionStatus.PENDING,
            "reason": "Оплата картой",
        })

    elif order.payment_method == PaymentMethod.CONTRACT:
        # B2B-отсрочка: второй проводки нет, долг остаётся
        pass

    await self.uow.financial_transactions.add_many(financial_txns)
```

### 6.2 `_process_pickup_settlement` — с учётом payment_method

```python
async def _process_pickup_settlement(self, order: Order) -> None:
    client_account = await self.uow.accounts.get_client_account(order.client_id)
    revenue_account = await self.uow.accounts.get_system_revenue_account()

    financial_txns = [
        {
            "from_id": revenue_account.id,
            "to_id": client_account.id,
            "amount": order.total_amount,
            "order_id": order.id,
            "status": TransactionStatus.COMPLETED,
            "reason": "Задолженность за заказ (самовывоз)",
        }
    ]

    if order.payment_method == PaymentMethod.CASH:
        cash_account = await self.uow.accounts.get_system_cash_account()
        financial_txns.append({
            "from_id": client_account.id,
            "to_id": cash_account.id,
            "amount": order.total_amount,
            "order_id": order.id,
            "status": TransactionStatus.COMPLETED,
            "reason": "Оплата наличными на складе",
        })

    elif order.payment_method == PaymentMethod.CARD:
        card_account = await self.uow.accounts.get_system_card_account()
        financial_txns.append({
            "from_id": client_account.id,
            "to_id": card_account.id,
            "amount": order.total_amount,
            "order_id": order.id,
            "status": TransactionStatus.PENDING,
            "reason": "Оплата картой на складе",
        })

    elif order.payment_method == PaymentMethod.CONTRACT:
        pass  # B2B-отсрочка

    await self.uow.financial_transactions.add_many(financial_txns)
```

### 6.3 BillingService — методы

```python
class BillingService:
    # Дашборд
    async def get_dashboard() -> FinanceDashboard

    # Счета
    async def get_accounts(filters) -> tuple[int, list[Account]]
    async def get_account_detail(account_id) -> AccountDetail
    async def get_account_statement(account_id, date_from, date_to) -> Statement

    # Транзакции
    async def get_transactions(filters) -> tuple[int, list[Transaction]]
    async def create_manual_transaction(dto, created_by_id) -> Transaction
    async def verify_transaction(txn_id, verified_by_id) -> Transaction
    async def reject_transaction(txn_id, verified_by_id, reason) -> Transaction

    # Сводки
    async def get_couriers_summary() -> CouriersSummary
    async def get_clients_debts(filters) -> ClientsDebts

    # Касса
    async def accept_payment(dto, cashier_id) -> Transaction
```

---

## 7. Доступы по ролям

| Эндпоинт | ADMIN | ACCOUNTANT | CASHIER | COURIER | CLIENT |
|----------|-------|------------|---------|---------|--------|
| GET /finances/dashboard | FINANCES_READ | FINANCES_READ | — | — | — |
| GET /finances/accounts | FINANCES_READ | FINANCES_READ | — | — | — |
| GET /finances/transactions | FINANCES_READ | FINANCES_READ | — | — | — |
| PATCH .../verify | FINANCES_WRITE | FINANCES_WRITE | — | — | — |
| PATCH .../reject | FINANCES_WRITE | FINANCES_WRITE | — | — | — |
| POST /finances/transactions | FINANCES_WRITE | FINANCES_WRITE | — | — | — |
| GET .../statement | FINANCES_READ | FINANCES_READ | — | — | — |
| GET .../couriers/summary | FINANCES_READ | FINANCES_READ | — | — | — |
| GET .../clients/debts | FINANCES_READ | FINANCES_READ | — | — | — |
| POST .../cashbox/accept-payment | — | — | PAYMENTS_CREATE | — | — |
| GET /courier/finances/my-balance | — | — | — | PAYMENTS_CREATE | — |
| GET /client/finances/my-balance | — | — | — | — | ORDERS_READ | — |

---

## 8. Схемы данных (новые Pydantic-модели)

```python
# --- Dashboard ---
class SystemAccountSummary(BaseModel):
    id: uuid.UUID
    balance: int
    name: str

class FinanceDashboard(BaseModel):
    system_accounts: dict[str, SystemAccountSummary]
    totals: DashboardTotals
    pending_transactions_count: int

class DashboardTotals(BaseModel):
    total_revenue: int
    total_cash_in_hand: int
    total_card_pending: int
    total_client_debt: int
    total_courier_cash: int

# --- Обогащённая транзакция ---
class AccountShort(BaseModel):
    id: uuid.UUID
    name: str
    type: AccountType

class TransactionDetail(BaseModel):
    id: uuid.UUID
    from_account: AccountShort
    to_account: AccountShort
    amount: int
    status: TransactionStatus
    reason: str
    order_id: uuid.UUID | None
    verified_by_id: uuid.UUID | None
    verified_by_name: str | None
    created_at: datetime

# --- Выписка ---
class StatementPeriod(BaseModel):
    date_from: date
    date_to: date
    opening_balance: int
    closing_balance: int
    total_incoming: int
    total_outgoing: int

class StatementEntry(BaseModel):
    id: uuid.UUID
    direction: Literal["incoming", "outgoing"]
    counterparty: AccountShort
    amount: int
    running_balance: int
    status: TransactionStatus
    reason: str
    order_id: uuid.UUID | None
    created_at: datetime

class AccountStatement(BaseModel):
    account: AccountShort
    period: StatementPeriod
    transactions: list[StatementEntry]

# --- Сверка курьеров ---
class CourierFinanceSummary(BaseModel):
    courier_id: uuid.UUID
    courier_name: str
    account_id: uuid.UUID
    cash_balance: int
    today_collected: int
    today_deposited: int
    pending_deposit: int
    active_orders_count: int

# --- Долги клиентов ---
class ClientDebt(BaseModel):
    client_id: uuid.UUID
    client_name: str
    role: str
    phone: str | None
    account_id: uuid.UUID
    balance: int
    last_order_date: date | None
    last_payment_date: date | None
    overdue_days: int

# --- Касса ---
class AcceptPaymentRequest(BaseModel):
    client_id: uuid.UUID
    amount: int = Field(gt=0)
    payment_method: Literal["cash", "card"]
    reason: str = Field(min_length=3, max_length=255)
    order_id: uuid.UUID | None = None
```

---

## 9. Приоритеты реализации

### Фаза 1 — MVP (must have)
1. `GET /finances/dashboard` — обзор денег
2. `GET /finances/transactions` — список с фильтрами
3. `PATCH .../verify` и `.../reject` — верификация карточных платежей
4. `POST /finances/transactions` — ручные проводки
5. CONTRACT-оплата в `_process_financial_settlement`
6. CARD-оплата в `_process_pickup_settlement`

### Фаза 2 — Operational
7. `GET /finances/accounts` — список счетов
8. `GET .../statement` — выписка по счёту
9. `GET .../couriers/summary` — сверка курьеров
10. `GET .../clients/debts` — долги клиентов
11. `POST .../cashbox/accept-payment` — кассовый приём

### Фаза 3 — Self-service
12. `GET /courier/finances/my-balance` — касса курьера
13. `GET /client/finances/my-balance` — баланс клиента
14. Скидки (DISCOUNT-проводки)

---

## 10. Ограничения и решения

| Ограничение | Решение |
|-------------|---------|
| Баланс обновляется ТОЛЬКО триггером | Никогда не писать в `account.balance` из Python |
| Транзакции append-only | Отмена = новая обратная проводка, не UPDATE |
| `from_id != to_id` (CHECK) | Валидировать в сервисе ДО insert |
| `amount > 0` (CHECK) | Валидировать в схеме Pydantic (`gt=0`) |
| Нет rate limiting | Ручные проводки должны логироваться для аудита |
| Нет multi-currency | Все суммы в тиыйнах (1 сум = 100 тиыйн) |
