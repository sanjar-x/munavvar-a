# Frontend: Изменения в Backend API

**Дата:** 2026-03-27

---

## 1. Новый тип инвентаря: `FACTORY`

`InventoryType` теперь содержит:

```
FACTORY         — Завод (отдельный от склада)
WAREHOUSE       — Склад
COURIER         — Машина курьера
CLIENT          — Клиент
VIRTUAL_LOSS    — Системный (списание)
VIRTUAL_VENDOR  — Системный (оприходование)
```

**Что поменять на фронте:**
- В селектах инвентарей учитывать тип `FACTORY`
- В таблице накладных `from_id` / `to_id` могут ссылаться на завод — нужно отображать имя
- Если есть маппинг `InventoryType → иконка/цвет`, добавить `FACTORY`

---

## 2. Удалены TransferType

Убраны из enum:
- ~~`PURCHASE`~~
- ~~`PRODUCTION`~~
- ~~`WAREHOUSE_TRANSFER`~~

**Что поменять на фронте:**
- Убрать из select при создании накладной (wizard Step 1)
- Убрать из фильтров, если есть
- Убрать из маппинга `TransferType → label/цвет`

Актуальные типы:

| TransferType        | Отображение (UZ)        | Цвет    |
| ------------------- | ----------------------- | ------- |
| `FACTORY_RECEIPT`   | Qabul qilish (zavoddan) | Зелёный |
| `COURIER_LOAD`      | Yuklanish               | Зелёный |
| `COURIER_RETURN`    | Qaytarish               | Синий   |
| `CLIENT_DELIVERY`   | Yetkazish               | Красный |
| `CLIENT_RETURN`     | Tara olish              | Синий   |
| `LOSS_WRITE_OFF`    | Hisobdan chiqarish      | Красный |
| `INVENTORY_FINDING` | Topilma                 | Зелёный |
| `INITIAL_BALANCE`   | Boshlang'ich qoldiq     | Серый   |

---

## 3. Новый эндпоинт: `POST /api/v1/backoffice/shifts/factory-exchange`

**Бизнес-сценарий:** Завсклад фиксирует обмен на заводе — курьер сдал пустые бутыли, забрал полные.

### Запрос

```json
POST /api/v1/backoffice/shifts/factory-exchange

{
  "courier_inventory_id": "uuid — машина курьера",
  "factory_id": "uuid — инвентарь завода (тип FACTORY)",
  "given_items": [
    { "product_id": "uuid — пустая тара", "quantity": 100 }
  ],
  "received_items": [
    { "product_id": "uuid — полная вода", "quantity": 95 }
  ]
}
```

### Ответ

```json
// Успех: HTTP 200
true

// Ошибки:
// 404 — INVENTORY_NOT_FOUND (курьер или завод не найден)
// 409 — INSUFFICIENT_STOCK (у курьера нет столько товара для сдачи)
//       { "error_code": "INSUFFICIENT_STOCK", "details": { "shortages": { "<product_id>": N } } }
```

### Что происходит на бэкенде

Одна кнопка завсклада создаёт **3 накладные атомарно**:

```
① COURIER_RETURN:  Курьер → Завод    [given_items]      — пустые сданы
② FACTORY_RECEIPT: V_VENDOR → Завод   [received_items]   — полные поступили
③ COURIER_LOAD:   Завод → Курьер     [received_items]    — полные загружены
```

Все три видны в журнале накладных (`GET /transfers/`).

### Требуется `INVENTORY_WRITE` scope (роль: Admin, Storekeeper)

---

## 4. Поле `type` добавлено в баланс продуктов

`ProductSimpleResponse` (используется в балансах складов, транспортов, накладных) теперь включает `type`:

**Было:**
```json
{ "id": "uuid", "name": "Вода 19Л" }
```

**Стало:**
```json
{ "id": "uuid", "name": "Вода 19Л", "type": "water" }
```

Значения: `water`, `container`, `equipment`

**Где используется:**
- `GET /warehouses/{id}` → `balances[].product.type`
- `GET /transports/{id}` → `balances[].product.type`
- `GET /transfers/` → `items[].product.type`

