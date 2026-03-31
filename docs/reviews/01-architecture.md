# Code Review: Архитектура и паттерны проектирования

## Краткая оценка

Кодовая база демонстрирует добротную реализацию DDD-модульного монолита с правильно выстроенными слоями и хорошей защитой целостности данных через PG-триггеры. Вместе с тем имеется ряд структурных нарушений и накопленного технического долга, который при росте команды может стать источником труднообнаруживаемых ошибок.

---

## Проблемы и замечания

### [CRITICAL] Проблема 1: Дублирование регистрации роутера в backoffice

**Файл:** `src/api/v1/backoffice/__init__.py`, строки 44-52

**Описание:** `system_router` зарегистрирован дважды на одном и том же префиксе `/system`:

```python
backoffice.include_router(
    system_router, prefix="/system", tags=["Backoffice | System"]
)
backoffice.include_router(
    system_router, prefix="/system", tags=["Backoffice | System"]  # ДУБЛЬ
)
```

FastAPI не выбросит ошибку, но все роуты `/backoffice/system/*` будут обработаны дважды при матчинге, а в OpenAPI schema появятся дублирующиеся операции. При наличии side-эффектов (например, сидирование) дублирование маршрута может привести к двойному выполнению.

**Рекомендация:** Удалить вторую строку регистрации `system_router`.

---

### [HIGH] Проблема 2: Две несогласованные схемы заказа (Order schemas)

**Файлы:**

- `src/application/order/schemas.py` — черновые схемы (устаревшие)
- `src/modules/orders/schemas.py` — реальные схемы, используемые в API

**Описание:** В `src/application/order/schemas.py` существуют `OrderCreate`, `OrderResponse` и `OrderDeliveryCompleteRequest`, которые **не используются ни в одном роутере**. Реальные роуты (backoffice, client, courier) импортируют схемы из `src/modules/orders/schemas.py`. Это создаёт ложную точку входа для разработчиков: при поиске схемы заказа они могут найти устаревшую версию.

Например, `application/order/schemas.py:OrderCreate` имеет поле `is_initial_tara: bool`, а реальная `modules/orders/schemas.py:OrderCreate` имеет `capitalize_missing_tara: bool` — разные имена, разная семантика.

**Рекомендация:** Удалить или явно пометить `src/application/order/schemas.py` как устаревший файл (`# DEPRECATED: используй src/modules/orders/schemas.py`). При желании — вынести в отдельный `_legacy.py` и не экспортировать.

---

### [HIGH] Проблема 3: Нарушение принципа "Service возвращает DTO, а не ORM-объекты"

**Файлы:**

- `src/modules/orders/services.py` (все методы `BaseOrderService`)
- `src/modules/users/services.py` (методы `UserService`)
- `src/application/client/service.py` (метод `ClientService.get_clients()`)

**Описание:** Согласно CLAUDE.md: `Service returns: Frozen DTOs only — never expose ORM objects to consumers`. Однако `BaseOrderService` возвращает ORM-объекты `Order` напрямую. `UserService.get_couriers()` возвращает `dict[str, Any]` с ORM-объектами `Account` и `Inventory` внутри:

```python
items.append({
    ...
    "account": account,      # ORM-объект Account, не DTO
    "inventory": inventory,  # ORM-объект Inventory, не DTO
})
```

`CatalogService` — единственный, кто правильно конвертирует в `ProductDTO`. Этот паттерн не распространён на остальные модули.

**Рекомендация:** Ввести frozen DTO для `Order`, `User`, `Courier`, `Client` или как минимум согласовать конвенцию: либо Pydantic-схема с `from_orm`, либо frozen dataclass. Критично для modules/orders, так как ORM-объекты с `lazy="raise"` могут вызывать ошибки при сериализации вне сессии.

---

### [HIGH] Проблема 4: Двойное открытие UoW в `ClientService.create_client_inventory()`

**Файл:** `src/application/client/service.py`, строки 69-86

**Описание:**

```python
async def create_client_inventory(self, client_id, data):
    async with self.uow:            # <-- UoW #1 открывается и закрывается
        ...
        await self.uow.commit()
                                    # <-- здесь UoW уже закрыт!
    return await self.get_client(client_id)   # get_client() открывает UoW #2
```

Это работает только потому, что `BaseSQLAlchemyUoW` создаёт новую сессию каждый раз в `__aenter__`. Однако паттерн "открыл UoW, закрыл, затем вызвал метод, который снова открывает UoW" — нарушение принципа единой транзакционной границы и потенциальный источник видимости неакомиченных данных в промежутке. Аналогичная ситуация в `create_client()` (строки 36-67): после `commit()` вызывается `get_client()` в отдельном `async with`.

**Рекомендация:** Либо объединить в одну транзакцию (передать сессию), либо явно документировать намеренность двух транзакций.

---

### [MEDIUM] Проблема 5: Модуль `orders` прямо импортирует из `inventory`, нарушая DDD-границы

**Файл:** `src/modules/orders/services.py`, строки 11-22

**Описание:** `BaseOrderService` (в модуле `orders`) напрямую импортирует из `src/modules/inventory/`:

