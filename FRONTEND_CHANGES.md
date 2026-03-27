# Frontend: Изменения в Backend API

**Дата:** 2026-03-27

---

## 1. Единый API накладных (Unified Transfer API)

### Что изменилось

Все операции с товародвижением теперь идут через **один эндпоинт**:

```
POST /api/v1/backoffice/transfers/
```

#### Удалённые эндпоинты (больше не работают!)

| Старый эндпоинт | Замена |
|---|---|
| `POST /shifts/load-truck` | `POST /transfers/` с `type: "COURIER_LOAD"` |
| `POST /shifts/loss` | `POST /transfers/` с `type: "LOSS_WRITE_OFF"` |
| `PUT /transfers/{id}/items` | Удалён — items передаются сразу |
| `POST /transfers/{id}/complete` | Удалён — накладная создаётся сразу COMPLETED |

#### Оставшиеся без изменений

| Эндпоинт | Назначение |
|---|---|
| `GET /transfers/` | Журнал накладных (без изменений) |
| `POST /shifts/factory-exchange` | Обмен курьера на заводе (без изменений) |
| `POST /shifts/close` | Закрытие смены (без изменений) |

---

### Единая схема запроса

```javascript
POST /api/v1/backoffice/transfers/

{
  "type": "COURIER_LOAD",           // Обязательно — тип накладной
  "from_id": "uuid",                // Откуда (необязательно для виртуальных источников)
  "to_id": "uuid",                  // Куда (необязательно для виртуальных получателей)
  "items": [                        // Обязательно — минимум 1 позиция
    { "product_id": "uuid", "quantity": 10 }
  ],
  "reason": "Broken during transport", // Только для LOSS_WRITE_OFF (обязательно)
  "route_sheet_id": "uuid"            // Только для COURIER_LOAD (необязательно)
}
```

#### Правила по полям `from_id` / `to_id`

**Бэкенд сам подставляет виртуальные склады — фронтенд их НЕ передаёт:**

| Тип | from_id | to_id | Что подставит бэкенд |
|---|---|---|---|
| `COURIER_LOAD` | ✅ передать (warehouse) | ✅ передать (courier) | — |
| `COURIER_RETURN` | ✅ передать (courier) | ✅ передать (warehouse) | — |
| `FACTORY_SHIPMENT` | ✅ передать (warehouse) | ✅ передать (factory) | — |
| `FACTORY_RETURN` | ✅ передать (factory) | ✅ передать (warehouse) | — |
| `LOSS_WRITE_OFF` | ✅ передать (warehouse/courier) | ❌ НЕ передавать | `to_id` = VIRTUAL_LOSS |
| `INVENTORY_FINDING` | ❌ НЕ передавать | ✅ передать (warehouse) | `from_id` = VIRTUAL_VENDOR |
| `FACTORY_RECEIPT` | ❌ НЕ передавать | ✅ передать (warehouse/factory) | `from_id` = VIRTUAL_VENDOR |
| `INITIAL_BALANCE` | ❌ НЕ передавать | ✅ передать (warehouse) | `from_id` = VIRTUAL_VENDOR |

> **Главное:** Больше не нужно знать UUID виртуальных складов (VIRTUAL_VENDOR / VIRTUAL_LOSS). Бэкенд сам разберётся.

---

### Новые типы накладных

| Тип | Название (UZ) | Маршрут | Описание |
|---|---|---|---|
| `FACTORY_SHIPMENT` | Zavodga jo'natish | Ombor → Zavod | Отправка товара на завод (пустые бутыли на розлив) |
| `FACTORY_RETURN` | Zavoddan qabul qilish | Zavod → Ombor | Приёмка товара с завода (полная вода) |

---

### Flow для каждой операции

#### 1. Yuklash (Загрузка курьера)

**Форма:** Ombor + Kuryer mashina + Mahsulotlar

```javascript
await createTransfer({
  type: "COURIER_LOAD",
  from_id: warehouseId,        // UUID выбранного склада
  to_id: courierId,            // UUID машины курьера
  items: [{ product_id: "...", quantity: 10 }],
  route_sheet_id: crypto.randomUUID(),  // опционально
}).unwrap();
```

---

#### 2. Tushurib olish (Выгрузка курьера)

**Без изменений.** Используется `POST /shifts/close` с `cash_collected: 0`.

