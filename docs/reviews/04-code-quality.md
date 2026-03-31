# Code Review: Качество кода и Python best practices

## Краткая оценка

Кодовая база HOD демонстрирует зрелую DDD-архитектуру с чёткими слоями, грамотным использованием SQLAlchemy (нет N+1, `lazy="raise"` + eager load), корректной транзакционной изоляцией через UoW. Основные проблемы — дублирование бизнес-логики (tara checkout повторяется 2+ раза), несколько мест с недостаточной типизацией, и один серьёзный дефект в типе параметра `sale_type`.

---

## Сильные стороны

- **N+1 защита**: все запросы с relationships используют `selectinload` / `joinedload`. Вместо ленивой загрузки — явные опции в каждом repository-методе (см. `OrderRepository._details_options`, `UserRepository.get_couriers_with_details`).
- **PEP 695 generics**: `BaseRepository[ModelType: BaseModel]`, `BaseService[ModelType, CreateSchemaType, UoWType, DTOType]` — корректное использование Python 3.14 generic syntax.
- **Frozen DTOs**: `ProductDTO` — `@dataclass(frozen=True, slots=True)`, защита от мутации на уровне типов. Покрыто тестом `test_catalog_dto.py`.
- **Deadlock protection**: `FOR UPDATE` в репозиториях (`get_inventory_with_balances(with_for_update=True)`, `get_with_details(order_id, with_for_update=True)`). Соответствует требованиям леджерной целостности.
- **FSM валидация**: `_ensure_status_transition_allowed` — classmethod, изолирован, легко тестируется. Блокировка некорректных переходов до записи в БД.
- **UoW pattern**: чёткая изоляция транзакций; `BaseSQLAlchemyUoW.commit()` перехватывает `IntegrityError -> ConflictError` — нет утечки SQLAlchemy-исключений наружу.
- **`UsersDashboardQuery`**: CQRS-стиль, сложные аналитические запросы с `union_all` вынесены в отдельный объект, избегают N+1 через агрегацию на стороне БД.
- **Scoped Inventory**: `_VALID_ROUTES` в `services.py` — маршруты для `TransferType` вынесены в module-level константу с `frozenset`. Валидация маршрутов изолирована.

---

## Проблемы и замечания

### [HIGH] Проблема 1: Ошибочный тип `sale_type` в `search_orders`

**Файл:** `src/modules/orders/services.py`, строка 1263

**Описание:**
```python
async def search_orders(
    self,
    ...
    sale_type: str | None = None,  # <-- НЕВЕРНО
    ...
) -> list[Order]:
```

Параметр `sale_type` принимает `str | None`, тогда как `OrderRepository.search_orders` ожидает `SaleType | None` (строки 131–145 в `repositories.py`). SQLAlchemy передаст строку в `where(self.model.sale_type == sale_type)` — сравнение пройдёт молча, но нарушается контракт. API-роутер передаёт правильный `SaleType` enum (`orders.py`, строка 85), но через слой сервиса тип теряется.

**Рекомендация:**
```python
from src.modules.orders.enums import SaleType

async def search_orders(
    self,
    ...
    sale_type: SaleType | None = None,
    ...
) -> list[Order]:
```

---

### [HIGH] Проблема 2: Дублирование бизнес-логики проверки и оприходования тары

**Файлы:**
- `src/modules/orders/services.py`, строки 163–251 (`create_order`)
- `src/modules/orders/services.py`, строки 340–399 (`create_warehouse_sale`)
- `src/modules/inventory/services.py`, строки 421–509 (`capitalize_deficit`)

**Описание:**
Логика расчёта дефицита тары (поиск `exchange_items`, вычисление `shortages`, оприходование дефицита через `INITIAL_BALANCE`) повторяется с минимальными отличиями в трёх местах. Блок ~40 строк идентичен в `create_order` и `create_warehouse_sale`:

```python
exchange_items = [
    (p, next(i for i in dto.items if i.product_id == p.id))
    for p in products
    if p.returnable_item_id is not None
]
# ... далее цикл shortages с одинаковой структурой
```

Если правила расчёта тары изменятся, придётся менять в трёх местах.

**Рекомендация:** Извлечь в private-метод `_calculate_tara_shortages(products, items, balances) -> list[dict]` и переиспользовать в `create_order` и `create_warehouse_sale`. Переиспользовать `_create_stock_transfer` для оприходования (уже реализован правильно).

---

