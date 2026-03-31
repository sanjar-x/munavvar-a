# Backoffice Order Flow

**Дата:** 2026-03-31  
**Аудитория:** Frontend разработчик backoffice  
**Scope:** только flow заказа на доставку, от создания до `delivered`

---

## 1. Что строим на фронте

Backoffice для диспетчера/оператора должен покрывать такой сценарий:

1. Найти клиента
2. Выбрать адрес доставки
3. Собрать корзину
4. Проверить/оприходовать тару при необходимости
5. Создать заказ
6. При необходимости отредактировать заказ, пока он `new`
7. Назначить курьера
8. Провести заказ по статусам `assigned -> in_transit -> arrived -> delivered`
9. Показать итоговые движения товара в карточке заказа

---

## 2. Основной FSM заказа

### Статусы delivery-заказа

| Статус | Значение | Что означает |
|---|---|---|
| `new` | Новый | Заказ создан, но курьер еще не назначен |
| `assigned` | Назначен | Курьер назначен |
| `in_transit` | В пути | Курьер взял заказ в работу |
| `arrived` | На месте | Курьер прибыл к клиенту |
| `delivered` | Доставлен | Доставка завершена, складские и финансовые проводки выполнены |
| `cancelled` | Отменен | Заказ отменен |

### Разрешенные переходы

| Откуда | Куда |
|---|---|
| `new` | `assigned`, `cancelled` |
| `assigned` | `in_transit`, `cancelled` |
| `in_transit` | `arrived`, `cancelled` |
| `arrived` | `delivered`, `cancelled` |

### Что важно для UI

- Нельзя перескакивать через шаги. `new -> delivered` вернет `409 INVALID_ORDER_STATUS`.
- Менять состав заказа можно только в статусе `new`.
- Назначать или менять курьера можно только в статусах `new` и `assigned`.
- Для frontend не использовать `PATCH /status` как основной путь. Использовать явные endpoint-ы:
  - `PATCH /in-transit`
  - `PATCH /arrived`
  - `PATCH /delivered`

---

## 3. Данные, которые нужны до создания заказа

### 3.1 Клиенты

#### Список клиентов

```http
GET /api/v1/backoffice/clients/?skip=0&limit=50&search=99890
```

Использовать для:
- таблицы клиентов
- поиска по имени/телефону

#### Карточка клиента

```http
GET /api/v1/backoffice/clients/{client_id}
```

Использовать для:
- выбора адреса доставки
- отображения текущих остатков клиента
- просмотра прошлых заказов

Из ответа фронту важны:
- `id`
- `username`
- `phone`
- `inventories[]`
- `account.balance`

Адрес доставки для заказа берется из `client.inventories[].id`.

### 3.2 Каталог товаров

```http
GET /api/v1/backoffice/catalog/?skip=0&limit=100
GET /api/v1/backoffice/catalog/?product_type=WATER
```

Использовать для:
- выбора воды, тары, оборудования
- отображения названия и цены товара в корзине

### 3.3 Курьеры

```http
GET /api/v1/backoffice/couriers/?page=1&size=50&search=
```

Использовать для:
- select списка курьеров при назначении заказа

---

## 4. Создание заказа

### Шаг 1. Собрать корзину

Payload для создания заказа:

```json
{
  "items": [
    {
      "product_id": "uuid",
      "quantity": 2
    }
  ],
  "payment_method": "cash",
  "client_inventory_id": "uuid",
  "capitalize_missing_tara": true
}
```

### Шаг 2. Опционально проверить тару до создания

Если на экране хотите показать оператору предупреждение до создания заказа:

```http
POST /api/v1/backoffice/orders/check-tara
```

```json
{
  "items": [
    {
      "product_id": "uuid",
      "quantity": 2
    }
  ],
  "client_inventory_id": "uuid"
}
```

Ответ:

```json
{
  "can_order": false,
  "shortages": [
    {
      "product_id": "uuid",
      "product_name": "Water 19L",
      "returnable_item_id": "uuid",
      "required": 2,
      "available": 0,
      "deficit": 2
    }
  ]
}
```

Логика UI:
- если `can_order=true`, можно создавать заказ без предупреждения
- если `can_order=false`, показать дефицит тары
- если оператор согласен, отправить `capitalize_missing_tara: true`

### Шаг 3. Создать заказ

```http
POST /api/v1/backoffice/orders/?clientId={client_id}
```

