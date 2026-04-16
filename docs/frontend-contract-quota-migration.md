# Миграция фронтенда: Кредитные лимиты → Квоты по продуктам

> **Дата:** 2026-04-16
> **Бэкенд коммит:** `71cf441` (ветка `main`)
> **Статус:** Бэкенд готов — ожидается синхронизация фронтенда

---

## Краткое описание изменений

Ранее договоры (Contract) ограничивали B2B заказы **финансовым кредитным лимитом** (`credit_limit` / `credit_used`).
Теперь ограничение по **квотам на каждый продукт**: в прайс-листе договора для каждого товара указывается
максимальное количество единиц (`quantity`) и сколько уже использовано (`quantity_used`).

**Что это значит для UI:**

- ❌ Убрать все поля "Кредитный лимит" / "Использованный кредит" из карточки договора
- ✅ В прайс-листе договора — показывать квоту и остаток по каждому продукту
- ✅ В заказе — вместо `reserved_credit_amount: number|null` теперь `quantities_reserved: boolean`

---

## 1. Удалённые поля (BREAKING)

Эти поля **больше НЕ возвращаются** бэкендом и **не принимаются** в запросах.
Все обращения к ним нужно удалить из фронтенда.

| Схема / Эндпоинт                  | Удалённое поле           | Тип           |
| --------------------------------- | ------------------------ | ------------- |
| `ContractCreate` (запрос)         | `credit_limit`           | `int`         |
| `ContractUpdate` (запрос)         | `credit_limit`           | `int \| null` |
| `ContractResponse` (ответ)        | `credit_limit`           | `int`         |
| `ContractResponse` (ответ)        | `credit_used`            | `int`         |
| `ContractBrief` (внутри заказа)   | `credit_limit`           | `int`         |
| `ContractBrief` (внутри заказа)   | `credit_used`            | `int`         |
| `ContractSummary` (карточка)      | `credit_limit`           | `int`         |
| `ContractSummary` (карточка)      | `credit_used`            | `int`         |
| `OrderResponse` (ответ)           | `reserved_credit_amount` | `int \| null` |
| `DashboardTotals` (дашборд)       | `total_b2b_credit_used`  | `int`         |
| `B2BContractDebt` (задолженности) | `credit_limit`           | `int`         |
| `B2BContractDebt` (задолженности) | `credit_used`            | `int`         |
| `B2BContractDebt` (задолженности) | `total_exposure`         | `int`         |
| `B2BContractDebt` (задолженности) | `limit_utilization_pct`  | `float`       |
| `B2BContractDebtsResponse`        | `total_exposure`         | `int`         |

---

## 2. Новые поля (NEW)

| Схема / Эндпоинт            | Новое поле            | Тип    | Описание                                      |
| --------------------------- | --------------------- | ------ | --------------------------------------------- |
| `PriceItemCreate` (запрос)  | `quantity`            | `int`  | Макс. кол-во единиц. `0` = без ограничений    |
| `PriceItemResponse` (ответ) | `quantity`            | `int`  | Макс. кол-во единиц. `0` = без ограничений    |
| `PriceItemResponse` (ответ) | `quantity_used`       | `int`  | Использовано единиц                           |
| `OrderResponse` (ответ)     | `quantities_reserved` | `bool` | `true` если квоты зарезервированы по договору |

---

## 3. Переименования / изменения (MODIFIED)

| Схема                      | Поле              | Было                              | Стало               |
| -------------------------- | ----------------- | --------------------------------- | ------------------- |
| `B2BContractDebtsResponse` | `total_exposure`→ | `total_exposure: int`             | `total_debt: int`   |
| `B2BContractDebt`          | `due_date_status` | `"ok" \| "overdue" \| "no_limit"` | `"ok" \| "overdue"` |

---

## 4. Затронутые эндпоинты

### 4.1. Договоры (Backoffice)

**`POST /api/v1/backoffice/contracts/`** — Создание договора