**Что поменять на фронте:**
- В таблице остатков колонка "Turi" теперь берётся из `product.type` (раньше не было)
- Маппинг: `water` → "Suv", `container` → "Idish", `equipment` → "Jihozlar"

---

## 5. Полная карта API shifts

| Метод | Эндпоинт                   | Описание                    | Когда                |
| ----- | -------------------------- | --------------------------- | -------------------- |
| POST  | `/shifts/load-truck`       | Загрузка курьера со склада  | Утро                 |
| POST  | `/shifts/factory-exchange` | **НОВЫЙ** — Обмен на заводе | После рейса на завод |
| POST  | `/shifts/loss`             | Списание потерь             | В любое время        |
| POST  | `/shifts/close`            | Закрытие смены + инкассация | Вечер                |

---

## 6. Полный цикл рейса на завод (UX)

```
Шаг 1: Завсклад → "Загрузить курьера"
        POST /shifts/load-truck
        { warehouse_id, courier_inventory_id, items: [пустые бутыли] }

Шаг 2: Курьер едет на завод, обменивает пустые на полные

Шаг 3: Завсклад → "Обмен на заводе"
        POST /shifts/factory-exchange
        { courier_inventory_id, factory_id, given_items: [пустые], received_items: [полные] }

Шаг 4: Завсклад → "Закрыть смену"
        POST /shifts/close
        { courier_id, returned_inventory: [полные], cash_collected: 0 }
```

---

*При вопросах — смотри Swagger: `/docs#/shifts`*

---

## 7. Продажа со склада (Warehouse Pickup Sales)

**Дата:** 2026-03-27

**Бизнес-сценарий:** Клиент приходит на склад, приносит пустую тару, покупает воду за наличку — без курьера.

---

### 7.1 Новые поля в OrderResponse

```json
{
  "id": "uuid",
  "sale_type": "delivery",
  "warehouse_id": null,
  "status": "new",
  ...
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `sale_type` | `"delivery"` \| `"warehouse_pickup"` | Тип продажи. Для всех старых заказов — `"delivery"` |
| `warehouse_id` | `uuid \| null` | ID склада (только для `warehouse_pickup`) |

**Новый статус заказа:**

| Код | Label (UZ) | Цвет |
|-----|-----------|------|
| `pickup_completed` | Skladdan berildi | Зелёный |

**Новые типы накладных:**

| TransferType | Отображение (UZ) | Цвет |
|---|---|---|
| `WAREHOUSE_SALE` | Skladdan sotish | Зелёный |
| `WAREHOUSE_TARA_RETURN` | Tara qabul qilish | Синий |

---

### 7.2 Новые API эндпоинты

#### 7.2.1 Оприходование тары покупателя

```
POST /api/v1/backoffice/orders/warehouse-sale/capitalize-tara?clientId={uuid}
```

Если `clientId` не передан — используется системный Walk-in клиент (анонимная продажа).

**Запрос:**
```json
{
  "warehouse_id": "uuid — ID склада",
  "items": [
    { "product_id": "uuid — ID тары (пустая бутыль)", "quantity": 5 }
  ]
}
```

**Ответ (201):**
```json
{
  "transfer_id": "uuid",
  "capitalized_items": [
    { "product_id": "uuid", "quantity": 5 }
  ]
}
```

**Ошибки:**
- `404` — `INVENTORY_NOT_FOUND` (инвентарь клиента не найден)

---

#### 7.2.2 Создание заказа на самовывоз

```
POST /api/v1/backoffice/orders/warehouse-sale?clientId={uuid}
```

Если `clientId` не передан — анонимная продажа (Walk-in).

**Запрос:**
```json
{
  "warehouse_id": "uuid",
  "items": [
    { "product_id": "uuid — вода", "quantity": 5 }
  ],
  "capitalize_missing_tara": false
}
```

**Ответ (201):** Стандартный `OrderResponse` с:
- `sale_type: "warehouse_pickup"`
- `warehouse_id: "uuid"`
- `status: "new"`
- `payment_method: "cash"` (всегда)
- `courier_id: null` (всегда)

**Ошибки:**
- `409` — `INSUFFICIENT_TARA` (недостаточно тары, если `capitalize_missing_tara=false`)
- `409` — `PRODUCTS_UNAVAILABLE`
- `409` — `EMPTY_CART`

---

#### 7.2.3 Подтверждение выдачи (завершение продажи)

```
PATCH /api/v1/backoffice/orders/{orderId}/complete-pickup
```

**Запрос:** Без тела (пустой)

**Ответ:** `OrderResponse` с `status: "pickup_completed"`

**Что происходит на бэкенде:**
1. Проверка остатков на складе
2. `WAREHOUSE_SALE`: Склад → Клиент (товар)
3. `WAREHOUSE_TARA_RETURN`: Клиент → Склад (пустая тара)
4. Финансовая проводка: Revenue → Client → Cash (обе COMPLETED)

**Ошибки:**
- `404` — `ORDER_NOT_FOUND`
- `409` — `INVALID_PICKUP_OPERATION` (заказ не самовывоз или не в статусе `new`)
- `409` — `INSUFFICIENT_STOCK` (на складе нет товара)

---

#### 7.2.4 Фильтрация заказов по типу продажи

```
GET /api/v1/backoffice/orders/?saleType=warehouse_pickup
```

Новый query-параметр `saleType`: `"delivery"` | `"warehouse_pickup"` | пусто (все)

---

### 7.3 RTK Query — новые эндпоинты для ordersApi.js

```javascript
// В ordersApi.js добавить:

