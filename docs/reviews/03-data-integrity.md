# Code Review: Целостность данных и леджеры

## Краткая оценка

Архитектура двойного леджера реализована грамотно: PG-триггеры корректно защищают неизменяемость записей и атомарно обновляют балансы. Обнаружено одно критическое расхождение между ORM-моделью и миграцией (отсутствующий CHECK constraint на `inventory_balances.quantity`), которое оставляет возможность отрицательных складских остатков на уровне БД, а также ряд структурных рисков в бизнес-логике.

---

## Сильные стороны

- **Append-only леджеры** — оба триггера (`update_account_balances`, `update_inventory_balances`) корректно запрещают `DELETE` и ограниченный `UPDATE` через `RAISE EXCEPTION`, гарантируя неизменяемость исторических записей.
- **Deadlock protection** — `update_account_balances` блокирует строки счетов в детерминированном порядке (`ORDER BY id FOR UPDATE`), что исключает взаимоблокировки при параллельных транзакциях.
- **Deadlock protection в инвентаре** — `update_inventory_balances` вставляет строки через `ORDER BY v.inv_id`, синхронизируя порядок блокировок с финансовым триггером.
- **Composite FK на `stock_transactions`** — `ForeignKeyConstraint(["transfer_id", "from_id", "to_id"], ...)` гарантирует, что проводка в леджере строго соответствует маршруту накладной; обойти маршрут через приложение невозможно.
- **Row-level locking** — `get_inventory_with_balances(with_for_update=True)` и `get_with_details(with_for_update=True)` применяются перед всеми критическими проверками (остатки, статус заказа), защищая от race condition при параллельных запросах.
- **Атомарность UoW** — `BaseSQLAlchemyUoW` правильно оборачивает все операции в одну транзакцию: rollback при любом исключении, перехват `IntegrityError -> ConflictError`.
- **Snapshot-цены** — `unit_price` фиксируется в `OrderItem` на момент создания заказа; изменение каталога не ретроспективно влияет на существующие заказы.
- **Валидация маршрутов** — словарь `_VALID_ROUTES` в `services.py` реализован как неизменяемые `frozenset`, что делает маршрутную валидацию декларативной и тестируемой.
- **ondelete="RESTRICT"** — критические FK (счета, инвентарь, пользователи) защищены от случайного каскадного удаления.

---

## Проблемы и замечания

### [CRITICAL] Проблема 1: CHECK constraint `quantity >= 0` объявлен в ORM, но отсутствует в миграции

**Файл:** `src/modules/inventory/models.py`, строки 241-248; `alembic/versions/4a1ea97312ca_init.py`, строки 350-388

**Описание:**
ORM-модель `Balance` объявляет:
```python
CheckConstraint(
    "quantity >= 0",
    name="ck_inventory_balances_quantity_non_negative",
)
```
Однако `create_table("inventory_balances", ...)` в миграции этот constraint не содержит. SQLAlchemy при `create_table` через Alembic не применяет `table_args` автоматически если миграция сгенерирована ранее добавления constraint. В результате в реальной БД ограничение отсутствует.

Последствие: триггер `update_inventory_balances` выполняет `quantity + EXCLUDED.quantity` без проверки результата. При списании товара (from_id получает `-quantity`) баланс может стать отрицательным и PG не заблокирует запись. Ситуация возможна при race condition: два параллельных списания с одного склада пройдут row-level lock только если оба успели прочитать баланс до первого коммита.

**Рекомендация:** Создать новую миграцию Alembic:
```python
op.create_check_constraint(
    "ck_inventory_balances_quantity_non_negative",
    "inventory_balances",
    "quantity >= 0",
)
```
Это критично: без этого constraint единственной защитой от отрицательных остатков является прикладная проверка в `create_transfer()` и `_handle_order_fulfillment()`, которую можно обойти при параллельных запросах.

---

### [HIGH] Проблема 2: Тара при доставке начисляется из VIRTUAL_VENDOR, но балансовая проверка не применяется

