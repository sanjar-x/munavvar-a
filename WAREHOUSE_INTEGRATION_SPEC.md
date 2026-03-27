# Warehouse Ledger — Integration Spec Flow
**Version:** 1.0
**Date:** 2026-03-27
**Status:** Final

---

## 0. Архитектура системы (быстрый обзор)

```
Frontend (React + RTK Query)
    └── baseApi (Bearer token из state.auth.accessToken)
            ├── warehousesApi  →  GET/POST /api/v1/backoffice/warehouses/...
            └── transfersApi   →  GET/POST/PUT /api/v1/backoffice/transfers/...

Backend (FastAPI + SQLAlchemy async)
    └── Каждое движение товаров = 3 записи (Event Sourcing):
            ├── StockTransfer     (шапка накладной)
            ├── StockTransferItem (строки накладной)
            └── StockTransaction  (иммутабельный леджер)
                    └── TRIGGER → inventory_balances (материализованные остатки)
```

---

## 1. Критический баг: `updateTransferItems` — тело запроса

### Проблема

```javascript
// transfersApi.js — ТЕКУЩИЙ КОД (НЕВЕРНО):
updateTransferItems: build.mutation({
  query: ({ id, items }) => ({
    url: `/backoffice/transfers/${id}/items`,
    method: "PUT",
    body: { items },          // ← объект { items: [...] }
  }),
})
```

```python
# transfers.py — БЭКЕНД ОЖИДАЕТ:
@router.put("/{transfer_id}/items")
async def update_transfer_items(
    items: list[TransferItemCreate],   # ← напрямую массив, не обёрнутый объект
    ...
)
```

### Исправление в `transfersApi.js`

```javascript
updateTransferItems: build.mutation({
  query: ({ id, items }) => ({
    url: `/backoffice/transfers/${id}/items`,
    method: "PUT",
    body: items,              // ← массив напрямую, без обёртки
  }),
  invalidatesTags: (result, error, { id }) => [
    { type: "Transfers", id },
    { type: "Transfers", id: "LIST" },
  ],
}),
```

---

## 2. Полная карта API вызовов страницы

### 2.1 Левая панель — Список складов

| Действие        | RTK Hook                     | HTTP | Endpoint                         | Тело                |
| --------------- | ---------------------------- | ---- | -------------------------------- | ------------------- |
| Загрузка списка | `useGetWarehousesQuery()`    | GET  | `/api/v1/backoffice/warehouses/` | —                   |
| Создать склад   | `useCreateWarehouseMutation` | POST | `/api/v1/backoffice/warehouses/` | `{ name, user_id }` |

**Ответ `GET /warehouses/`** — массив `WarehouseDetailResponse`:
```json
[
  {
    "id": "uuid",
    "name": "Склад Центр",
    "user_id": "uuid",
    "balances": [
      { "product": { "id": "uuid", "name": "Вода 19л" }, "quantity": 150 },
      { "product": { "id": "uuid", "name": "Пустая бутыль" }, "quantity": 80 }
    ]
  }
]
```

**Бейдж в левой панели** = `warehouse.balances.length` (количество уникальных позиций).

**Ответ `POST /warehouses/`** — `InventoryResponse`:
```json
{
  "id": "uuid",
  "name": "Склад Центр",
  "type": "WAREHOUSE",
  "user": { "id": "uuid", "username": "Иван Иванов", "role": "ADMIN", ... },
  "is_active": true
}
```

---

### 2.2 Вкладка "Qoldiqlar" (Остатки)

| Действие          | RTK Hook                                  | HTTP | Endpoint                             |
| ----------------- | ----------------------------------------- | ---- | ------------------------------------ |
| Загрузка остатков | `useGetWarehouseDetailQuery(warehouseId)` | GET  | `/api/v1/backoffice/warehouses/{id}` |

**Ответ** — `WarehouseDetailResponse` (аналогичен пункту 2.1, один объект).

**Таблица остатков:**

| Mahsulot               | Turi                                      | Miqdor                                            |
| ---------------------- | ----------------------------------------- | ------------------------------------------------- |
| `balance.product.name` | `balance.product.type` (ProductType enum) | `balance.quantity` — выравнивание по правому краю |

**ProductType → отображение:**
- `"WATER"` → "Suv"
- `"CONTAINER"` → "Idish"
- `"EQUIPMENT"` → "Jihozlar"

**Cache invalidation:** `completeTransfer` инвалидирует `{ type: "Warehouses", id: warehouseId }` → вкладка Qoldiqlar перезагружается автоматически после проведения накладной.

