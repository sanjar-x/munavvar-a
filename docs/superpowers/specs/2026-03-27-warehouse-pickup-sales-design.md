# Warehouse Pickup Sales (Продажа со склада за наличку)

**Date:** 2026-03-27
**Status:** Approved

## Summary

Новый функционал продажи товаров напрямую со склада за наличные без участия курьера. Поддержка как зарегистрированных клиентов, так и анонимных покупателей через системного walk-in пользователя.

## Requirements

| Параметр         | Решение                                                      |
| ---------------- | ------------------------------------------------------------ |
| Кто продаёт      | Любой сотрудник с правами (backoffice, scope `ORDERS_EDIT`)  |
| Покупатель       | Зарегистрированный клиент ИЛИ анонимный (walk-in)            |
| Анонимный клиент | Единый системный "Walk-in" пользователь (`WALKIN_USER_ID`)   |
| Тара             | Обязательный обмен, проверка баланса даже для walk-in        |
| Деньги           | Revenue -> Client -> Cash (центральная касса), обе COMPLETED |
| Статус заказа    | Отдельный `PICKUP_COMPLETED`                                 |
| Товарный поток   | Warehouse -> Client напрямую (без курьера)                   |

---

## 1. Data Model

### Новые enum-значения

```python
# orders/enums.py
class SaleType(enum.StrEnum):
    DELIVERY = "delivery"
    WAREHOUSE_PICKUP = "warehouse_pickup"

class OrderStatus(enum.StrEnum):
    ...
    PICKUP_COMPLETED = "pickup_completed"
```

```python
# inventory/enums.py
class TransferType(enum.StrEnum):
    ...
    WAREHOUSE_SALE = "WAREHOUSE_SALE"
    WAREHOUSE_TARA_RETURN = "WAREHOUSE_TARA_RETURN"
```

### Изменения в модели Order

```python
class Order:
    ...
    sale_type: Mapped[str] = mapped_column(
        String, default=SaleType.DELIVERY, server_default="delivery"
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inventories.id"), nullable=True
    )
```

- `sale_type` — default `DELIVERY` для обратной совместимости
- `warehouse_id` — склад-источник, заполняется только для `WAREHOUSE_PICKUP`
- `courier_id` — остаётся nullable, для pickup не заполняется

### Системный Walk-in пользователь (seed)

```
WALKIN_USER_ID    = UUID("00000000-0000-0000-0000-000000000002")
User              → role=CLIENT_B2C, username="walk-in", phone="00000000002"
Identity          → provider=LOCAL, provider_identity_id="00000000002"
Inventory         → type=CLIENT, name="Самовывоз", user_id=WALKIN_USER_ID
Account           → type=CLIENT, name="Счёт анонимных покупок"
```

### Валидация маршрутов трансферов

```python
ALLOWED_ROUTES[TransferType.WAREHOUSE_SALE] = (
    frozenset({InventoryType.WAREHOUSE}),
    frozenset({InventoryType.CLIENT}),
)
ALLOWED_ROUTES[TransferType.WAREHOUSE_TARA_RETURN] = (
    frozenset({InventoryType.CLIENT}),
    frozenset({InventoryType.WAREHOUSE}),
)
```

---

## 2. Order Flow

### Жизненный цикл статусов

```
Доставка:   NEW -> ASSIGNED -> IN_TRANSIT -> ARRIVED -> DELIVERED
Самовывоз:  NEW -> PICKUP_COMPLETED
```

Для `sale_type=WAREHOUSE_PICKUP` промежуточные статусы (ASSIGNED, IN_TRANSIT, ARRIVED, DELIVERED) запрещены.

### Создание заказа

Расширение `OrderCreate` схемы:

```python
class OrderCreate(BaseModel):
    items: list[OrderItemCreate]
    payment_method: PaymentMethod
    client_inventory_id: uuid.UUID
    capitalize_missing_tara: bool = False
    sale_type: SaleType = SaleType.DELIVERY
    warehouse_id: uuid.UUID | None = None
```

Валидация:
- `sale_type=WAREHOUSE_PICKUP` -> `warehouse_id` обязателен, `payment_method` только `CASH`
- `sale_type=DELIVERY` -> `warehouse_id` игнорируется