```javascript
await closeShift({
  courier_id: courierUserId,
  returned_inventory: [{ product_id: "...", quantity: 5 }],
  cash_collected: 0,
}).unwrap();
```

---

#### 3. Hisobga qo'shish (Оприходование / Топилма)

**Форма:** Ombor + Mahsulotlar

```javascript
await createTransfer({
  type: "INVENTORY_FINDING",
  to_id: warehouseId,          // только to_id!
  items: [{ product_id: "...", quantity: 3 }],
}).unwrap();
```

> **Было:** 3 вызова (createTransfer → updateItems → complete). **Стало:** 1 вызов.
> **Больше не нужен** `virtualVendorId` — бэкенд подставит сам.

---

#### 4. Hisobdan chiqarish (Списание)

**Форма:** Ombor + Mahsulotlar + Sabab

```javascript
await createTransfer({
  type: "LOSS_WRITE_OFF",
  from_id: warehouseId,        // только from_id!
  items: [{ product_id: "...", quantity: 2 }],
  reason: "Transportda singan",  // обязательно, мин. 3 символа
}).unwrap();
```

> **to_id не передаём** — бэкенд автоматически направит в VIRTUAL_LOSS.

---

#### 5. Boshlang'ich qoldiq (Начальные остатки)

**Форма:** Ombor + Mahsulotlar

```javascript
await createTransfer({
  type: "INITIAL_BALANCE",
  to_id: warehouseId,          // только to_id!
  items: [{ product_id: "...", quantity: 100 }],
}).unwrap();
```

> **Было:** 3 вызова. **Стало:** 1 вызов. Без `virtualVendorId`.

---

#### 6. Zavodga jo'natish (Отправка на завод) — НОВЫЙ

**Форма:** Ombor + Zavod + Mahsulotlar

```javascript
await createTransfer({
  type: "FACTORY_SHIPMENT",
  from_id: warehouseId,        // UUID склада
  to_id: factoryId,            // UUID завода
  items: [{ product_id: "...", quantity: 50 }],
}).unwrap();
```

**Сценарий:** Складовщик грузит пустые бутыли в машину → фиксирует накладную. Машина едет на завод.

---

#### 7. Zavoddan qabul qilish (Приёмка с завода) — НОВЫЙ

**Форма:** Zavod + Ombor + Mahsulotlar

```javascript
await createTransfer({
  type: "FACTORY_RETURN",
  from_id: factoryId,          // UUID завода
  to_id: warehouseId,          // UUID склада
  items: [{ product_id: "...", quantity: 50 }],
}).unwrap();
```

**Сценарий:** Машина вернулась с завода с полной водой → складовщик принимает и фиксирует накладную.

---

#### 8. Zavoddan qabul (Обмен курьера на заводе) — БЕЗ ИЗМЕНЕНИЙ

```javascript
await factoryExchange({
  courier_inventory_id: courierId,
  factory_id: factoryId,
  given_items: [{ product_id: "...", quantity: 10 }],
  received_items: [{ product_id: "...", quantity: 10 }],
}).unwrap();
```

---

### Ответ API (TransferResponse)

Новые поля в ответе:

```json
{
  "id": "uuid",
  "type": "COURIER_LOAD",
  "status": "COMPLETED",
  "from_id": "uuid",
  "to_id": "uuid",
  "created_by_id": "uuid",
  "accepted_by_id": "uuid",
  "items": [{ "product": { "id": "...", "name": "...", "type": "..." }, "quantity": 10 }],
  "reason": null,              // ← НОВОЕ: причина списания (для LOSS_WRITE_OFF)
  "route_sheet_id": null,      // ← НОВОЕ: ID маршрутного листа (для COURIER_LOAD)
  "created_at": "2026-03-27T12:00:00Z"
}
```

---

### Полная таблица операций

| # | Операция (UZ) | Тип | Форма | Endpoint |
|---|---|---|---|---|
| 1 | Yuklash | `COURIER_LOAD` | Ombor + Kuryer + Mahsulotlar | `POST /transfers/` |
| 2 | Tushurib olish | — | Kuryer + Mahsulotlar + Naqd | `POST /shifts/close` |
| 3 | Hisobga qo'shish | `INVENTORY_FINDING` | Ombor + Mahsulotlar | `POST /transfers/` |
| 4 | Hisobdan chiqarish | `LOSS_WRITE_OFF` | Ombor + Mahsulotlar + Sabab | `POST /transfers/` |
| 5 | Boshlang'ich qoldiq | `INITIAL_BALANCE` | Ombor + Mahsulotlar | `POST /transfers/` |
| 6 | Zavodga jo'natish | `FACTORY_SHIPMENT` | Ombor + Zavod + Mahsulotlar | `POST /transfers/` |
| 7 | Zavoddan qabul | `FACTORY_RETURN` | Zavod + Ombor + Mahsulotlar | `POST /transfers/` |
| 8 | Zavod almashinuv | — | Kuryer + Zavod + 2 ro'yxat | `POST /shifts/factory-exchange` |