---

### 2.3 Вкладка "Nakladnoy" (Накладные)

| Действие        | RTK Hook                                   | HTTP | Endpoint                        | Параметры         |
| --------------- | ------------------------------------------ | ---- | ------------------------------- | ----------------- |
| Загрузка списка | `useGetTransfersQuery({ page, size: 20 })` | GET  | `/api/v1/backoffice/transfers/` | `?page=1&size=20` |

**Ответ** — массив `TransferResponse`:
```json
[
  {
    "id": "uuid",
    "type": "FACTORY_RECEIPT",
    "status": "COMPLETED",
    "from_id": "uuid",
    "to_id": "uuid",
    "created_by_id": "uuid",
    "accepted_by_id": "uuid",
    "items": [
      { "product": { "id": "uuid", "name": "Вода 19л" }, "quantity": 100 }
    ]
  }
]
```

> **Важно:** Список накладных глобальный (не фильтруется по складу). Это соответствует бизнес-требованиям — кладовщик видит все движения.

**Разрешение имён складов в таблице:**
`from_id` / `to_id` — UUID. Для отображения имени:
```javascript
// warehouses — массив из useGetWarehousesQuery()
const getName = (id) =>
  warehouses?.find((w) => w.id === id)?.name
  ?? virtualInventoryName(id); // см. раздел 5
```

**Пагинация:** `page` (state) × `size: 20`. `hasNextPage = transfers.length === 20`.

---

### 2.4 Мастер создания накладной (3 шага)

#### Шаг 1 — Параметры накладной

| Действие         | RTK Hook                    | HTTP | Endpoint                        | Тело                       |
| ---------------- | --------------------------- | ---- | ------------------------------- | -------------------------- |
| Создать черновик | `useCreateTransferMutation` | POST | `/api/v1/backoffice/transfers/` | `{ type, from_id, to_id }` |

**Ответ** — `TransferResponse` с `status: "DRAFT"`. Сохранить `id` как `draftId`.

**Валидация маршрута на бэкенде** (`_VALID_ROUTES`):

| TransferType         | from (тип инвентаря)      | to (тип инвентаря)                  | Бизнес-смысл                  |
| -------------------- | ------------------------- | ----------------------------------- | ----------------------------- |
| `FACTORY_RECEIPT`    | `VIRTUAL_VENDOR`          | `WAREHOUSE`                         | Новая тара с завода           |
| `PURCHASE`           | `VIRTUAL_VENDOR`          | `WAREHOUSE`                         | Закупка товаров               |
| `PRODUCTION`         | `WAREHOUSE`               | `WAREHOUSE`                         | Розлив воды (склад→склад)     |
| `COURIER_LOAD`       | `WAREHOUSE`               | `COURIER`                           | Загрузка машины курьера       |
| `COURIER_RETURN`     | `COURIER`                 | `WAREHOUSE`                         | Возврат остатков в склад      |
| `CLIENT_DELIVERY`    | `COURIER`                 | `CLIENT`                            | Доставка заказа клиенту       |
| `CLIENT_RETURN`      | `CLIENT`                  | `COURIER`                           | Забор пустой тары             |
| `WAREHOUSE_TRANSFER` | `WAREHOUSE`               | `WAREHOUSE`                         | Между складами                |
| `LOSS_WRITE_OFF`     | `WAREHOUSE` или `COURIER` | `VIRTUAL_LOSS`                      | Списание утерянного/разбитого |
| `INVENTORY_FINDING`  | `VIRTUAL_VENDOR`          | `WAREHOUSE` или `COURIER`           | Излишки при инвентаризации    |
| `INITIAL_BALANCE`    | `VIRTUAL_VENDOR`          | `CLIENT`, `WAREHOUSE` или `COURIER` | Ввод начальных остатков       |

**Ошибки от бэкенда (HTTP 409):**

```json
// from_id == to_id
{ "error_code": "ROUTE_LOOP_DETECTED", "details": { "inventory_id": "uuid" } }

// Неверный тип инвентаря для данного TransferType
{ "error_code": "INVENTORY_TYPE_MISMATCH",
  "details": { "inventory_id": "uuid", "expected_type": "...", "actual_type": "..." } }
```

**Умный select для from_id / to_id:**
Фильтровать список инвентарей в зависимости от выбранного `type`. Не показывать `VIRTUAL_VENDOR` / `VIRTUAL_LOSS` в UI — они виртуальные, пользователь их не выбирает.
При `FACTORY_RECEIPT` → `from_id` фиксирован на VIRTUAL_VENDOR (подставить автоматически).