После успешного ответа:
- сохранить `order.id`
- сразу перейти на деталку заказа
- желательно сделать `GET /api/v1/backoffice/orders/{orderId}` и строить экран уже из каноничного ответа

---

## 5. Деталка заказа

### Получить заказ

```http
GET /api/v1/backoffice/orders/{orderId}
```

Основные поля ответа:

```json
{
  "id": "uuid",
  "client_id": "uuid",
  "client": {
    "id": "uuid",
    "username": "Client Name",
    "phone": "+998..."
  },
  "client_inventory_id": "uuid",
  "client_inventory": {
    "id": "uuid",
    "name": "Дом",
    "type": "CLIENT",
    "is_active": true
  },
  "courier_id": "uuid",
  "courier": {
    "id": "uuid",
    "username": "Courier Name",
    "phone": "+998..."
  },
  "status": "assigned",
  "payment_method": "cash",
  "total_amount": 40000,
  "capitalization_applied": true,
  "sale_type": "delivery",
  "items": [
    {
      "id": "uuid",
      "product_id": "uuid",
      "product": {
        "id": "uuid",
        "name": "Water 19L",
        "price": 20000
      },
      "quantity": 2,
      "unit_price": 20000,
      "total": 40000
    }
  ],
  "stock_transfers": []
}
```

### Что рисовать на деталке

- шапка заказа: `id`, `status`, `payment_method`, `total_amount`
- клиент: `client.username`, `client.phone`
- адрес: `client_inventory.name`
- курьер: `courier.username`, `courier.phone`
- флаг `capitalization_applied`
- таблица `items`
- timeline или блок движений по `stock_transfers`

---

## 6. Редактирование заказа, пока он new

### Добавить товар

```http
POST /api/v1/backoffice/orders/{orderId}/items
```

```json
{
  "productId": "uuid",
  "quantity": 1
}
```

### Удалить товар

```http
DELETE /api/v1/backoffice/orders/{orderId}/items/{productId}
```

### Ограничения

- работает только в статусе `new`
- нельзя удалить последнюю позицию, вернется `409 CANNOT_REMOVE_LAST_ITEM`

### Правило UI

Когда статус заказа не `new`:
- скрыть edit action-ы для корзины
- сделать список товаров readonly

---

## 7. Назначение курьера

### Endpoint

```http
PATCH /api/v1/backoffice/orders/{orderId}/assign
```

```json
{
  "courierId": "uuid"
}
```

### Что происходит

- backend ставит `courier_id`
- backend переводит заказ в `assigned`

### Ограничения

- разрешено только для delivery-заказов
- разрешено только в статусах `new` и `assigned`
- если попытаться переназначить заказ после `in_transit`, вернется `409 COURIER_ASSIGNMENT_ERROR`

### Правило UI

- кнопку `Назначить курьера` показывать в `new`
- кнопку `Сменить курьера` показывать только в `assigned`
- в `in_transit`, `arrived`, `delivered` блокировать reassignment

---

## 8. Проведение заказа по шагам доставки

### 8.1 Перевести в in_transit

```http
PATCH /api/v1/backoffice/orders/{orderId}/in-transit
```

Переход:

```text
assigned -> in_transit
```

### 8.2 Перевести в arrived

```http
PATCH /api/v1/backoffice/orders/{orderId}/arrived
```

Переход:

```text
in_transit -> arrived
```

### 8.3 Завершить доставку

```http
PATCH /api/v1/backoffice/orders/{orderId}/delivered
```

Без корректировки фактического состава:

```json
{}
```

С корректировкой фактически доставленных товаров:

```json
{
  "actual_items": [
    {
      "product_id": "uuid",
      "quantity": 1
    }
  ]
}
```

Переход:

```text
arrived -> delivered
```

### Что делает backend на delivered

При `delivered` backend автоматически создает складские движения:

1. `CLIENT_DELIVERY`  
   вода: `courier -> client`

2. `INITIAL_BALANCE`  
   физическая тара: `VIRTUAL_VENDOR -> client`

3. `CLIENT_RETURN`  
   пустая тара: `client -> courier`

То есть после завершения доставки:
- статус заказа меняется на `delivered`
- `stock_transfers` в заказе уже содержат фактические проводки
- остатки клиента и курьера уже обновлены

### Правило UI

После `PATCH /delivered`:
- перезапросить `GET /orders/{id}`
- на деталке показать `stock_transfers`
- заказ становится readonly

---

## 9. Как строить список заказов

### Endpoint

```http
GET /api/v1/backoffice/orders/
```