```diff
 {
   "number": "HOD-2025-001",
   "start_date": "2025-01-01",
-  "credit_limit": 5000000,
   "payment_due_days": 30,
   "legal_name": "ООО Аква Корп",
   "inn": "123456789"
 }
```

**`PUT /api/v1/backoffice/contracts/{id}/prices/{product_id}`** — Установка цены и квоты

```diff
 // Запрос
 {
   "price": 15000,
+  "quantity": 100    // 0 = без ограничений (по умолчанию)
 }

 // Ответ
 {
   "id": "...",
   "contract_id": "...",
   "product_id": "...",
   "price": 15000,
+  "quantity": 100,
+  "quantity_used": 42,
   "is_active": true,
   "created_at": "...",
   "updated_at": "..."
 }
```

### 4.2. Заказы

**`POST /api/v1/client/orders/`** и все `GET /orders/...`

```diff
 // OrderResponse
 {
   "id": "...",
   "payment_method": "contract",
   "contract_id": "...",
-  "reserved_credit_amount": 30000,
+  "quantities_reserved": true,
   ...
 }
```

### 4.3. Дашборд финансов

**`GET /api/v1/backoffice/finances/dashboard`**

```diff
 // DashboardTotals
 {
   "total_revenue": 1000000,
   "total_cash_in_hand": 500000,
   "total_card_pending": 200000,
   "total_client_debt": 300000,
   "total_courier_cash": 50000,
   "total_b2b_settled_debt": 150000,
-  "total_b2b_credit_used": 80000
 }
```

### 4.4. B2B Задолженности

**`GET /api/v1/backoffice/finances/b2b-debts`**

```diff
 // B2BContractDebtsResponse
 {
-  "total_exposure": 500000,
+  "total_debt": 500000,
   "items": [
     {
       "client_id": "...",
       "client_name": "ООО Аква",
       "contract_id": "...",
       "contract_number": "HOD-2025-001",
       "account_balance": -250000,
-      "credit_limit": 5000000,
-      "credit_used": 300000,
-      "total_exposure": 550000,
-      "limit_utilization_pct": 11.0,
-      "due_date_status": "no_limit"
+      "due_date_status": "ok"
     }
   ]
 }
```

---

## 5. Новые коды ошибок

Три **новых** ошибки, которые фронтенд должен обрабатывать:

### `QUANTITY_LIMIT_EXCEEDED` (HTTP 400)

Клиент пытается заказать больше единиц, чем разрешено по договору.

```json
{
  "error": {
    "code": "QUANTITY_LIMIT_EXCEEDED",
    "message": "Квота по продукту в договоре будет превышена. Уменьшите количество или обратитесь к менеджеру.",
    "details": {
      "contract_id": "...",
      "product_id": "...",
      "quantity_limit": 100,
      "quantity_used": 90,
      "requested": 15,
      "available": 10
    }
  }
}
```

**Рекомендация для UI:** Показать пользователю сообщение вида:
> «Вы можете заказать ещё **{available}** ед. этого товара (из {quantity_limit})»

### `PRODUCT_NOT_IN_CONTRACT` (HTTP 400)

Клиент пытается заказать товар, которого нет в прайс-листе договора.

```json
{
  "error": {
    "code": "PRODUCT_NOT_IN_CONTRACT",
    "message": "Данный продукт отсутствует в прайс-листе договора. Заказ по договору возможен только для товаров из договорного прайс-листа.",
    "details": {
      "contract_id": "...",
      "product_id": "..."
    }
  }
}
```

**Рекомендация для UI:** При оформлении заказа CONTRACT — фильтровать каталог,
показывая **только товары из прайс-листа договора**.

### `PRICE_ITEM_HAS_USAGE` (HTTP 409)

Администратор пытается удалить позицию прайс-листа или уменьшить квоту ниже использованного.

```json
{
  "error": {
    "code": "PRICE_ITEM_HAS_USAGE",
    "message": "Невозможно удалить позицию прайс-листа: есть активные заказы с этим продуктом.",
    "details": {
      "contract_id": "...",
      "product_id": "...",
      "quantity_used": 42
    }
  }
}
```