---

#### Шаг 2 — Товары

| Действие                  | RTK Hook                                      | HTTP | Endpoint                                       | Тело                                        |
| ------------------------- | --------------------------------------------- | ---- | ---------------------------------------------- | ------------------------------------------- |
| Обновить позиции          | `useUpdateTransferItemsMutation`              | PUT  | `/api/v1/backoffice/transfers/{draftId}/items` | **raw массив** `[{ product_id, quantity }]` |
| Список товаров для select | `useGetCatalogQuery({ skip: 0, limit: 100 })` | GET  | `/api/v1/backoffice/catalog/`                  | —                                           |

**Тело запроса (исправленный формат):**
```json
[
  { "product_id": "uuid", "quantity": 50 },
  { "product_id": "uuid", "quantity": 30 }
]
```

**Ошибки:**
```json
// quantity <= 0
{ "error_code": "INVALID_QUANTITY" }
```

**UX:** Если черновик уже создан (draftId существует) и пользователь вернулся на Шаг 2 — не вызывать `createTransfer` повторно, только `updateTransferItems`.

---

#### Шаг 3 — Подтверждение и проведение

| Действие             | RTK Hook                                   | HTTP | Endpoint                                          | Тело                 |
| -------------------- | ------------------------------------------ | ---- | ------------------------------------------------- | -------------------- |
| Провести накладную   | `useCompleteTransferMutation`              | POST | `/api/v1/backoffice/transfers/{draftId}/complete` | `{ accepted_by_id }` |
| Список пользователей | `useGetUsersQuery({ page: 1, size: 100 })` | GET  | `/api/v1/backoffice/users/`                       | —                    |

**Ответ** — `TransferResponse` с `status: "COMPLETED"`.

**Что происходит на бэкенде при `complete`:**
1. Блокирует строку `inventories` (from_id) — `FOR UPDATE`
2. Проверяет остатки (кроме `VIRTUAL_VENDOR`)
3. Создаёт `StockTransaction` для каждой строки накладной
4. **Триггер `update_inventory_balances` срабатывает** при каждом INSERT в `stock_transactions`:
   ```sql
   INSERT INTO inventory_balances (inventory_id, product_id, quantity)
   VALUES (from_id, product_id, -quantity),
          (to_id,   product_id, +quantity)
   ON CONFLICT (inventory_id, product_id) DO UPDATE
     SET quantity = inventory_balances.quantity + EXCLUDED.quantity
   ```
5. Устанавливает `status = COMPLETED`, `accepted_by_id`

**После успеха:**
- RTK Query инвалидирует: `{ type: "Transfers", id: "LIST" }` + `{ type: "Warehouses", id: from_id }` + `{ type: "Warehouses", id: to_id }`
- Вкладки "Qoldiqlar" и "Nakladnoy" обновятся автоматически

**Ошибки от бэкенда:**
```json
// Нехватка остатков (HTTP 409)
{
  "error_code": "INSUFFICIENT_STOCK",
  "details": {
    "shortages": { "<product_uuid>": 15 }  // дефицит: нужно N, не хватает 15
  }
}

// Накладная не в статусе DRAFT (HTTP 409)
{
  "error_code": "INVALID_TRANSFER_STATUS",
  "details": { "current_status": "COMPLETED", "expected_status": "DRAFT" }
}

// Пустая накладная (HTTP 422)
{ "error_code": "EMPTY_TRANSFER" }
```

---

## 3. Полные бизнес-потоки HOD (доставка воды)

### Flow 1: Поступление товара с завода
```
Кладовщик: Шаг1 [FACTORY_RECEIPT | VIRTUAL_VENDOR → Склад_А]
           Шаг2 [Вода 19л: 200шт, Пустая бутыль: 200шт]
           Шаг3 [accepted_by: Кладовщик] → COMPLETE

Backend:
  StockTransfer(type=FACTORY_RECEIPT, from=VIRTUAL_VENDOR, to=Склад_А, status=COMPLETED)
  StockTransferItem(Вода 19л: 200) + StockTransferItem(Пустая бутыль: 200)
  StockTransaction(VIRTUAL_VENDOR -200, Склад_А +200) × 2 позиции
  TRIGGER: inventory_balances[Склад_А][Вода 19л] += 200
           inventory_balances[Склад_А][Пустая бутыль] += 200
```