**Файл:** `src/modules/orders/services.py`, строки 935-961

**Описание:**
В `_handle_order_fulfillment` физическая тара (полные бутыли) начисляется клиенту через `INITIAL_BALANCE` (VIRTUAL_VENDOR → Client), а затем сразу забирается обратно как пустая (`CLIENT_RETURN`: Client → Courier). Поскольку отправитель — `VIRTUAL_VENDOR`, проверка остатков пропускается (`if from_inventory.type != InventoryType.VIRTUAL_VENDOR`). Это корректно для самого начисления.

Однако **возврат тары** (Client → Courier) выполняется без проверки, что клиент физически имеет достаточное количество пустых бутылей в своём инвентаре. Сценарий: если клиент ранее уже отдал тару через другой канал или у него скорректировали остатки — `CLIENT_RETURN` сгенерирует запись в леджере с отрицательным балансом на стороне клиента. Защита — только `CheckConstraint("quantity >= 0")` на `inventory_balances`, который отсутствует в БД (см. Проблему 1).

**Рекомендация:** Добавить явную проверку остатков тары на стороне клиента перед созданием `CLIENT_RETURN`. Либо устранить Проблему 1, чтобы PG отклонял некорректный результат.

---

### [HIGH] Проблема 3: Финансовое закрытие для CASH-доставки не создаёт транзакцию при отсутствии courier_account

**Файл:** `src/modules/orders/services.py`, строки 1115-1129

**Описание:**
```python
if order.payment_method == PaymentMethod.CASH and order.courier_id:
    courier_account = await self.uow.accounts.get_courier_account(order.courier_id)
    if courier_account:
        financial_txns.append(...)
```
Если у курьера нет финансового счёта (`courier_account` равен `None`), транзакция `Client → Courier` просто не создаётся, и долг клиента (Revenue → Client) остаётся непогашенным без какого-либо исключения или предупреждения в логе. Долг зависает в балансе клиента, выручка не инкассируется.

**Рекомендация:** Заменить тихий пропуск явным исключением:
```python
if not courier_account:
    raise NotFoundError(
        message=f"Финансовый счёт курьера {order.courier_id} не найден",
        error_code="COURIER_ACCOUNT_NOT_FOUND",
    )
```
Создание courier_account должно быть обязательным при онбординге курьера. Это уже гарантируется `CourierService.create_courier`, но добавление защиты на уровне закрытия заказа устраняет риск при ручном создании данных.

---

### [HIGH] Проблема 4: Двойное списание тары при Walk-in cleanup может дать отрицательный баланс

**Файл:** `src/modules/orders/services.py`, строки 1054-1072

**Описание:**
При анонимной (Walk-in) продаже `_handle_warehouse_pickup` делает:
1. `WAREHOUSE_SALE`: Warehouse → WalkIn inventory (вода поступает к Walk-in)
2. `INITIAL_BALANCE`: VIRTUAL_VENDOR → WalkIn inventory (тара поступает к Walk-in)
3. `WAREHOUSE_TARA_RETURN`: WalkIn → Warehouse (тара возвращается обратно)
4. `LOSS_WRITE_OFF`: WalkIn → VIRTUAL_LOSS (вода + тара списываются с Walk-in)

Шаг 4 включает `cleanup_items = sale_items + returnable_items`. Тара уже была отдана на шаге 3, поэтому на шаге 4 у Walk-in инвентаря тары нет. Это создаст запись в `stock_transactions` с `from_id = WalkIn`, уменьшая баланс WalkIn по таре ниже нуля. Единственная защита — отсутствующий DB-constraint (Проблема 1).

**Рекомендация:** Исключить `returnable_items` из `cleanup_items` для Walk-in — тара уже ушла через `WAREHOUSE_TARA_RETURN`. Либо пересмотреть порядок операций: сначала LOSS_WRITE_OFF воды, без тары (она уже в WAREHOUSE_TARA_RETURN).

---

### [MEDIUM] Проблема 5: FSM допускает отмену заказа (`CANCELLED`) после `IN_TRANSIT`