### [MEDIUM] Проблема 3: Ненадёжная обработка ошибки в `capitalize_tara_for_sale` — `ValueError` вместо доменного исключения

**Файл:** `src/api/v1/backoffice/orders.py`, строки 183–188

**Описание:**
```python
if not client_inv:
    raise ValueError(
        f"Инвентарь клиента {effective_client_id} не найден"
    )
```

`ValueError` — программная ошибка, не доменная. Она не перехватывается глобальным exception handler (он ловит `AppException`), что приведёт к 500-ответу вместо 404. Правильно: `ClientInventoryNotFoundError` или `InventoryNotFoundError`.

**Рекомендация:**
```python
from src.modules.inventory.exceptions import InventoryNotFoundError

if not client_inv:
    raise InventoryNotFoundError(inventory_id=effective_client_id)
```

---

### [MEDIUM] Проблема 4: Двойное открытие UoW в `capitalize_tara_for_sale`

**Файл:** `src/api/v1/backoffice/orders.py`, строки 180–203

**Описание:**
В роутере `capitalize_tara_for_sale` вручную открывается `async with capitalize_service.uow:` для получения инвентаря, затем закрывается, а потом `capitalize_service.capitalize_tara()` открывает новый UoW-контекст. Это два разных соединения с БД, между которыми нет транзакционной гарантии. Если между двумя `async with` инвентарь будет удалён — возникнет race condition.

**Рекомендация:** Перенести логику получения `client_inventory_id` внутрь сервиса `capitalize_tara`, принимая `client_id` напрямую. Роутер не должен управлять транзакциями.

---

### [MEDIUM] Проблема 5: `CapitalizeTaraService.capitalize_tara` возвращает `dict` без типа

**Файл:** `src/modules/inventory/services.py`, строка 370–419

**Описание:**
```python
async def capitalize_tara(
    self,
    dto: CapitalizeTaraRequest,
    created_by_id: uuid.UUID,
) -> dict:  # <-- нет типизации содержимого
```

Возвращаемый тип `dict` скрывает структуру ответа. То же самое у `capitalize_deficit`. Сервисный слой должен возвращать frozen DTO или typed schema, а не сырой `dict`.

**Рекомендация:** Создать `CapitalizeTaraResponse` dataclass/schema с полями `transfer_id: uuid.UUID | None` и `capitalized_items: list[CapitalizeTaraItem]`.

---

### [MEDIUM] Проблема 6: `UserService.get_user_local_identity` — без аннотации возвращаемого типа

**Файл:** `src/modules/users/services.py`, строка 136

**Описание:**
```python
async def get_user_local_identity(self, identity_id: str):
    async with self.uow:
        return await self.uow.users.get_with_identity(...)
```

Нет аннотации возврата. `get_with_identity` возвращает `tuple[User, Identity] | None`, но сигнатура метода скрывает это.

**Рекомендация:**
```python
async def get_user_local_identity(
    self, identity_id: str
) -> tuple[User, Identity] | None:
```

---

### [MEDIUM] Проблема 7: `add_product_to_order` — `updated_order` может быть `Order | None`, но используется без проверки

**Файл:** `src/modules/orders/services.py`, строки 555–560

**Описание:**
```python
updated_order = await self.uow.orders.update(
    order_id, {"total_amount": new_total}
)

await self.uow.commit()
return updated_order  # тип Order, но BaseRepository.update может вернуть None
```

`BaseRepository.update` объявлен как `-> ModelType` (строка 77 в `repository.py`), что само по себе misleading — при отсутствии записи `scalar_one()` бросит исключение, а не вернёт None. Но при параллельном удалении заказа между `get_with_details` и `update` — возникнет непойманное SQLAlchemy-исключение вместо `OrderNotFoundError`.

**Рекомендация:** Явно обернуть в try/except или использовать `scalar_one_or_none()` + проверку в `BaseRepository.update`.

---

### [LOW] Проблема 8: `product_to_dto` принимает `Any` вместо `Product`

**Файл:** `src/modules/catalog/dtos.py`, строка 27

**Описание:**
```python
def product_to_dto(product: Any) -> ProductDTO:
```

Принимает `Any`, что отключает type-checking для аргумента. Функция работает только с ORM `Product`, что должно быть выражено в сигнатуре.

**Рекомендация:**
```python
from src.infrastructure.database.models import Product

def product_to_dto(product: Product) -> ProductDTO:
```