### Flow 2: Загрузка машины курьера утром
```
Кладовщик: POST /api/v1/backoffice/shifts/load-truck
  { warehouse_id, courier_inventory_id, items: [Вода 19л: 30, Пустая бутыль: 10] }

Backend:
  Проверяет: Склад_А.balances[Вода 19л] >= 30
  StockTransfer(type=COURIER_LOAD, from=Склад_А, to=Машина_Курьера, status=COMPLETED)
  StockTransferItem × 2 + StockTransaction × 2
  TRIGGER: Склад_А[Вода 19л] -= 30, Машина_Курьера[Вода 19л] += 30

```

### Flow 3: Доставка заказа клиенту (автоматически при смене статуса)
```
Курьер: PATCH /orders/{id}/status → { status: "DELIVERED", actual_items: [...] }

Backend (автоматически):
  Проверяет: Машина_Курьера.balances[Вода 19л] >= ordered_qty
  StockTransfer(CLIENT_DELIVERY, Машина_Курьера → Клиент_Адрес, order_id=X)
  StockTransfer(CLIENT_RETURN,   Клиент_Адрес → Машина_Курьера, order_id=X)
  TRIGGER: Машина_Курьера[Вода 19л] -= qty, Клиент_Адрес[Вода 19л] += qty
           Клиент_Адрес[Пустая бутыль] -= qty, Машина_Курьера[Пустая бутыль] += qty

  Финансы (одновременно):
    Transaction(Revenue → Клиент_Счет, amount=total, status=COMPLETED) — долг
    Transaction(Клиент_Счет → Курьер_Касса, amount=total)              — если CASH
    Transaction(Клиент_Счет → Card_Account, status=PENDING)            — если CARD
```

### Flow 4: Закрытие смены (вечером)
```
Кладовщик: POST /api/v1/backoffice/shifts/close
  { courier_id, returned_inventory: [Вода 19л: 5, Пустая бутыль: 45], cash_collected: 15000 }

Backend:
  Сверка: Машина_Курьера.balances == returned_inventory (иначе 400)
  StockTransfer(COURIER_RETURN, Машина_Курьера → Главный_Склад)
  StockTransferItem × N + StockTransaction × N
  TRIGGER: Машина_Курьера обнуляется, Главный_Склад += остатки

  Инкассация:
    Transaction(Курьер_Касса → SystemCash, amount=15000, status=COMPLETED)

  inventory.is_active = False  ← машина деактивируется
```

### Flow 5: Списание потерь
```
Кладовщик: POST /api/v1/backoffice/shifts/loss
  { from_inventory_id: Машина_Курьера, items: [Пустая бутыль: 2], reason: "Разбито" }

Backend:
  StockTransfer(LOSS_WRITE_OFF, Машина_Курьера → VIRTUAL_LOSS)
  TRIGGER: Машина_Курьера[Пустая бутыль] -= 2, VIRTUAL_LOSS[Пустая бутыль] += 2
```

### Flow 6: Оприходование тары клиента
```
Администратор: POST /api/v1/backoffice/inventories/capitalize
  { client_inventory_id, items: [Пустая бутыль: 5] }

Backend:
  StockTransfer(INITIAL_BALANCE, VIRTUAL_VENDOR → Клиент_Адрес)
  TRIGGER: Клиент_Адрес[Пустая бутыль] += 5
```

---

## 4. Схема данных — точные типы полей

### `WarehouseDetailResponse`
```typescript
{
  id: string;          // UUID
  name: string;
  user_id: string;     // UUID — материально ответственный
  balances: Array<{
    product: { id: string; name: string; };
    quantity: number;  // всегда >= 0 (материализованный остаток)
  }>;
}
```

### `TransferResponse`
```typescript
{
  id: string;
  type: TransferType;           // enum строка
  status: TransferStatus;       // "DRAFT" | "COMPLETED" | "CANCELLED"
  from_id: string;              // UUID инвентаря (не имя — нужен lookup)
  to_id: string;                // UUID инвентаря (не имя — нужен lookup)
  created_by_id: string;        // UUID пользователя
  accepted_by_id: string | null;
  items: Array<{
    product: { id: string; name: string; };
    quantity: number;
  }>;
  // ОТСУТСТВУЕТ: created_at — нет в схеме TransferResponse!
  // Для даты нужно добавить created_at в backend схему или использовать id (UUIDv7 содержит timestamp)
}
```