**Файл:** `src/modules/orders/services.py`, строки 48-62

**Описание:**
`_DELIVERY_ALLOWED_TRANSITIONS`:
```python
OrderStatus.IN_TRANSIT: {OrderStatus.ARRIVED, OrderStatus.CANCELLED},
OrderStatus.ARRIVED:    {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
```
Отмена заказа в статусе `IN_TRANSIT` или `ARRIVED` не отменяет уже выданный товар курьеру (накладная `COURIER_LOAD` уже проведена) и не создаёт автоматического обратного перемещения. Товар физически у курьера, в системе — нет фиксации факта возврата. Это оставляет складской баланс курьера несходящимся.

**Рекомендация:** При отмене после `ASSIGNED` и далее требовать явного создания `COURIER_RETURN` накладной, либо создавать её автоматически. В противном случае ограничить `CANCELLED` только статусами `NEW` и `ASSIGNED`.

---

### [MEDIUM] Проблема 6: `_process_financial_settlement` не обрабатывает `CONTRACT` payment method

**Файл:** `src/modules/orders/services.py`, строки 1077-1144

**Описание:**
Метод обрабатывает `CASH` и `CARD`, но для `PaymentMethod.CONTRACT` не создаётся ни одна дополнительная транзакция (только базовая `Revenue → Client`). Это означает, что при оплате по договору долг клиента создаётся, но никакой маршрутизации не происходит. Возможно, это намеренное поведение (долг оплачивается позже), но бухгалтеру нет возможности отличить в леджере "плановый долг по договору" от "забытой оплаты наличными". Также нет системного счёта для CONTRACT (нет `AccountType.CONTRACT`).

**Рекомендация:** Документировать намерение (комментарий в коде) или добавить отдельный `AccountType.CONTRACT` и соответствующую маршрутизацию в `_process_financial_settlement`.

---

### [MEDIUM] Проблема 7: `update_status()` позволяет курьеру доставить любой заказ, к которому он назначен

**Файл:** `src/modules/orders/services.py`, строки 697-741; `src/api/v1/backoffice/orders.py`

**Описание:**
Проверка `requesting_user_id != order.courier_id` выполняется только если передан `requesting_user_id`. В backoffice-эндпоинтах (строка 40-45 `orders.py`) `requesting_user_id` не передаётся — это корректно для администратора. Однако `update_status` вызывается одним и тем же методом для обоих контекстов. Если фронтенд ошибочно вызовет backoffice-роут без авторизации (или с чужим JWT), проверка IDOR не сработает.

**Рекомендация:** Проверка IDOR уже есть в courier-роутах через `requesting_user_id=current_user.id`, что верно. Риск минимален при правильной конфигурации scopes. Убедиться, что backoffice-эндпоинты для статусов (arrived, in_transit, delivered) защищены scope `ORDERS_EDIT`, а courier — `ORDERS_DELIVER`.

---

### [LOW] Проблема 8: `total_amount` в заказе не имеет DB CHECK constraint

**Файл:** `alembic/versions/4a1ea97312ca_init.py`, строки 440-442

**Описание:**
Поле `total_amount BIGINT` в таблице `orders` не имеет `CHECK (total_amount >= 0)`. В методе `remove_product_from_order` используется `max(0, order.total_amount - amount_to_subtract)` (строка 619), что защищает от отрицательных значений на уровне приложения. Однако прямое обновление через SQL или другой сервис может создать отрицательный `total_amount`.

**Рекомендация:** Добавить `CHECK (total_amount >= 0)` в схему таблицы `orders` для защиты на уровне БД.

---

### [LOW] Проблема 9: Транзакция верификации PENDING → COMPLETED не перепроверяет сумму

**Файл:** `src/modules/finances/repositories.py`, строки 127-142