### Поток для walk-in (анонимная продажа)

```
1. POST /warehouse-sale/capitalize-tara    VIRTUAL_VENDOR -> Walk-in inventory
2. POST /warehouse-sale                    Создание заказа (тара-чек пройдёт)
3. PATCH /{orderId}/complete-pickup        Выдача + финансы
```

### Поток для зарегистрированного клиента

```
1. POST /warehouse-sale?clientId=xxx       Создание заказа (тара на балансе)
2. PATCH /{orderId}/complete-pickup        Выдача + финансы
```

---

## 3. Stock Transfers & Financial Settlement

### _handle_warehouse_pickup()

При переходе в `PICKUP_COMPLETED` создаёт:

```
1. WAREHOUSE_SALE:        Warehouse -> Client inventory   [заказанные товары]
2. WAREHOUSE_TARA_RETURN: Client inventory -> Warehouse   [пустая тара по returnable_item_id]
```

- Источник товара: `order.warehouse_id`
- Проверка остатков на складе (с `FOR UPDATE` блокировкой)
- Тара вычисляется через `product.returnable_item_id` (как в delivery)

### _process_pickup_settlement()

```
1. Revenue -> Client account   (COMPLETED)  "Задолженность за заказ (самовывоз)"
2. Client  -> Cash account     (COMPLETED)  "Оплата наличными на складе"
```

### Итоговый баланс

- Склад: -N воды, +N пустых бутылей
- Client/Walk-in inventory: 0 (вода пришла/ушла, тара пришла/ушла)
- Revenue: -сумма (выручка)
- Cash: +сумма (наличные в кассе)
- Client account: 0 (долг создан и погашен)

---

## 4. API Endpoints

### Новые эндпоинты (backoffice)

```
POST   /api/v1/backoffice/orders/warehouse-sale
  Body: { warehouse_id, items, client_id? }
  - client_id не передан -> WALKIN_USER_ID
  - sale_type=WAREHOUSE_PICKUP автоматически
  - payment_method=CASH автоматически
  - Возвращает Order (status=NEW)
  Scope: ORDERS_EDIT

POST   /api/v1/backoffice/orders/warehouse-sale/capitalize-tara
  Body: { warehouse_id, items: [{product_id, quantity}], client_id? }
  - Оприходование тары от покупателя
  - client_id не передан -> walk-in inventory
  - VIRTUAL_VENDOR -> Client inventory (INITIAL_BALANCE)
  Scope: ORDERS_EDIT

PATCH  /api/v1/backoffice/orders/{orderId}/complete-pickup
  - Переводит в PICKUP_COMPLETED
  - Запускает _handle_warehouse_pickup()
  - Валидация: order.sale_type == WAREHOUSE_PICKUP
  Scope: ORDERS_EDIT
```

### Изменения в существующих эндпоинтах

- `GET /api/v1/backoffice/orders/` — новый query-параметр `sale_type` для фильтрации
- Клиентские и курьерские API не затрагиваются

---

## 5. Migration

Alembic-миграция:
1. Добавить колонки `sale_type` (default="delivery") и `warehouse_id` (nullable) в таблицу `orders`
2. FK constraint: `warehouse_id -> inventories.id`
3. Seed: создать walk-in user, identity, inventory, account

---

## 6. Files to Modify/Create

### Modify
- `src/modules/orders/enums.py` — SaleType enum, PICKUP_COMPLETED status
- `src/modules/orders/models.py` — sale_type, warehouse_id fields
- `src/modules/orders/schemas.py` — OrderCreate extension, new DTOs
- `src/modules/orders/services.py` — _handle_warehouse_pickup, _process_pickup_settlement, status validation
- `src/modules/inventory/enums.py` — WAREHOUSE_SALE, WAREHOUSE_TARA_RETURN transfer types
- `src/modules/inventory/services.py` — ALLOWED_ROUTES update
- `src/api/v1/backoffice/orders.py` — new endpoints
- `src/core/constants.py` — WALKIN_USER_ID
- `src/core/init.py` — seed walk-in user

### Create
- `alembic/versions/xxxx_add_warehouse_pickup.py` — migration