Поддерживаемые query params:

- `skip`
- `limit`
- `statuses`
- `paymentMethods`
- `courierId`
- `clientId`
- `clientInventoryId`
- `dateFrom`
- `dateTo`
- `minAmount`
- `maxAmount`
- `saleType`

Пример:

```http
GET /api/v1/backoffice/orders/?skip=0&limit=50&statuses=new&statuses=assigned&saleType=delivery
```

### Рекомендуемые табы на frontend

- `New`: `statuses=new`
- `Assigned`: `statuses=assigned`
- `In transit`: `statuses=in_transit`
- `Arrived`: `statuses=arrived`
- `Delivered`: `statuses=delivered`
- `All`: без статуса или набором фильтров

---

## 10. Матрица action-кнопок по статусу

| Статус | Edit items | Assign courier | In transit | Arrived | Delivered |
|---|---|---|---|---|---|
| `new` | yes | yes | no | no | no |
| `assigned` | no | yes | yes | no | no |
| `in_transit` | no | no | no | yes | no |
| `arrived` | no | no | no | no | yes |
| `delivered` | no | no | no | no | no |
| `cancelled` | no | no | no | no | no |

---

## 11. Основные бизнес-ошибки для UI

### При создании

| Код | Когда прилетает |
|---|---|
| `EMPTY_CART` | Корзина пустая |
| `PRODUCTS_UNAVAILABLE` | Товар не найден или недоступен |
| `CLIENT_INVENTORY_NOT_FOUND` | У клиента нет выбранного адреса |
| `INSUFFICIENT_TARA` | Не хватает тары и `capitalize_missing_tara=false` |

### При редактировании

| Код | Когда прилетает |
|---|---|
| `CANNOT_REMOVE_LAST_ITEM` | Попытка удалить последнюю строку |

### При статусных переходах

| Код | Когда прилетает |
|---|---|
| `INVALID_ORDER_STATUS` | Неверный переход, например `new -> delivered` |
| `COURIER_ASSIGNMENT_ERROR` | Смена курьера в неверном статусе |
| `DELIVERY_QUANTITY_EXCEEDED` | В `actual_items` указали больше, чем было заказано |
| `INSUFFICIENT_STOCK` | У курьера не хватает товара для доставки |
| `INVALID_PICKUP_OPERATION` | Delivery endpoint вызвали для warehouse pickup |
| `ORDER_NOT_FOUND` | Заказ не найден |

### Практика для frontend

- для `409` показывать `error.message`
- для `INVALID_ORDER_STATUS` можно дополнительно опираться на `details.allowed_statuses`
- после любой неуспешной статусной мутации желательно рефетчить заказ

---

## 12. Отдельно про warehouse pickup

Этот документ описывает только `sale_type=delivery`.

Для `sale_type=warehouse_pickup` flow другой:
- заказ создается через `POST /api/v1/backoffice/orders/warehouse-sale`
- завершается через `PATCH /api/v1/backoffice/orders/{orderId}/complete-pickup`
- статусы `assigned`, `in_transit`, `arrived`, `delivered` для него не использовать

Поэтому на frontend обязательно проверять:

```text
if order.sale_type !== "delivery":
    не показывать delivery action-кнопки
```

---

## 13. Рекомендуемый frontend flow

### Список

1. `GET /backoffice/orders`
2. Показать фильтры по статусу, клиенту, курьеру, оплате
3. По клику открывать деталку заказа

### Создание

1. `GET /backoffice/clients`
2. `GET /backoffice/clients/{clientId}`
3. `GET /backoffice/catalog`
4. Опционально `POST /backoffice/orders/check-tara`
5. `POST /backoffice/orders?clientId=...`
6. `GET /backoffice/orders/{orderId}`

### Доставка

1. `GET /backoffice/couriers`
2. `PATCH /backoffice/orders/{id}/assign`
3. `PATCH /backoffice/orders/{id}/in-transit`
4. `PATCH /backoffice/orders/{id}/arrived`
5. `PATCH /backoffice/orders/{id}/delivered`
6. `GET /backoffice/orders/{id}`

---

## 14. Что frontend должен считать источником истины

- Источник истины по статусу: `order.status`
- Источник истины по шагам доставки: только explicit endpoint-ы
- Источник истины по адресам клиента: `GET /backoffice/clients/{clientId}`
- Источник истины по итоговым движениям товара: `order.stock_transfers`
- После каждой мутации лучше делать refetch списка и refetch деталки заказа

