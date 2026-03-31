# Code Review: Тестирование

## Краткая оценка

Тестовая база охватывает критические happy-path сценарии (леджер, FSM, shift-close) и заложила правильные архитектурные паттерны (per-test rollback, monkeypatching session factory). Однако количество тестов невелико — около 25 функций итого — и значительная часть бизнес-логики (client API, finances verification, inventory route validation, concurrent writes) остаётся полностью непокрытой.

---



## Проблемы и замечания


---

### [HIGH] Проблема 2: Нулевое покрытие client-facing API

**Файл:** `src/api/v1/client/orders.py`, `src/api/v1/client/catalog.py`, `src/application/client/service.py`
**Описание:** Весь клиентский API (`/api/v1/client/*`) — логин, каталог, создание заказов, история — не имеет ни одного теста. `ClientService.create_client()`, `ClientService.onboard_client_with_balance()`, `ClientService.create_client_inventory()` — операции, создающие User + Identity + Account + Inventory + Stock transfer в одной транзакции — полностью не проверены.
**Рекомендация:** Написать интеграционный тест `test_client_onboarding.py` с проверкой создания всех 4 сущностей и корректного ответа API.

---

### [HIGH] Проблема 3: FSM покрывает только негативные сценарии, позитивные — только через один путь

**Файл:** `tests/integration/test_order_fsm.py`
**Описание:** `TestOrderFsm` содержит только 4 reject-теста. Переходы `NEW -> CANCELLED`, `ASSIGNED -> CANCELLED`, `PICKUP_COMPLETED` как конечное состояние (не delivered) не тестируются. `_DELIVERY_ALLOWED_TRANSITIONS` и `_PICKUP_ALLOWED_TRANSITIONS` в `src/modules/orders/services.py` содержат логику для CANCELLED, но она ни разу не вызвана в тестах.
**Рекомендация:** Добавить тесты для `CANCEL` переходов на каждом допустимом этапе и проверить финальные статусы как terminal states (нельзя перейти из DELIVERED).

---

### [HIGH] Проблема 4: Не тестируется card/contract payment

**Файл:** `tests/integration/test_delivery_fulfillment.py`, `test_warehouse_pickup.py`
**Описание:** Все интеграционные тесты используют `payment_method: "cash"`. Логика записи в `card_account` и `CARD`-транзакций в `src/modules/orders/services.py` не покрыта тестами. Ошибка в ветке CARD могла бы существовать месяцами.
**Рекомендация:** Добавить параметризацию `@pytest.mark.parametrize("payment_method", ["cash", "card", "contract"])` в хотя бы одном delivery-тесте и проверять `card_account.balance` вместо `cash_account.balance`.

---

### [HIGH] Проблема 5: Финансовая верификация (PENDING -> COMPLETED/REJECTED) не протестирована

**Файл:** `src/modules/finances/`, `src/api/v1/backoffice/finances.py`
**Описание:** Жизненный цикл транзакции (`PENDING -> COMPLETED` бухгалтером) является ключевым бизнес-процессом. `TransactionRepository.change_status()` и логика пересчёта баланса триггером при смене статуса (`update_account_balances()` — ветка "UPDATE status из 'completed'") ни разу не вызываются в тестах. PG-триггер содержит ветку для отката баланса при rejection — эта ветка не покрыта вообще.
**Рекомендация:** Написать тест, создающий PENDING транзакцию, верифицирующий её через backoffice API, и проверяющий изменение баланса.

---

### [MEDIUM] Проблема 6: `data.json` и `data copy.json` — артефакты без использования

**Файл:** `tests/data.json`, `tests/data copy.json`
**Описание:** Оба файла находятся в директории `tests/`, но ни один тест не загружает их. `data copy.json` — явная случайная копия. Файлы засоряют структуру и вводят в заблуждение.
**Рекомендация:** Удалить `data copy.json`. Если `data.json` — snapshot для документации, переместить в `docs/`.

---

### [MEDIUM] Проблема 7: `anyio_backend` — scope мismatch с документацией и потенциальный риск

**Файл:** `tests/conftest.py`, строка 44-46
**Описание:** `anyio_backend` объявлен с `scope="session"`, но `asyncio_default_fixture_loop_scope = "function"` в `pyproject.toml`. Это несоответствие может вызывать предупреждения в будущих версиях pytest-asyncio. Документация (`docs/codebase/05-tests.md`) ошибочно описывала `anyio_backend` как function-scoped (исправлено в рамках этого ревью).
**Рекомендация:** Явно задокументировать мотив session scope (экономия на создании event loop) или изменить на function scope для полной изоляции.