> **⚠️ Важно:** `TransferResponse` не содержит `created_at`. В таблице "Nakladnoy" колонка "Sana" не заполнится. Нужно либо добавить поле в схему, либо декодировать timestamp из UUIDv7.

### `TransferCreate` (тело POST /transfers/)
```typescript
{
  type: TransferType;
  from_id: string;   // UUID инвентаря
  to_id: string;     // UUID инвентаря
}
```

### `TransferItemCreate` (тело PUT /transfers/{id}/items — **raw array**)
```typescript
// НЕ { items: [...] } — НАПРЯМУЮ МАССИВ:
[
  { product_id: string; quantity: number; }  // quantity: int > 0
]
```

### `TransferCompleteRequest` (тело POST /transfers/{id}/complete)
```typescript
{
  accepted_by_id: string;  // UUID пользователя
}
```

---

## 5. Виртуальные инвентари — отображение имён

Виртуальные склады (`VIRTUAL_VENDOR`, `VIRTUAL_LOSS`) присутствуют в `from_id`/`to_id` накладных, но не возвращаются `GET /warehouses/` (они системные).

```javascript
const VIRTUAL_INVENTORY_NAMES = {
  // Эти ID нужно получить из API или захардкодить по конфигу
  // Альтернатива: фолбэк по типу из транзакции
};

// Функция для получения имени любого инвентаря
const getInventoryName = (id, warehouses, allInventories) => {
  const warehouse = warehouses?.find((w) => w.id === id);
  if (warehouse) return warehouse.name;

  // Фолбэк — показать тип если имя неизвестно
  return id?.slice(0, 8) + "...";
};
```

**Рекомендация:** Добавить эндпоинт `GET /api/v1/backoffice/inventories/` или расширить ответ TransferResponse полными объектами `from_inventory` / `to_inventory` (с `name` и `type`).

---

## 6. Инвалидация кэша RTK Query — полная карта

| Мутация               | Что инвалидирует                                                                  | Эффект в UI                        |
| --------------------- | --------------------------------------------------------------------------------- | ---------------------------------- |
| `createWarehouse`     | `Warehouses:LIST`                                                                 | Список складов перезагружается     |
| `createTransfer`      | —                                                                                 | Только draftId сохраняется в state |
| `updateTransferItems` | `Transfers:{id}`, `Transfers:LIST`                                                | —                                  |
| `completeTransfer`    | `Transfers:LIST`, `Warehouses:{from_id}`, `Warehouses:{to_id}`, `Warehouses:LIST` | Остатки обоих складов обновятся    |

---

## 7. Обработка ошибок — форматы

Все ошибки от бэкенда приходят в формате:
```json
{
  "detail": "Сообщение об ошибке",
  "error_code": "MACHINE_READABLE_CODE",
  "details": { ...доп. поля... }
}
```

Для парсинга использовать существующий `getApiErrorMessage(err)` из `utils`:
```javascript
// Возвращает строку для отображения в UI
const msg = getApiErrorMessage(err);
```

**Ключевые error_code для Warehouse страницы:**

| error_code                | HTTP | Когда                     | Сообщение для UI                                |
| ------------------------- | ---- | ------------------------- | ----------------------------------------------- |
| `ROUTE_LOOP_DETECTED`     | 400  | from_id == to_id          | "Склад отправителя и получателя совпадают"      |
| `INVENTORY_TYPE_MISMATCH` | 409  | Неверный маршрут для типа | "Недопустимый маршрут для этого типа накладной" |
| `INVENTORY_NOT_FOUND`     | 404  | Склад не существует       | "Склад не найден"                               |
| `INSUFFICIENT_STOCK`      | 409  | Нехватка товара           | "Недостаточно товара: {details.shortages}"      |
| `INVALID_TRANSFER_STATUS` | 409  | Не DRAFT при complete     | "Накладная уже проведена"                       |
| `EMPTY_TRANSFER`          | 422  | Нет товаров               | "Добавьте хотя бы один товар"                   |

---

## 8. Отсутствующие поля в `TransferResponse` (нужно добавить на бэкенде)

```python
# src/modules/inventory/schemas.py — добавить поля:
class TransferResponse(BaseModel):
    id: uuid.UUID
    from_id: uuid.UUID
    to_id: uuid.UUID
    created_by_id: uuid.UUID
    accepted_by_id: uuid.UUID | None
    status: TransferStatus
    type: TransferType
    items: list[TransferItemResponse] = []
    created_at: datetime          # ← ДОБАВИТЬ для колонки "Sana"
    # Опционально для имён складов без lookup:
    # from_inventory_name: str | None = None
    # to_inventory_name: str | None = None
```