---

### [LOW] Проблема 9: `InventoryRepository.get_couriers_inventory` игнорирует `unique()` — потенциальные дубли

**Файл:** `src/modules/inventory/repositories.py`, строки 110–127

**Описание:**
```python
result = await self.session.execute(query)
return result.scalars().all()
```

Запрос использует `joinedload(self.model.user)`, что при join может создать дублирующиеся строки. Нет вызова `result.unique()`. Другие методы с `joinedload` (например, `get_with_user`) корректно используют `.unique()`.

**Рекомендация:** Добавить `.unique()` перед `.scalars().all()`.

---

### [LOW] Проблема 10: Неоднородный стиль фильтрации в `StockTransferRepository.search_transfers`

**Файл:** `src/modules/inventory/repositories.py`, строки 261–298

**Описание:**
Статус `status` проверяется через `if status:` — это falsy-проверка. `TransferStatus` — StrEnum, все значения truthy, так что `if status:` работает. Но стиль отличается от других мест, где явно пишут `if status is not None:`. Непоследовательность затрудняет чтение.

**Рекомендация:** Использовать `if status is not None:` для всех фильтров в методе.

---

### [LOW] Проблема 11: `UserRepository.get_by_id` — лишний алиас без `selectinload(identities)`

**Файл:** `src/modules/users/repositories.py`, строки 152–156

**Описание:**
```python
async def get_by_id(self, id: uuid.UUID) -> User | None:
    query = select(self.model).where(
        self.model.id == id, self.model.is_active.is_(True)
    )
    return await self.session.scalar(query)
```

Метод `get_by_id` не загружает `identities`, тогда как основной `get()` загружает через `selectinload`. Дублирует функцию `get()` с другим eager-load поведением. Используется только в `ClientService.create_client_inventory` — там потом данные не используются.

**Рекомендация:** Удалить `get_by_id` или явно документировать, что он не загружает relationships. Использовать `get()` повсюду.

---

### [LOW] Проблема 12: `StockTransferService.create_transfer` — однострочные `add` в цикле вместо `add_many`

**Файл:** `src/modules/inventory/services.py`, строки 341–353

**Описание:**
```python
for item in schema.items:
    await self.uow.transfer_items.add({...})
    await self.uow.transactions.add({...})
```

Каждый `add()` выполняет `session.flush()` — один round-trip на каждый item. В `BaseOrderService._create_stock_transfer` правильно используется `add_many()`. Для `StockTransferService` это не критично (мало items в накладной), но непоследовательно.

**Рекомендация:** Переиспользовать `add_many()` для batch-вставки.

---

## Обновления документации

### `docs/codebase/02-domain-modules.md`

1. **`BaseOrderService.check_tara_availability`** — исправлен возвращаемый тип с `TaraCheckResponse` на `dict` (фактически возвращает `{"can_order": bool, "shortages": list}`).
2. **`BaseOrderService.search_orders`** — добавлена заметка о несоответствии типа `sale_type: str | None` вместо `SaleType | None`.

---

## Итоговые рекомендации

1. **[НЕМЕДЛЕННО]** Исправить тип `sale_type: str | None` → `SaleType | None` в `BaseOrderService.search_orders` — это нарушение контракта типов, которое молча принимает невалидные значения.

2. **[НЕМЕДЛЕННО]** Заменить `raise ValueError(...)` на `InventoryNotFoundError` в `capitalize_tara_for_sale` — иначе при пропущенном инвентаре возвращается необработанный 500.

3. **[ПРИОРИТЕТ]** Вынести логику расчёта тара-шортажей в приватный метод `_calculate_tara_shortages` — устранить дублирование между `create_order` и `create_warehouse_sale`.

4. **[ПРИОРИТЕТ]** Убрать управление UoW из роутера `capitalize_tara_for_sale` — перенести получение `client_inventory_id` внутрь `CapitalizeTaraService`.

5. **[РЕФАКТОРИНГ]** Типизировать возвращаемые `dict` в `CapitalizeTaraService` — создать `CapitalizeTaraResponse` schema.

6. **[ТЕХДОЛГ]** Добавить аннотацию возвращаемого типа к `get_user_local_identity`.

7. **[ТЕХДОЛГ]** Добавить `.unique()` в `InventoryRepository.get_couriers_inventory`.

8. **[ТЕХДОЛГ]** Унифицировать `if status is not None:` вместо `if status:` в filter-методах.