---

### [MEDIUM] Проблема 8: Отсутствие negative path тестов для validation errors

**Файл:** `src/modules/orders/schemas.py`, `src/api/v1/backoffice/orders.py`
**Описание:** Ни один тест не проверяет возврат 422 при невалидном input — пустой корзине, quantity=0, несуществующем product_id, невалидном UUID в path. Pydantic-валидация и FastAPI-обработчик `RequestValidationError` (формат `{"error": {"code": "VALIDATION_ERROR", ...}}`) не проверяются.
**Рекомендация:** Добавить параметризованные тесты негативных сценариев для основных эндпоинтов создания заказа.

---

### [MEDIUM] Проблема 9: Inventory route validation не покрыта

**Файл:** `src/modules/inventory/services.py` (StockTransferService), `tests/integration/test_backoffice_transfer_create.py`
**Описание:** В проекте существуют 9 типов TransferType с конкретными валидными парами `(from_type, to_type)`. Тест `test_backoffice_transfer_create.py` проверяет только INITIAL_BALANCE и COURIER_LOAD. Инвалидный маршрут (например, COURIER -> COURIER или CLIENT -> WAREHOUSE_SALE) не проверяется, как и `RouteLoopError` при `from_id == to_id`.
**Рекомендация:** Добавить тест с невалидным маршрутом (например, COURIER_LOAD из CLIENT inventory) и проверить код ошибки `INVENTORY_TYPE_MISMATCH` или аналог.

---

### [MEDIUM] Проблема 10: pytest-archon установлен, но не используется

**Файл:** `pyproject.toml` (зависимость `pytest-archon>=0.0.7`)
**Описание:** Библиотека `pytest-archon` для проверки архитектурных зависимостей между модулями установлена, но ни одного теста с её использованием нет. Правила, которые она должна охранять (например, "модуль `orders` не импортирует `finances` напрямую, только через UoW"), нигде не формализованы.
**Рекомендация:** Создать `tests/test_architecture.py` с правилами импортов, используя `pytest-archon`.

---

### [LOW] Проблема 11: Нет тестов для конкурентного доступа к леджеру

**Файл:** `src/infrastructure/database/scripts/` (PG triggers)
**Описание:** Ключевой механизм защиты от race conditions — `FOR UPDATE` с `ORDER BY id` для deadlock prevention в `update_account_balances()` — не тестируется ни одним тестом конкурентных записей. Однопоточная природа текущих тестов не нагружает deadlock-защиту.
**Рекомендация:** Написать тест с несколькими `asyncio.gather`-конкурентными INSERT в transactions и проверить, что итоговый баланс корректен.

---

### [LOW] Проблема 12: `test_backoffice_transfer_create` проверяет статус 200, не 201

**Файл:** `tests/integration/test_backoffice_transfer_create.py`, строки 33, 77
**Описание:** POST `/api/v1/backoffice/transfers/` декларирует `status_code=200` по умолчанию (нет `status_code=201` в декораторе). Тесты правильно проверяют 200. Однако по REST-конвенциям создание ресурса должно возвращать 201. Это несоответствие в API, а не в тестах.
**Рекомендация:** Добавить `status_code=201` в `@transfers_router.post("/", ...)` в `src/api/v1/backoffice/transfers.py` и обновить тест.

---

## Обновления документации

Следующие расхождения между документацией и реальным кодом были исправлены в `docs/codebase/05-tests.md`:

1. **Количество тестов `test_auth_service.py`**: исправлено с 8 на **7** (функция `test_local_login_rejects_walkin_account` как 8-й тест не существует — в файле 7 функций).
2. **Количество тестов `test_bootstrap_alembic.py`**: исправлено с 6 на **7** (добавлен `test_returns_none_for_partially_initialized_schema`). Добавлено предупреждение об отсутствии `scripts/bootstrap_alembic.py`.
3. **`test_catalog_public.py`**: расширено описание с 2 пунктов до **7 тестов** (все методы класса `TestCatalogPublicFacade`).
4. **Количество тестов `test_courier_api.py`**: исправлено с 4 на **3** (в файле 3 test-функции, а не 4).
5. **`test_courier_orders_auth.py`**: исправлено описание — не "5 тестов", а **2 параметризованные функции × 5 маршрутов = 10 тест-кейсов**.
6. **`anyio_backend` fixture**: добавлено в список Key Fixtures с корректным `scope="session"` (ранее отсутствовало в документации).
7. **`data.json`**: добавлено примечание "не используется в тестах".