---

## 9. Список всех файлов для изменений

### Frontend (`C:\Users\Sanjar\Desktop\MunnavarA\`)

| Файл                           | Изменение                                                             |
| ------------------------------ | --------------------------------------------------------------------- |
| `src/services/transfersApi.js` | **Исправить `updateTransferItems`:** `body: items` (без обёртки)      |
| `src/pages/Warehouse.jsx`      | Исправить вызов `updateItems` в WizardStep2 если он оборачивает items |

### Backend (`C:\Users\Sanjar\Desktop\munavvar-a\`)

| Файл                               | Изменение                                            |
| ---------------------------------- | ---------------------------------------------------- |
| `src/modules/inventory/schemas.py` | Добавить `created_at: datetime` в `TransferResponse` |

---

## 10. Полная таблица бизнес-процессов HOD

| Процесс                      | Тип накладной        | Откуда              | Куда                | API                          | Автоматически?    |
| ---------------------------- | -------------------- | ------------------- | ------------------- | ---------------------------- | ----------------- |
| Поступление с завода         | `FACTORY_RECEIPT`    | VIRTUAL_VENDOR      | WAREHOUSE           | POST /transfers/ (wizard)    | Нет — кладовщик   |
| Закупка товара               | `PURCHASE`           | VIRTUAL_VENDOR      | WAREHOUSE           | POST /transfers/ (wizard)    | Нет — кладовщик   |
| Розлив воды                  | `PRODUCTION`         | WAREHOUSE (сырьё)   | WAREHOUSE (готовая) | POST /transfers/ (wizard)    | Нет — кладовщик   |
| Загрузка курьера             | `COURIER_LOAD`       | WAREHOUSE           | COURIER             | POST /shifts/load-truck      | Нет — кладовщик   |
| Доставка клиенту             | `CLIENT_DELIVERY`    | COURIER             | CLIENT              | Авто при DELIVERED           | Да — при доставке |
| Возврат тары от клиента      | `CLIENT_RETURN`      | CLIENT              | COURIER             | Авто при DELIVERED           | Да — при доставке |
| Возврат остатков (конец дня) | `COURIER_RETURN`     | COURIER             | WAREHOUSE           | POST /shifts/close           | Нет — кладовщик   |
| Списание потерь              | `LOSS_WRITE_OFF`     | WAREHOUSE / COURIER | VIRTUAL_LOSS        | POST /shifts/loss            | Нет — кладовщик   |
| Оприходование тары клиента   | `INITIAL_BALANCE`    | VIRTUAL_VENDOR      | CLIENT              | POST /inventories/capitalize | Нет — оператор    |
| Перемещение между складами   | `WAREHOUSE_TRANSFER` | WAREHOUSE           | WAREHOUSE           | POST /transfers/ (wizard)    | Нет — кладовщик   |
| Излишки инвентаризации       | `INVENTORY_FINDING`  | VIRTUAL_VENDOR      | WAREHOUSE / COURIER | POST /transfers/ (wizard)    | Нет — кладовщик   |

> **Серые строки** (COURIER_LOAD, COURIER_RETURN, LOSS_WRITE_OFF) доступны через `/shifts/` эндпоинты, а не через wizard накладных — они имеют дополнительную бизнес-логику (сверка остатков, инкассация).

---

## 11. Диаграмма движения товаров (HOD полный цикл)

```
VIRTUAL_VENDOR ──FACTORY_RECEIPT──► WAREHOUSE
                                        │
                                   COURIER_LOAD
                                        │
                                        ▼
                                     COURIER ──CLIENT_DELIVERY──► CLIENT
                                        ◄──CLIENT_RETURN───────── CLIENT
                                        │
                                   COURIER_RETURN
                                        │
                                        ▼
                                     WAREHOUSE
                                        │
                         LOSS_WRITE_OFF │
                                        ▼
                                   VIRTUAL_LOSS

Параллельно при CLIENT_DELIVERY:
  Revenue Account ──► Client Account (долг)
  Client Account  ──► Courier Account (CASH оплата)
  Client Account  ──► Card Account   (CARD оплата, PENDING)

При COURIER_RETURN (close_shift):
  Courier Account ──► System Cash Account (инкассация)
```

---

*Spec подготовлен на основе анализа исходного кода бэкенда и фронтенда по состоянию на 2026-03-27.*