```python
from src.modules.inventory.enums import InventoryType, TransferStatus, TransferType
from src.modules.inventory.exceptions import InventoryNotFoundError, InsufficientStockError
```

И из `src/modules/users/enums`:

```python
from src.modules.users.enums import Role
```

И напрямую из `src/modules/finances/enums`:

```python
from src.modules.finances.enums import TransactionStatus
```

Это нарушает принцип изоляции bounded context. Модуль `orders` знает о внутренностях `inventory`, `users` и `finances`. Должен существовать только один "тонкий" публичный фасад (как у `catalog/public.py`), а не прямые импорты из internals модулей.

**Рекомендация:** Создать `public.py` для модулей `inventory`, `finances`, `users` аналогично `catalog/public.py`. Ограничить межмодульные импорты только через фасад. Использовать `pytest-archon` (он уже в зависимостях, но не используется) для автоматической проверки.

---

### [MEDIUM] Проблема 6: `UserService` (модульный) выполняет кросс-доменные операции

**Файл:** `src/modules/users/services.py`

**Описание:** `UserService.register_client()` создаёт: User + Identity + Account (finances) + Inventory (inventory) + StockTransfer + StockTransaction — всё в одном методе уровня модуля. Это противоречит архитектурному решению иметь `ClientService` в application layer именно для кросс-доменных операций. `UserUnitOfWork` тоже включает `StockTransferRepository`, `StockTransferItemRepository`, `StockTransactionRepository` — репозитории из модуля `inventory` напрямую доступны в модуле `users`.

**Рекомендация:** `register_client()` с созданием тары должен жить только в `ClientService` (application layer). `UserService` (modules/users) должен знать только о `users` и `identities`. Счёт клиента (`Account`) можно создавать в модуле `users` только при наличии публичного интерфейса `finances`.

---

### [MEDIUM] Проблема 7: `init.py` — прямая работа с ORM-объектами, обход репозиториев и сервисов

**Файл:** `src/core/init.py`

**Описание:** `init_data()` напрямую создаёт `User`, `Account`, `Identity`, `Inventory` через `session.add()` без использования репозиториев или сервисов. Это нарушает DRY и создаёт скрытое дублирование бизнес-логики (например, правила создания identity дублируются с `UserService.register_client()`). Core layer импортирует ORM-модели напрямую из `src/infrastructure/database/models`.

**Рекомендация:** Вынести инициализационную логику в `UserService`/`ClientService`. Core layer (`src/core/`) не должен знать об ORM-моделях — это нарушение dependency direction.

---

### [MEDIUM] Проблема 8: `BaseService` открывает UoW внутри каждого метода — риск вложенных контекстов

**Файл:** `src/common/service.py`

**Описание:** Каждый метод `BaseService` (`get`, `get_multi`, `add`, `update`, `archive`, `delete`) открывает `async with self.uow`. Если подкласс вызывает `super().get()` внутри собственного `async with self.uow`, то UoW откроется дважды. `BaseSQLAlchemyUoW` не защищён от вложенных вызовов `__aenter__` — каждый вызов создаёт новую сессию, затирая `self._session`. Это означает, что первая открытая сессия будет потеряна.

В `BaseOrderService.add_product_to_order()` сначала вызывается `self.catalog_service.get_by_ids()` (открывает UoW CatalogService), затем `async with self.uow` — это разные UoW, поэтому здесь всё безопасно. Но подклассы должны быть осторожны.

**Рекомендация:** Добавить защиту от реентерабельности в `BaseSQLAlchemyUoW.__aenter__`, либо явно документировать, что UoW не реентерабелен.

---

### [LOW] Проблема 9: `capitalize_tara_for_sale` открывает UoW вне сервиса напрямую из роутера

**Файл:** `src/api/v1/backoffice/orders.py`, строки 180-203

**Описание:**

```python
async with capitalize_service.uow:
    client_inv = await capitalize_service.uow.inventories.get_client_inventory(...)
```

Роутер (API-слой) напрямую управляет UoW сервиса. Это нарушает принцип "API-слой только вызывает сервис, не управляет транзакцией". Бизнес-логика получения инвентаря протекла в роутер.

**Рекомендация:** Переместить логику поиска инвентаря клиента внутрь `CapitalizeTaraService.capitalize_tara()` или создать отдельный метод сервиса.

---

### [LOW] Проблема 10: `create_warehouse_sale` жёстко устанавливает `payment_method = CASH`

**Файл:** `src/modules/orders/services.py`, строка 405

**Описание:**

```python
new_order = await self.uow.orders.add({
    ...
    "payment_method": PaymentMethod.CASH,   # Всегда CASH, игнорирует DTO
    ...
})
```

`WarehouseSaleCreate` не содержит поля `payment_method`, поэтому метод самостоятельно ставит CASH. Это не задокументировано явно и нарушает принцип единственной ответственности — бизнес-правило "warehouse sale всегда CASH" закопано в деталях реализации.

**Рекомендация:** Либо добавить `payment_method` в `WarehouseSaleCreate` (опциональный с дефолтом CASH), либо вынести константу в именованный бизнес-класс и добавить комментарий.