**Описание:**
`change_status` переводит транзакцию из `PENDING` в `COMPLETED` (или `REJECTED`) через прямое изменение поля `status`. PG-триггер при `UPDATE` корректно проверяет, что `amount` и `from_id/to_id` не изменились. Однако нет проверки, что счёт отправителя имеет достаточный баланс для `COMPLETED`. Баланс может уйти в минус (если транзакция была создана, когда баланс был положительным, но к моменту верификации счёт был опустошён другими транзакциями).

**Рекомендация:** Добавить проверку `account.balance >= transaction.amount` перед сменой статуса на `COMPLETED`, либо добавить `CHECK (balance >= 0)` на таблицу `accounts`. Текущий дизайн намеренно допускает отрицательные балансы счетов (долги клиентов — кредитная природа), поэтому для счетов `REVENUE`, `CASH`, `CARD` стоит добавить отдельную логику.

---

### [LOW] Проблема 10: `StockTransfer.order_id` использует `ondelete="RESTRICT"`, блокируя удаление завершённых заказов

**Файл:** `src/modules/inventory/models.py`, строка 117; `alembic/versions/4a1ea97312ca_init.py`, строка 606-608 (implicit через RESTRICT)

**Описание:**
FK `stock_transfers.order_id -> orders.id ondelete="RESTRICT"` означает, что архивирование или физическое удаление заказа (даже `is_active=False`) невозможно, пока существуют связанные накладные. Поскольку накладные append-only и удалять нельзя, заказы фактически не могут быть физически удалены никогда. Это, вероятно, намеренное поведение, но документация это не оговаривает.

**Рекомендация:** Документировать явно: "физическое удаление заказов невозможно из-за RESTRICT-FK со стороны накладных, используйте только soft-delete через `is_active=False`".

---

## Обновления документации

| Файл | Что изменено |
|------|--------------|
| `docs/codebase/02-domain-modules.md` | Добавлено описание `CheckConstraint("quantity >= 0")` на модели `Balance` с примечанием об отсутствии в миграции |
| `docs/codebase/04-infrastructure-db.md` | Добавлено предупреждение об расхождении ORM-модели `Balance` и миграции по `quantity >= 0` check constraint |

Отдельно: при чтении `02-domain-modules.md` обнаружено что секция FSM Orders уже была обновлена (вероятно автоматически) и корректно отражает реальный код (FSM через `_DELIVERY_ALLOWED_TRANSITIONS` и `_PICKUP_ALLOWED_TRANSITIONS`). Проверено соответствие — расхождений нет.

---

## Итоговые рекомендации

1. **[Срочно] Создать миграцию** `op.create_check_constraint("ck_inventory_balances_quantity_non_negative", "inventory_balances", "quantity >= 0")` — без этого единственной защитой от отрицательных остатков является прикладной код, который обходится при race condition.

2. **[Срочно] Исправить Walk-in cleanup** в `_handle_warehouse_pickup` — исключить `returnable_items` из `cleanup_items`, поскольку тара уже ушла через `WAREHOUSE_TARA_RETURN` и повторное списание создаёт отрицательный баланс Walk-in инвентаря.

3. **[Высокий] Добавить явное исключение** при отсутствии `courier_account` в `_process_financial_settlement` вместо тихого пропуска `CLIENT → COURIER` транзакции.

4. **[Высокий] Проверить баланс тары клиента** перед `CLIENT_RETURN` в `_handle_order_fulfillment`, независимо от шага начисления из VIRTUAL_VENDOR.

5. **[Средний] Ограничить отмену заказа** в статусах `IN_TRANSIT` и `ARRIVED` — либо запретить, либо автоматически создавать `COURIER_RETURN` накладную.

6. **[Средний] Добавить CHECK (total_amount >= 0)** на таблицу `orders` в отдельной миграции.

7. **[Средний] Задокументировать поведение CONTRACT** в `_process_financial_settlement` или добавить маршрутизацию через системный счёт.

8. **[Низкий] Добавить интеграционные тесты** на параллельные операции (concurrent orders, double-spend сценарии) — в текущем покрытии таких тестов нет, а именно они верифицируют корректность row-level locking.