// Оприходование тары покупателя
capitalizeTaraForSale: builder.mutation({
  query: ({ clientId, body }) => ({
    url: `/api/v1/backoffice/orders/warehouse-sale/capitalize-tara${
      clientId ? `?clientId=${clientId}` : ''
    }`,
    method: 'POST',
    body,
  }),
}),

// Создание заказа на самовывоз
createWarehouseSale: builder.mutation({
  query: ({ clientId, body }) => ({
    url: `/api/v1/backoffice/orders/warehouse-sale${
      clientId ? `?clientId=${clientId}` : ''
    }`,
    method: 'POST',
    body,
  }),
  invalidatesTags: [{ type: 'Orders', id: 'LIST' }],
}),

// Подтверждение выдачи
completePickup: builder.mutation({
  query: (orderId) => ({
    url: `/api/v1/backoffice/orders/${orderId}/complete-pickup`,
    method: 'PATCH',
  }),
  invalidatesTags: (result, error, orderId) => [
    { type: 'Orders', id: orderId },
    { type: 'Orders', id: 'LIST' },
  ],
}),
```

Также обновить `searchOrders` — добавить `saleType` в params:
```javascript
searchOrders: builder.query({
  query: ({ ..., saleType }) => ({
    url: '/api/v1/backoffice/orders/',
    params: { ..., saleType },
  }),
  ...
}),
```

---

### 7.4 Изменения в UI — Модалка создания заказа (Orders.jsx)

#### Шаг 1: Добавить переключатель режима продажи

В модалке создания заказа добавить **сегментированный переключатель** сверху:

```
┌─────────────────────────────────┐
│  [🚗 Yetkazish]  [🏢 Skladdan] │   ← сегментированный контрол
└─────────────────────────────────┘
```

- `"Yetkazish"` (Доставка) — текущий flow, по умолчанию
- `"Skladdan sotish"` (Со склада) — новый flow

**State:**
```javascript
const [saleMode, setSaleMode] = useState('delivery') // 'delivery' | 'warehouse_pickup'
```

При переключении — сбрасывать форму (очищать выбранные товары, клиента, склад).

---

#### Шаг 2: Режим "Skladdan sotish" — что меняется в форме

**Левая панель (каталог товаров):** Без изменений — товары выбираются так же.

**Правая панель — меняется:**

| Поле | Режим "Yetkazish" | Режим "Skladdan" |
|------|---|---|
| Mijoz (Клиент) | Обязательный combobox | **Опциональный** combobox + чекбокс "Anonim sotish" |
| Manzil (Адрес) | Select из inventories клиента | **Скрыт** |
| Ombor (Склад) | Скрыт | **Новый select** — выбор склада |
| To'lov turi | cash/card/contract | **Скрыт** (всегда cash) |
| Tara checkbox | "Mijoz taralarini hisobga kiritish" | **"Tara qabul qilish"** (оприходовать тару покупателя) |

**Новый flow правой панели для "Skladdan":**

```
┌──────────────────────────────────┐
│  ☐ Anonim sotish                 │  ← чекбокс, по умолчанию ВКЛ
│                                  │
│  Mijoz: [поиск клиента ▾]       │  ← скрыт, если "Anonim" включен
│                                  │
│  Ombor: [Основной склад    ▾]   │  ← новый select (useGetWarehousesQuery)
│                                  │
│  ─── Tara ───────────────────    │
│  ☑ Tara qabul qilish            │  ← чекбокс (оприходовать тару)
│    Suv idishi 19L: [5] [-][+]   │  ← ввод количества тары (если включен)
│                                  │
│  ─── Jami ───────────────────    │
│  💰 125 000 so'm                 │
│                                  │
│  [ Sotish ]                      │  ← кнопка "Продать"
└──────────────────────────────────┘
```

---

#### Шаг 3: Логика кнопки "Sotish" (Продать)

```javascript
async function handleWarehouseSale() {
  try {
    // 1. Если тара включена — сначала оприходуем
    if (acceptTara && taraItems.length > 0) {
      await capitalizeTaraForSale({
        clientId: isAnonymous ? null : selectedClientId,
        body: {
          warehouse_id: selectedWarehouseId,
          items: taraItems, // [{product_id, quantity}]
        },
      }).unwrap()
    }

    // 2. Создаём заказ
    const order = await createWarehouseSale({
      clientId: isAnonymous ? null : selectedClientId,
      body: {
        warehouse_id: selectedWarehouseId,
        items: selectedItems,
        capitalize_missing_tara: false, // тару уже оприходовали выше
      },
    }).unwrap()

    // 3. Сразу подтверждаем выдачу
    await completePickup(order.id).unwrap()

    toast.success('Sotildi!') // "Продано!"
    setCreateOpen(false)
    resetForm()

  } catch (err) {
    if (err?.data?.error_code === 'INSUFFICIENT_TARA') {
      toast.error('Mijozda yetarli tara yo\'q')
    } else if (err?.data?.error_code === 'INSUFFICIENT_STOCK') {
      toast.error('Omborda yetarli tovar yo\'q')
    } else {
      toast.error('Xatolik yuz berdi')
    }
  }
}
```

**Важно:** Все 3 вызова последовательны. Если шаг 1 или 2 упал — не продолжать.

---

#### Шаг 4: Выбор тары для оприходования

Когда чекбокс "Tara qabul qilish" включен, показать отдельный мини-список **только тарных позиций** из каталога (фильтр `product.type === 'container'`):

```javascript
const taraProducts = catalog?.filter(p => p.type === 'container' && p.is_active)
```

Для каждой тары — степпер количества (как в основном каталоге). Эти `taraItems` передаются в `capitalize-tara`, а **не** в основной заказ.

---

### 7.5 Изменения в UI — Таблица заказов

#### 7.5.1 Фильтр по типу продажи

Добавить dropdown-фильтр рядом с фильтром оплаты:

| Значение | Label (UZ) |
|----------|-----------|
| *пусто* | Hammasi (все) |
| `delivery` | Yetkazish (доставка) |
| `warehouse_pickup` | Skladdan (со склада) |

Передавать `saleType` в `useSearchOrdersQuery`.

#### 7.5.2 Новый статус в таблице

В маппинг статусов добавить:

```javascript
const STATUS_MAP = {
  ...existing,
  pickup_completed: { label: 'Skladdan berildi', color: '#22c55e' },
}
```

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

### 7.8 Файлы для изменения

| Файл | Что сделать |
|------|------------|
| `frontend/src/services/ordersApi.js` | Добавить 3 mutation + saleType в searchOrders |
| `frontend/src/pages/Orders.jsx` | Переключатель режима, форма склада, логика продажи |
| `frontend/src/pages/Orders.module.css` | Стили для переключателя, формы склада |

---

*При вопросах — смотри Swagger: `/docs#/Backoffice%20%7C%20Orders`*