---

### [LOW] Проблема 11: Inconsistent сигнатура `BaseService` — 4-й generic параметр `DTOType` не используется

**Файл:** `src/common/service.py`, строки 13-18

**Описание:** `BaseService[ModelType, CreateSchemaType, UoWType, DTOType = object]` объявляет `DTOType`, но ни один из методов базового класса его не использует. `CatalogService` правильно передаёт `DTOType = ProductDTO`, но наследованные методы (`get`, `get_multi` и т.д.) всё равно возвращают `ModelType` (ORM-объект), а не `DTOType`. Это приводит к несоответствию: декларируется контракт "вернём DTO", а возвращается ORM.

**Рекомендация:** Либо реализовать `@abstractmethod _to_dto(model: ModelType) -> DTOType` и использовать его в базовых методах, либо убрать `DTOType` из сигнатуры `BaseService`, раз он не используется базовым классом.

---

### [LOW] Проблема 12: `src/core/exceptions.py` импортирует `fastapi.status`

**Файл:** `src/core/exceptions.py`, строка 4

**Описание:**

```python
from fastapi import status
```

`src/core/` — нижний слой, который должен быть независим от фреймворка. Импорт FastAPI в core создаёт зависимость нижнего слоя от инфраструктурного. При замене FastAPI на другой фреймворк придётся менять core.

**Рекомендация:** Использовать числовые константы (`404`, `400` и т.д.) или создать `src/core/http_status.py` с простым перечислением статусов без зависимости от FastAPI.

---

## Обновления документации

| Файл                                    | Что исправлено                                                                                                                                                                                                                                                                        |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/codebase/02-domain-modules.md`    | `IdentityRepository`: добавлены методы `get_local_by_user_or_none`, `get_by_id_and_provider`, `get_by_user_and_provider`                                                                                                                                                              |
| `docs/codebase/02-domain-modules.md`    | `UserUnitOfWork`: уточнён тип `transactions` (StockTransactionRepository), добавлено примечание об отсутствии `FinancialTransactionRepository`                                                                                                                                        |
| `docs/codebase/02-domain-modules.md`    | `BaseOrderUnitOfWork`: уточнены типы всех репозиториев (Stock vs Financial)                                                                                                                                                                                                           |
| `docs/codebase/02-domain-modules.md`    | `BaseOrderService`: добавлены недокументированные методы (`complete_pickup`, `get_order_with_details`, `add_product_to_order`, `remove_product_from_order`, `assign_courier`, `update_status`, `search_orders`, `get_client_history`, `get_courier_tasks`, `check_tara_availability`) |
| `docs/codebase/02-domain-modules.md`    | FSM-таблица переходов: исправлена — `NEW -> ASSIGNED` не через FSM-таблицу, а через `assign_courier()`. `PICKUP_COMPLETED` — только через `complete_pickup()`                                                                                                                         |
| `docs/codebase/03-application-layer.md` | `OrderUnitOfWork`: уточнены типы репозиториев и добавлено отличие от `BaseOrderUnitOfWork`                                                                                                                                                                                            |
| `docs/codebase/03-application-layer.md` | Order Schemas: добавлено предупреждение об устаревших схемах в `application/order/schemas.py` vs реальных в `modules/orders/schemas.py`                                                                                                                                               |
| `docs/codebase/03-application-layer.md` | Диаграмма зависимостей: уточнено расположение `BaseOrderService` (modules, не application)                                                                                                                                                                                            |

---

## Итоговые рекомендации

1. **Немедленно:** Удалить дублирующуюся регистрацию `system_router` в `src/api/v1/backoffice/__init__.py` (Проблема 1).

2. **Приоритет 1:** Ввести `public.py` фасады для модулей `inventory`, `users`, `finances` по образцу `catalog/public.py`. Активировать `pytest-archon` для автоматического контроля dependency direction (Проблема 5).

3. **Приоритет 1:** Переместить кросс-доменную логику `UserService.register_client()` в `ClientService` или создать общий внутренний хелпер. `UserUnitOfWork` не должен включать инвентарные репозитории (Проблема 6).

4. **Приоритет 2:** Удалить/пометить устаревшие схемы в `src/application/order/schemas.py`. Использовать только схемы из `src/modules/orders/schemas.py` (Проблема 2).

5. **Приоритет 2:** Перенести логику роутера `capitalize_tara_for_sale` в метод сервиса. API-слой не должен управлять UoW напрямую (Проблема 9).

6. **Приоритет 3:** Ввести DTO-конвертацию для заказов и пользователей по образцу `ProductDTO`, либо чётко задокументировать, что Pydantic-схемы с `from_attributes=True` выполняют роль DTO (Проблема 3).

7. **Приоритет 3:** Заменить `from fastapi import status` в `src/core/exceptions.py` на числовые константы (Проблема 12).

8. **Приоритет 4:** Написать тесты через `pytest-archon` на dependency direction (уже в deps — просто не используется). Добавить тест на отсутствие прямых импортов между модулями минуя фасад.
