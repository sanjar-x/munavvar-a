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

| TransferType       | Отображение (UZ)        | Цвет    |
|--------------------|-------------------------|---------|
| `FACTORY_RECEIPT`  | Qabul qilish (zavoddan) | Зелёный |
| `COURIER_LOAD`     | Yuklanish               | Зелёный |
| `COURIER_RETURN`   | Qaytarish               | Синий   |
| `CLIENT_DELIVERY`  | Yetkazish               | Красный |
| `CLIENT_RETURN`    | Tara olish              | Синий   |
| `LOSS_WRITE_OFF`   | Hisobdan chiqarish      | Красный |
| `INVENTORY_FINDING`| Topilma                 | Зелёный |
| `INITIAL_BALANCE`  | Boshlang'ich qoldiq     | Серый   |

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

| Метод | Эндпоинт | Описание | Когда |
|-------|----------|----------|-------|
| POST | `/shifts/load-truck` | Загрузка курьера со склада | Утро |
| POST | `/shifts/factory-exchange` | **НОВЫЙ** — Обмен на заводе | После рейса на завод |
| POST | `/shifts/loss` | Списание потерь | В любое время |
| POST | `/shifts/close` | Закрытие смены + инкассация | Вечер |

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