---

## Итоговые рекомендации

### Пример 1: Тест верификации финансовой транзакции

```python
# tests/integration/test_financial_verification.py
from sqlalchemy import select
from src.infrastructure.database.models import Account, Transaction
from src.modules.finances.enums import TransactionStatus
from src.modules.users.enums import Role
from tests.conftest import make_auth_headers
from tests.integration.conftest import credit_account


class TestFinancialVerification:
    async def test_accountant_verifies_pending_transaction(
        self,
        client,
        db_session,
        system_entities,
        admin_user,
    ):
        # Setup: создать PENDING транзакцию
        rev_account = system_entities["revenue_account"]
        cash_account = system_entities["cash_account"]

        txn = Transaction(
            from_id=rev_account.id,
            to_id=cash_account.id,
            amount=10_000,
            status=TransactionStatus.PENDING,
            reason="Test pending",
        )
        db_session.add(txn)
        await db_session.flush()

        # Баланс не изменился (статус PENDING)
        rev_bal = (await db_session.execute(
            select(Account.balance).where(Account.id == rev_account.id)
        )).scalar_one()

        headers = make_auth_headers(admin_user.id, Role.ADMIN)
        # Верифицировать транзакцию
        resp = await client.patch(
            f"/api/v1/backoffice/finances/transactions/{txn.id}/verify",
            json={"status": "completed"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        # Баланс должен измениться на 10_000
        new_rev_bal = (await db_session.execute(
            select(Account.balance).where(Account.id == rev_account.id)
        )).scalar_one()
        assert new_rev_bal - rev_bal == -10_000
```

### Пример 2: Архитектурный тест (pytest-archon)

```python
# tests/test_architecture.py
from pytest_archon import archrule


def test_orders_module_does_not_import_finances_models():
    """orders модуль не должен напрямую импортировать модели finances."""
    (
        archrule("orders-no-finances-models")
        .match("src.modules.orders.*")
        .should_not_import("src.modules.finances.models")
        .check()
    )


def test_api_layer_does_not_import_repositories():
    """API слой не должен знать о репозиториях."""
    (
        archrule("api-no-repositories")
        .match("src.api.*")
        .should_not_import("src.modules.*.repositories")
        .check()
    )
```

### Пример 3: FSM cancel тест

```python
# Добавить в tests/integration/test_order_fsm.py
async def test_cancel_assigned_order_is_allowed(
    self, client, admin_user, courier_user, courier_inventory,
    client_user, client_inventory, products,
):
    headers = make_auth_headers(admin_user.id, Role.ADMIN)

    # Создать и назначить заказ
    resp = await client.post(
        f"/api/v1/backoffice/orders/?clientId={client_user.id}",
        json={
            "items": [{"product_id": str(products["water"].id), "quantity": 1}],
            "payment_method": "cash",
            "client_inventory_id": str(client_inventory.id),
            "capitalize_missing_tara": True,
        },
        headers=headers,
    )
    order_id = resp.json()["id"]

    await client.patch(
        f"/api/v1/backoffice/orders/{order_id}/assign",
        json={"courierId": str(courier_user.id)},
        headers=headers,
    )

    # Отменить назначенный заказ
    resp = await client.patch(
        f"/api/v1/backoffice/orders/{order_id}/status",
        json={"newStatus": "cancelled"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    # Попытка перехода из CANCELLED должна быть отклонена
    resp = await client.patch(
        f"/api/v1/backoffice/orders/{order_id}/in-transit",
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_ORDER_STATUS"
```

### Пример 4: Тест с card payment

```python
# Параметризация в существующем test_delivery_fulfillment.py
import pytest

@pytest.mark.parametrize("payment_method,expected_account_key", [
    ("cash", "cash_account"),
    ("card", "card_account"),
])
async def test_delivery_payment_method(
    self, payment_method, expected_account_key, ...
):
    # ... (те же шаги что в test_cash_delivery_fulfillment)
    # Проверить нужный счёт:
    result = await db_session.execute(
        select(Account.balance).where(
            Account.id == system_entities[expected_account_key].id
        )
    )
    assert result.scalar_one() - before == 40_000
```