---

### Что нужно обновить в UI (Warehouse.jsx)

#### Кнопки создания (CREATE_TYPES)

Добавить 2 новые кнопки в массив `CREATE_TYPES`:

```javascript
const CREATE_TYPES = [
  { key: "factory-receipt", label: "Zavoddan qabul", hint: "Zavod → Ombor (kuryer orqali)" },
  { key: "load", label: "Yuklash", hint: "Ombor → Kuryer mashinasi" },
  { key: "unload", label: "Tushurib olish", hint: "Kuryer mashinasi → Ombor" },
  { key: "capitalize", label: "Hisobga qo'shish", hint: "Topilma — yangi tovar kiritish" },
  { key: "loss", label: "Hisobdan chiqarish", hint: "Tovarni hisobdan chiqarish" },
  { key: "initial-balance", label: "Boshlang'ich qoldiq", hint: "Dastlabki qoldiq kiritish" },
  // ⬇ НОВЫЕ
  { key: "factory-shipment", label: "Zavodga jo'natish", hint: "Ombor → Zavod (bo'sh idishlar)" },
  { key: "factory-return", label: "Zavoddan qabul qilish", hint: "Zavod → Ombor (to'la suv)" },
];
```

#### Новые case в handleSubmit

```javascript
case "factory-shipment": {
  if (!warehouseId || !factoryId)
    throw { local: "Ombor va zavodini tanlang" };
  if (v.length === 0) throw { local: "Kamida bitta mahsulot qo'shing" };
  await createTransfer({
    type: "FACTORY_SHIPMENT",
    from_id: warehouseId,
    to_id: factoryId,
    items: v,
  }).unwrap();
  break;
}
case "factory-return": {
  if (!warehouseId || !factoryId)
    throw { local: "Ombor va zavodini tanlang" };
  if (v.length === 0) throw { local: "Kamida bitta mahsulot qo'shing" };
  await createTransfer({
    type: "FACTORY_RETURN",
    from_id: factoryId,
    to_id: warehouseId,
    items: v,
  }).unwrap();
  break;
}
```

#### Форма для factory-shipment / factory-return

Показывать 2 select-а:
- **Ombor** (select из warehousesApi)
- **Zavod** (select из списка инвентарей с type=FACTORY)

И стандартный список товаров (items).

---

### RTK Query — обновлённые хуки

**transfersApi.js:**
```javascript
// Доступные хуки:
useGetTransfersQuery()       // журнал
useCreateTransferMutation()  // единый вызов для всех типов
```

**shiftsApi.js:**
```javascript
// Доступные хуки:
useFactoryExchangeMutation() // обмен на заводе
useCloseShiftMutation()      // закрытие смены
```

**Удалённые хуки (больше не экспортируются!):**
- ~~`useLoadTruckMutation`~~ → использовать `useCreateTransferMutation`
- ~~`useWriteOffLossMutation`~~ → использовать `useCreateTransferMutation`
- ~~`useUpdateTransferItemsMutation`~~ → удалён (items передаются сразу)
- ~~`useCompleteTransferMutation`~~ → удалён (накладная сразу COMPLETED)

---

### Журнал накладных (GET /transfers/)

Ответ теперь включает `reason` и `route_sheet_id`. В таблице журнала можно:
- Показывать `reason` для строк с `type === "LOSS_WRITE_OFF"`
- Показывать новые типы `FACTORY_SHIPMENT` / `FACTORY_RETURN` с соответствующими лейблами

---

*При вопросах — смотри Swagger (`/docs`)*

---

## 2. Удалены TransferType


### 7.4 Изменения в UI — Модалка создания заказа (Orders.jsx)

#### Шаг 1: Добавить переключатель режима продажи

В модалке создания заказа добавить **сегментированный переключатель** сверху:

```
┌─────────────────────────────────┐
│  [🚗 Yetkazish]  [🏢 Skladdan]  │   ← сегментированный контрол
└─────────────────────────────────┘
```

- `"Yetkazish"` (Доставка) — текущий flow, по умолчанию
- `"Skladdan sotish"` (Со склада) — новый flow


---

#### Шаг 2: Режим "Skladdan sotish" — что меняется в форме

**Левая панель (каталог товаров):** Без изменений — товары выбираются так же.

**Правая панель — меняется:**

| Поле           | Режим "Yetkazish"                   | Режим "Skladdan"                                       |
| -------------- | ----------------------------------- | ------------------------------------------------------ |
| Mijoz (Клиент) | Обязательный combobox               | **Опциональный** combobox + чекбокс "Anonim sotish"    |
| Manzil (Адрес) | Select из inventories клиента       | **Скрыт**                                              |
| Ombor (Склад)  | Скрыт                               | **Новый select** — выбор склада                        |
| To'lov turi    | cash/card/contract                  | **Скрыт** (всегда cash)                                |
| Tara checkbox  | "Mijoz taralarini hisobga kiritish" | **"Tara qabul qilish"** (оприходовать тару покупателя) |


**Важно:** Все 3 вызова последовательны. Если шаг 1 или 2 упал — не продолжать.

---

#### Шаг 4: Выбор тары для оприходования

Когда чекбокс "Tara qabul qilish" включен, показать отдельный мини-список **только тарных позиций** из каталога (фильтр `product.type === 'container'`):


Для каждой тары — степпер количества (как в основном каталоге). Эти `taraItems` передаются в `capitalize-tara`, а **не** в основной заказ.

---

### 7.5 Изменения в UI — Таблица заказов

#### 7.5.1 Фильтр по типу продажи

Добавить dropdown-фильтр рядом с фильтром оплаты:

| Значение           | Label (UZ)           |
| ------------------ | -------------------- |
| *пусто*            | Hammasi (все)        |
| `delivery`         | Yetkazish (доставка) |
| `warehouse_pickup` | Skladdan (со склада) |


#### 7.5.2 Новый статус в таблице

В маппинг статусов добавить:


#### 7.5.3 Колонка "Курьер" для pickup-заказов

Для `sale_type === 'warehouse_pickup'` вместо курьера показывать:
- Текст: `"Skladdan"` (или имя склада)
- Не показывать inline-dropdown назначения курьера

#### 7.5.4 Колонка "Статус" для pickup-заказов

Для `sale_type === 'warehouse_pickup'` в inline-dropdown статуса:
- **Не показывать** статусы `assigned`, `in_transit`, `arrived`, `delivered`
- Показывать только: `new`, `pickup_completed`, `cancelled`

---

### 7.6 Изменения в UI — Детальная модалка заказа

Для `sale_type === 'warehouse_pickup'`:
- Показать строку `"Turi": "Skladdan sotish"`
- Показать `"Ombor": <имя склада>` (вместо или рядом с "Manzil")
- Скрыть строку "Kuryer" (или показать `"—"`)

---

### 7.7 Итого — полный UX Flow

```
┌─ Сотрудник открывает Orders ──────────────────────────────────┐
│                                                                │
│  Клик "Yaratish" → модалка                                     │
│                                                                │
│  ┌─ Переключатель: [Yetkazish] / [Skladdan] ──────────┐       │
│  │                                                      │       │
│  │  Если "Skladdan":                                    │       │
│  │    1. Выбрать склад (из warehousesApi)               │       │
│  │    2. Набрать товары в каталоге                       │       │
│  │    3. Если нужно — включить "Tara qabul qilish"     │       │
│  │       и указать количество принесённой тары          │       │
│  │    4. Если зарегистрированный клиент — выбрать       │       │
│  │       Если аноним — оставить "Anonim sotish" ☑       │       │
│  │    5. Клик "Sotish"                                  │       │
│  │                                                      │       │
│  │  Backend (автоматически, 3 вызова):                  │       │
│  │    → capitalize-tara (если тара включена)            │       │
│  │    → warehouse-sale (создать заказ)                   │       │
│  │    → complete-pickup (завершить и списать)            │       │
│  │                                                      │       │
│  │  Toast: "Sotildi!" ✅                                │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                │
│  В таблице заказов появляется строка:                          │
│  │ Skladdan berildi │ Skladdan │ 125 000 │ Naqd │              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```


---

*При вопросах — смотри Swagger