### Удалённый код ошибки

| Старый код              | Замена                    |
| ----------------------- | ------------------------- |
| `CREDIT_LIMIT_EXCEEDED` | `QUANTITY_LIMIT_EXCEEDED` |

---

## 6. Изменения в бизнес-логике

### До (кредитный лимит)

```
Договор: credit_limit = 5 000 000, credit_used = 2 000 000
→ Доступно: 3 000 000 сум
→ При создании заказа: credit_used += total_amount
→ При отмене: credit_used -= total_amount
→ При доставке: credit_used -= total_amount
```

### После (квоты по продуктам)

```
Прайс-лист:
  Вода 19л: price=15000, quantity=100, quantity_used=42 → осталось 58 ед.
  Стакан:   price=500,   quantity=0,   quantity_used=7  → без ограничений

→ При создании заказа: quantity_used += quantity (для каждого товара)
→ При отмене: quantity_used -= quantity (для каждого товара)
→ При доставке: ничего не меняется (квота безвозвратно использована)
```

**Ключевое отличие:** Квота не возвращается после доставки — она "потрачена навсегда".
Возврат только при отмене заказа.

---

## 7. Рекомендации по UI

### 7.1. Карточка договора (Backoffice)

**Убрать:**
- Поле "Кредитный лимит"
- Прогресс-бар "Использовано X из Y"

**Добавить:**
- В таблице прайс-листа — колонки «Квота» и «Использовано»
- Если `quantity = 0` → показывать «∞» или «Без лимита»
- Если `quantity > 0` → показывать прогресс: `quantity_used / quantity`

### 7.2. Форма добавления позиции прайс-листа

```
┌──────────────────────────────────┐
│ Цена: [15 000] сум               │
│ Квота: [100] ед.  (0 = безлим.)  │
│            [Сохранить]           │
└──────────────────────────────────┘
```

### 7.3. Оформление заказа (клиент B2B)

- Показывать **только товары из прайс-листа договора**
- Рядом с каждым товаром — «Доступно: {available} ед.» (если `quantity > 0`)
- При ошибке `QUANTITY_LIMIT_EXCEEDED` → подсветить поле quantity с подсказкой

### 7.4. Список заказов

- Заменить отображение `reserved_credit_amount` (сумма) на иконку/бейдж
  `quantities_reserved: true/false`
- Или просто убрать — поле `quantities_reserved` больше для внутренней логики

### 7.5. Дашборд финансов

- Убрать виджет/карточку "B2B кредит в работе" (`total_b2b_credit_used`)
- В таблице B2B задолженностей — убрать колонки: "Кредитный лимит",
  "Кредит использован", "Общий риск", "% использования"
- Переименовать `total_exposure` → `total_debt`

---

## 8. Чеклист для фронтенда

- [ ] Удалить `credit_limit` из формы создания/редактирования договора
- [ ] Удалить `credit_limit` / `credit_used` из карточки договора
- [ ] Добавить `quantity` в форму добавления/редактирования позиции прайс-листа
- [ ] Показывать `quantity` / `quantity_used` в таблице прайс-листа
- [ ] Обработать ошибку `QUANTITY_LIMIT_EXCEEDED` (показать доступный остаток)
- [ ] Обработать ошибку `PRODUCT_NOT_IN_CONTRACT` (фильтровать каталог)
- [ ] Обработать ошибку `PRICE_ITEM_HAS_USAGE` (запрет удаления позиции)
- [ ] Заменить `reserved_credit_amount` на `quantities_reserved` в списке заказов
- [ ] Обновить дашборд: убрать `total_b2b_credit_used`
- [ ] Обновить B2B задолженности: убрать кредитные поля, `total_exposure` → `total_debt`
- [ ] Убрать значение `"no_limit"` из обработки `due_date_status`
- [ ] Обновить TypeScript типы/интерфейсы под новые схемы
