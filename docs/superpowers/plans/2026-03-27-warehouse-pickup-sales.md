# Warehouse Pickup Sales Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable direct warehouse-to-client sales for cash without courier involvement, supporting both registered and anonymous (walk-in) buyers.

**Architecture:** Extend the existing Order model with `sale_type` and `warehouse_id` fields. Add `PICKUP_COMPLETED` status and `WAREHOUSE_SALE`/`WAREHOUSE_TARA_RETURN` transfer types. Create a system walk-in user for anonymous sales. Financial settlement goes Revenue → Client → Cash (both COMPLETED immediately).

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.x (async), PostgreSQL, Alembic, Pydantic V2

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/core/constants.py` | Add `WALKIN_USER_ID` constant |
| Modify | `src/core/init.py` | Seed walk-in user, identity, inventory, account |
| Modify | `src/modules/orders/enums.py` | Add `SaleType` enum, `PICKUP_COMPLETED` status |
| Modify | `src/modules/inventory/enums.py` | Add `WAREHOUSE_SALE`, `WAREHOUSE_TARA_RETURN` transfer types |
| Modify | `src/modules/orders/models.py` | Add `sale_type`, `warehouse_id` columns to Order |
| Modify | `src/modules/orders/schemas.py` | Add `WarehouseSaleCreate`, `WarehouseSaleCapitalizeTaraRequest` DTOs, extend `OrderResponse` |
| Modify | `src/modules/orders/exceptions.py` | Add `InvalidPickupOperationError` |
| Modify | `src/modules/inventory/services.py` | Add `WAREHOUSE_SALE`, `WAREHOUSE_TARA_RETURN` to `_VALID_ROUTES` |
| Modify | `src/modules/orders/services.py` | Add `create_warehouse_sale`, `complete_pickup`, `_handle_warehouse_pickup`, `_process_pickup_settlement` |
| Modify | `src/modules/orders/repositories.py` | Add `sale_type` filter to `search_orders` |
| Modify | `src/api/v1/backoffice/orders.py` | Add 3 new endpoints: warehouse-sale, capitalize-tara, complete-pickup |
| Create | `alembic/versions/xxxx_add_warehouse_pickup.py` | Migration: sale_type, warehouse_id columns |

---

### Task 1: Enums and Constants

**Files:**
- Modify: `src/core/constants.py:1-3`
- Modify: `src/modules/orders/enums.py:1-16`
- Modify: `src/modules/inventory/enums.py:1-28`

- [ ] **Step 1: Add WALKIN_USER_ID constant**

```python
# src/core/constants.py
from uuid import UUID

SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
WALKIN_USER_ID = UUID("00000000-0000-0000-0000-000000000002")
```

- [ ] **Step 2: Add SaleType enum and PICKUP_COMPLETED status**

```python
# src/modules/orders/enums.py
import enum


class OrderStatus(enum.StrEnum):
    NEW = "new"
    ASSIGNED = "assigned"
    IN_TRANSIT = "in_transit"
    ARRIVED = "arrived"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    PICKUP_COMPLETED = "pickup_completed"


class PaymentMethod(enum.StrEnum):
    CASH = "cash"
    CARD = "card"
    CONTRACT = "contract"


class SaleType(enum.StrEnum):
    DELIVERY = "delivery"
    WAREHOUSE_PICKUP = "warehouse_pickup"
```

- [ ] **Step 3: Add WAREHOUSE_SALE and WAREHOUSE_TARA_RETURN transfer types**

In `src/modules/inventory/enums.py`, add to `TransferType`:

```python
class TransferType(enum.StrEnum):
    FACTORY_RECEIPT = "FACTORY_RECEIPT"
    COURIER_LOAD = "COURIER_LOAD"
    COURIER_RETURN = "COURIER_RETURN"
    CLIENT_DELIVERY = "CLIENT_DELIVERY"
    CLIENT_RETURN = "CLIENT_RETURN"
    LOSS_WRITE_OFF = "LOSS_WRITE_OFF"
    INVENTORY_FINDING = "INVENTORY_FINDING"
    INITIAL_BALANCE = "INITIAL_BALANCE"
    WAREHOUSE_SALE = "WAREHOUSE_SALE"
    WAREHOUSE_TARA_RETURN = "WAREHOUSE_TARA_RETURN"
```

- [ ] **Step 4: Add valid routes for new transfer types**

In `src/modules/inventory/services.py`, add to the `_VALID_ROUTES` dict (after the `INITIAL_BALANCE` entry):

```python
    TransferType.WAREHOUSE_SALE: (
        frozenset({InventoryType.WAREHOUSE}),
        frozenset({InventoryType.CLIENT}),
    ),
    TransferType.WAREHOUSE_TARA_RETURN: (
        frozenset({InventoryType.CLIENT}),
        frozenset({InventoryType.WAREHOUSE}),
    ),
```

- [ ] **Step 5: Commit**

```bash
git add src/core/constants.py src/modules/orders/enums.py src/modules/inventory/enums.py src/modules/inventory/services.py
git commit -m "feat: add warehouse pickup enums, constants, and transfer routes"
```

---

### Task 2: Order Model Changes

**Files:**
- Modify: `src/modules/orders/models.py:1-145`

- [ ] **Step 1: Add sale_type and warehouse_id columns to Order**

Add the import for `SaleType` and `String` at the top of `src/modules/orders/models.py`:

```python
from src.modules.orders.enums import OrderStatus, PaymentMethod, SaleType
```

Add `String` to the `sqlalchemy` import:

```python
from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, String
```

Add two new columns to the `Order` class, after `capitalization_applied` (line 76) and before the `client` relationship (line 77):

```python
    sale_type: Mapped[str] = mapped_column(
        String(30),
        default=SaleType.DELIVERY,
        server_default="delivery",
        nullable=False,
        index=True,
        comment="Тип продажи: delivery (доставка) или warehouse_pickup (самовывоз)",
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Склад-источник (заполняется только для самовывоза)",
    )
```

Add a relationship for warehouse after the `client_inventory` relationship:

```python
    warehouse: Mapped["Inventory | None"] = relationship(
        foreign_keys=[warehouse_id],
    )
```

- [ ] **Step 2: Commit**

```bash
git add src/modules/orders/models.py
git commit -m "feat: add sale_type and warehouse_id columns to Order model"
```

---

### Task 3: Alembic Migration

**Files:**
- Create: `alembic/versions/xxxx_add_warehouse_pickup.py`

- [ ] **Step 1: Generate the migration**

```bash
cd C:/Users/Sanjar/Desktop/munavvar-a && uv run alembic revision --autogenerate -m "add_warehouse_pickup_fields"
```

- [ ] **Step 2: Verify and edit the generated migration**

Open the generated file in `alembic/versions/`. It should contain:
- `op.add_column('orders', sa.Column('sale_type', sa.String(30), server_default='delivery', nullable=False))`
- `op.add_column('orders', sa.Column('warehouse_id', sa.UUID(), nullable=True))`
- `op.create_index(...)` for both columns
- `op.create_foreign_key(...)` for `warehouse_id -> inventories.id`

Also add the new enum values for `order_status_enum` and `transfer_type_enum` (PostgreSQL native enums need `ALTER TYPE ... ADD VALUE`):

Add to `upgrade()` before the add_column calls:

```python
    # Add new enum values
    op.execute("ALTER TYPE order_status_enum ADD VALUE IF NOT EXISTS 'pickup_completed'")
    op.execute("ALTER TYPE transfer_type_enum ADD VALUE IF NOT EXISTS 'WAREHOUSE_SALE'")
    op.execute("ALTER TYPE transfer_type_enum ADD VALUE IF NOT EXISTS 'WAREHOUSE_TARA_RETURN'")
```

Note: `transfer_type_enum` may not be a native PG enum if the `TransferType` is stored as a `String`. Check the model — in `src/modules/inventory/models.py` the `StockTransfer.type` column. If it uses `String`, skip the `ALTER TYPE` for `transfer_type_enum`.

- [ ] **Step 3: Apply the migration**

```bash
cd C:/Users/Sanjar/Desktop/munavvar-a && uv run alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
git add alembic/
git commit -m "feat: migration for warehouse pickup fields and enum values"
```

---

### Task 4: Seed Walk-in User

**Files:**
- Modify: `src/core/init.py:1-144`

- [ ] **Step 1: Add walk-in user seeding to init_data()**

Add the import at the top of `src/core/init.py`:

```python
from src.core.constants import WALKIN_USER_ID
```

Add the following block after the virtual inventories section (after line 92, before the admin section) in `init_data()`:

```python
        # --- 3.5 СОЗДАНИЕ WALK-IN ПОЛЬЗОВАТЕЛЯ (АНОНИМНЫЕ ПРОДАЖИ СО СКЛАДА) ---
        query_walkin = select(User).where(User.id == WALKIN_USER_ID)
        walkin_user = (await session.execute(query_walkin)).scalar_one_or_none()

        if not walkin_user:
            walkin_user = User(
                id=WALKIN_USER_ID,
                username="Покупатель со склада (Walk-in)",
                role=Role.CLIENT_B2C,
                is_active=True,
            )
            session.add(walkin_user)
            await session.flush()

            # Identity для Walk-in
            walkin_identity = Identity(
                user_id=walkin_user.id,
                provider=AuthProvider.LOCAL,
                provider_identity_id="00000000002",
                password_hash="!disabled",
            )
            session.add(walkin_identity)

            # Inventory для Walk-in
            walkin_inventory = Inventory(
                user_id=walkin_user.id,
                type=InventoryType.CLIENT,
                name="Самовывоз",
            )
            session.add(walkin_inventory)

            # Финансовый счет Walk-in
            walkin_account = Account(
                user_id=walkin_user.id,
                type=AccountType.CLIENT,
                name="Счёт анонимных покупок",
            )
            session.add(walkin_account)
            await session.flush()

            logger.info("Walk-in пользователь и связанные сущности созданы.")
        else:
            logger.info("Walk-in пользователь уже существует.")
```

Add `AccountType` to the imports from `src.modules.finances.enums`:

```python
from src.modules.finances.enums import AccountType
```

- [ ] **Step 2: Run init to verify**

```bash
cd C:/Users/Sanjar/Desktop/munavvar-a && uv run python -m src.core.init
```

- [ ] **Step 3: Commit**

```bash
git add src/core/init.py src/core/constants.py
git commit -m "feat: seed walk-in user for anonymous warehouse sales"
```

---

### Task 5: Schemas and Exceptions

**Files:**
- Modify: `src/modules/orders/schemas.py:1-167`
- Modify: `src/modules/orders/exceptions.py:1-213`

- [ ] **Step 1: Add WarehouseSaleCreate schema**

Add the import for `SaleType` at the top of `src/modules/orders/schemas.py`:

```python
from src.modules.orders.enums import OrderStatus, PaymentMethod, SaleType
```

Add after the `TaraCheckResponse` class (line 110):

```python
class WarehouseSaleCreate(BaseModel):
    """Создание заказа на самовывоз со склада."""

    warehouse_id: uuid.UUID = Field(
        ..., description="ID склада, с которого продаём"
    )
    items: list[Item] = Field(
        ..., min_length=1, title="Корзина товаров"
    )
    capitalize_missing_tara: bool = Field(
        default=False,
        title="Оприходовать недостающую тару",
    )


class WarehouseSaleCapitalizeTaraRequest(BaseModel):
    """Оприходование тары, принесённой покупателем на склад."""

    warehouse_id: uuid.UUID = Field(
        ..., description="ID склада (для контекста)"
    )
    items: list[Item] = Field(
        ..., min_length=1, description="Тара, принесённая покупателем"
    )
```

- [ ] **Step 2: Extend OrderResponse with sale_type and warehouse_id**

In the `OrderResponse` class, add after `capitalization_applied`:

```python
    sale_type: str = Field(
        default=SaleType.DELIVERY,
        description="Тип продажи: delivery или warehouse_pickup",
    )
    warehouse_id: uuid.UUID | None = Field(
        default=None,
        description="ID склада (только для самовывоза)",
    )
```

- [ ] **Step 3: Add InvalidPickupOperationError**

Add to `src/modules/orders/exceptions.py` after `CannotRemoveLastItemError`:

```python
class InvalidPickupOperationError(ConflictError):
    """Выбрасывается при попытке выполнить pickup-операцию на обычном заказе."""

    def __init__(
        self,
        order_id: uuid.UUID | str,
        reason: str,
    ):
        super().__init__(
            message=f"Ошибка операции самовывоза: {reason}",
            error_code="INVALID_PICKUP_OPERATION",
            details={"order_id": str(order_id)},
        )
```

- [ ] **Step 4: Commit**

```bash
git add src/modules/orders/schemas.py src/modules/orders/exceptions.py
git commit -m "feat: add warehouse sale schemas and exceptions"
```

---

### Task 6: Service Layer — create_warehouse_sale

**Files:**
- Modify: `src/modules/orders/services.py:1-739`

- [ ] **Step 1: Add imports**

Add to the imports at the top of `src/modules/orders/services.py`:

```python
from src.modules.orders.enums import OrderStatus, PaymentMethod, SaleType
```

Add `InvalidPickupOperationError` to the exceptions import:

```python
from src.modules.orders.exceptions import (
    ...
    InvalidPickupOperationError,
)
```

Add `WarehouseSaleCreate` to the schemas import:

```python
from src.modules.orders.schemas import (
    OrderCreate,
    OrderItemActual,
    TaraCheckRequest,
    WarehouseSaleCreate,
)
```

Add `InventoryType` to the inventory enums import:

```python
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
```

Add the constants import:

```python
from src.core.constants import WALKIN_USER_ID
```

- [ ] **Step 2: Add create_warehouse_sale method**

Add to the `BaseOrderService` class, after `create_order`:

```python
    async def create_warehouse_sale(
        self,
        dto: WarehouseSaleCreate,
        client_id: uuid.UUID | None,
        created_by_id: uuid.UUID,
    ) -> Order:
        """
        Создание заказа на самовывоз со склада.
        Если client_id не передан — используется WALKIN_USER_ID.
        """
        effective_client_id = client_id or WALKIN_USER_ID

        if not dto.items:
            raise EmptyCartError()

        product_ids = [item.product_id for item in dto.items]
        products = await self.catalog_service.get_by_ids(product_ids)
        price_map = {p.id: p.price for p in products}

        missing_ids = [pid for pid in product_ids if pid not in price_map]
        if missing_ids:
            raise ProductsUnavailableError(missing_product_ids=missing_ids)

        exchange_items = [
            (p, next(i for i in dto.items if i.product_id == p.id))
            for p in products
            if p.returnable_item_id is not None
        ]

        total_amount = 0
        order_items_data = []
        for item in dto.items:
            current_price = price_map[item.product_id]
            total_amount += current_price * item.quantity
            order_items_data.append(
                {
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "unit_price": current_price,
                }
            )

        async with self.uow:
            # Проверяем, что склад существует
            warehouse = await self.uow.inventories.get_inventory_with_balances(
                dto.warehouse_id, inv_type=InventoryType.WAREHOUSE
            )
            if not warehouse:
                raise ValueError(f"Склад {dto.warehouse_id} не найден")

            # Получаем inventory клиента
            client_inventory = await self.uow.inventories.get_client_inventory(
                effective_client_id
            )
            if not client_inventory:
                raise ClientInventoryNotFoundError(
                    inventory_id=effective_client_id
                )

            capitalization_applied = False

            if exchange_items:
                inventory = (
                    await self.uow.inventories.get_inventory_with_balances(
                        client_inventory.id, with_for_update=True
                    )
                )
                if not inventory:
                    raise ClientInventoryNotFoundError(
                        inventory_id=client_inventory.id
                    )

                balances = {
                    b.product_id: b.quantity for b in inventory.balances
                }

                ordering_tare_now = {
                    item.product_id: item.quantity for item in dto.items
                }

                shortages = []
                for product, item in exchange_items:
                    required_tare_id = product.returnable_item_id
                    available_in_inventory = balances.get(required_tare_id, 0)
                    ordering_now = ordering_tare_now.get(required_tare_id, 0)
                    effective_available = available_in_inventory + ordering_now
                    if effective_available < item.quantity:
                        shortages.append(
                            {
                                "product_id": str(product.id),
                                "product_name": product.name,
                                "returnable_item_id": str(required_tare_id),
                                "required": item.quantity,
                                "available": effective_available,
                                "deficit": item.quantity - effective_available,
                            }
                        )

                if shortages and not dto.capitalize_missing_tara:
                    raise InsufficientTaraError(shortages=shortages)

                if shortages and dto.capitalize_missing_tara:
                    vendor_inv = (
                        await self.uow.inventories.get_vendor_inventory()
                    )
                    transfer = await self.uow.transfers.add(
                        {
                            "from_id": vendor_inv.id,
                            "to_id": client_inventory.id,
                            "type": TransferType.INITIAL_BALANCE,
                            "status": TransferStatus.COMPLETED,
                            "created_by_id": created_by_id,
                            "accepted_by_id": created_by_id,
                        }
                    )
                    for shortage in shortages:
                        await self.uow.transfer_items.add(
                            {
                                "transfer_id": transfer.id,
                                "product_id": uuid.UUID(
                                    shortage["returnable_item_id"]
                                ),
                                "quantity": shortage["deficit"],
                            }
                        )
                        await self.uow.transactions.add(
                            {
                                "product_id": uuid.UUID(
                                    shortage["returnable_item_id"]
                                ),
                                "transfer_id": transfer.id,
                                "from_id": vendor_inv.id,
                                "to_id": client_inventory.id,
                                "quantity": shortage["deficit"],
                            }
                        )
                    capitalization_applied = True

            new_order = await self.uow.orders.add(
                {
                    "client_id": effective_client_id,
                    "client_inventory_id": client_inventory.id,
                    "payment_method": PaymentMethod.CASH,
                    "status": OrderStatus.NEW,
                    "total_amount": total_amount,
                    "capitalization_applied": capitalization_applied,
                    "sale_type": SaleType.WAREHOUSE_PICKUP,
                    "warehouse_id": dto.warehouse_id,
                }
            )

            for item_data in order_items_data:
                item_data["order_id"] = new_order.id
            await self.uow.order_items.add_many(order_items_data)

            await self.uow.commit()
            return await self.uow.orders.get_with_details(new_order.id)
```

- [ ] **Step 3: Add get_client_inventory to InventoryRepository**

Check if `get_client_inventory` method exists in `src/modules/inventory/repositories.py`. If not, add it:

```python
    async def get_client_inventory(
        self, user_id: uuid.UUID
    ) -> Inventory | None:
        query = select(self.model).where(
            self.model.user_id == user_id,
            self.model.type == InventoryType.CLIENT,
            self.model.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalars().first()
```

- [ ] **Step 4: Commit**

```bash
git add src/modules/orders/services.py src/modules/inventory/repositories.py
git commit -m "feat: add create_warehouse_sale service method"
```

---

### Task 7: Service Layer — complete_pickup and fulfillment

**Files:**
- Modify: `src/modules/orders/services.py`

- [ ] **Step 1: Add complete_pickup method**

Add to `BaseOrderService`, after `create_warehouse_sale`:

```python
    async def complete_pickup(
        self,
        order_id: uuid.UUID,
        completed_by_id: uuid.UUID,
    ) -> Order:
        """
        Подтверждение выдачи товара со склада.
        NEW → PICKUP_COMPLETED с созданием складских и финансовых проводок.
        """
        async with self.uow:
            order = await self.uow.orders.get_with_details(
                order_id, with_for_update=True
            )
            if not order:
                raise OrderNotFoundError(order_id=order_id)

            if order.sale_type != SaleType.WAREHOUSE_PICKUP:
                raise InvalidPickupOperationError(
                    order_id=order_id,
                    reason="Заказ не является самовывозом",
                )

            if order.status != OrderStatus.NEW:
                raise InvalidPickupOperationError(
                    order_id=order_id,
                    reason=f"Ожидался статус NEW, текущий: {order.status}",
                )

            await self.uow.orders.update_status(
                order_id, OrderStatus.PICKUP_COMPLETED
            )

            await self._handle_warehouse_pickup(order, completed_by_id)

            await self.uow.commit()
            return await self.uow.orders.get_with_details(order_id)
```

- [ ] **Step 2: Add _handle_warehouse_pickup method**

Add after `_handle_order_fulfillment`:

```python
    async def _handle_warehouse_pickup(
        self,
        order: Order,
        completed_by_id: uuid.UUID,
    ) -> None:
        """
        Складские перемещения при самовывозе:
        1. Проверка остатков на складе
        2. WAREHOUSE_SALE: Warehouse → Client (товар)
        3. WAREHOUSE_TARA_RETURN: Client → Warehouse (тара)
        4. Финансовая проводка
        """
        if not order.warehouse_id:
            raise ValueError("Заказ самовывоза без warehouse_id")

        warehouse = await self.uow.inventories.get_inventory_with_balances(
            order.warehouse_id,
            inv_type=InventoryType.WAREHOUSE,
            with_for_update=True,
        )
        if not warehouse:
            raise ValueError(f"Склад {order.warehouse_id} не найден")

        # Проверка остатков на складе
        warehouse_balances = {
            b.product_id: b.quantity for b in warehouse.balances
        }
        stock_shortages: dict[uuid.UUID, int] = {}
        for item in order.items:
            available = warehouse_balances.get(item.product_id, 0)
            if available < item.quantity:
                stock_shortages[item.product_id] = item.quantity - available
        if stock_shortages:
            raise InsufficientStockError(shortages=stock_shortages)

        # 1. WAREHOUSE_SALE: Warehouse → Client
        sale_transfer = await self.uow.transfers.add(
            {
                "from_id": warehouse.id,
                "to_id": order.client_inventory_id,
                "type": TransferType.WAREHOUSE_SALE,
                "status": TransferStatus.COMPLETED,
                "created_by_id": completed_by_id,
                "accepted_by_id": order.client_id,
                "order_id": order.id,
            }
        )

        # 2. WAREHOUSE_TARA_RETURN: Client → Warehouse
        returnable_map: dict[uuid.UUID, int] = {}
        for item in order.items:
            if item.product.returnable_item_id and item.quantity > 0:
                tare_id = item.product.returnable_item_id
                returnable_map[tare_id] = (
                    returnable_map.get(tare_id, 0) + item.quantity
                )
        returnable_items = [
            {"product_id": pid, "quantity": qty}
            for pid, qty in returnable_map.items()
        ]

        tara_transfer = None
        if returnable_items:
            tara_transfer = await self.uow.transfers.add(
                {
                    "from_id": order.client_inventory_id,
                    "to_id": warehouse.id,
                    "type": TransferType.WAREHOUSE_TARA_RETURN,
                    "status": TransferStatus.COMPLETED,
                    "created_by_id": completed_by_id,
                    "accepted_by_id": completed_by_id,
                    "order_id": order.id,
                }
            )

        # 3. Строки накладных и проводки в леджере
        for item in order.items:
            if item.quantity == 0:
                continue
            await self.uow.transfer_items.add(
                {
                    "transfer_id": sale_transfer.id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                }
            )
            await self.uow.transactions.add(
                {
                    "product_id": item.product_id,
                    "transfer_id": sale_transfer.id,
                    "from_id": warehouse.id,
                    "to_id": order.client_inventory_id,
                    "quantity": item.quantity,
                }
            )

        if tara_transfer:
            for item_data in returnable_items:
                await self.uow.transfer_items.add(
                    {
                        "transfer_id": tara_transfer.id,
                        "product_id": item_data["product_id"],
                        "quantity": item_data["quantity"],
                    }
                )
                await self.uow.transactions.add(
                    {
                        "product_id": item_data["product_id"],
                        "transfer_id": tara_transfer.id,
                        "from_id": order.client_inventory_id,
                        "to_id": warehouse.id,
                        "quantity": item_data["quantity"],
                    }
                )

        # 4. Финансовое закрытие
        await self._process_pickup_settlement(order)
```

- [ ] **Step 3: Add _process_pickup_settlement method**

Add after `_process_financial_settlement`:

```python
    async def _process_pickup_settlement(self, order: Order) -> None:
        """
        Финансовое закрытие самовывоза:
        1. Revenue → Client (долг)
        2. Client → Cash (оплата наличными на складе)
        Обе транзакции COMPLETED — деньги сразу в кассе.
        """
        client_account = await self.uow.accounts.get_client_account(
            order.client_id
        )
        if not client_account:
            raise ValueError(
                f"Финансовый счет клиента {order.client_id} не найден"
            )
        revenue_account = await self.uow.accounts.get_system_revenue_account()
        cash_account = await self.uow.accounts.get_system_cash_account()

        await self.uow.financial_transactions.add_many(
            [
                {
                    "from_id": revenue_account.id,
                    "to_id": client_account.id,
                    "amount": order.total_amount,
                    "order_id": order.id,
                    "status": TransactionStatus.COMPLETED,
                    "reason": "Задолженность за заказ (самовывоз)",
                },
                {
                    "from_id": client_account.id,
                    "to_id": cash_account.id,
                    "amount": order.total_amount,
                    "order_id": order.id,
                    "status": TransactionStatus.COMPLETED,
                    "reason": "Оплата наличными на складе",
                },
            ]
        )
```

- [ ] **Step 4: Add status guard for pickup orders in update_status**

In the `update_status` method (around line 380), add a guard after the order is fetched to prevent pickup orders from using delivery statuses:

```python
            # Guard: pickup orders cannot use delivery statuses
            if order.sale_type == SaleType.WAREHOUSE_PICKUP and new_status in (
                OrderStatus.ASSIGNED,
                OrderStatus.IN_TRANSIT,
                OrderStatus.ARRIVED,
                OrderStatus.DELIVERED,
            ):
                raise InvalidPickupOperationError(
                    order_id=order_id,
                    reason=f"Заказ самовывоза не может перейти в статус {new_status}. "
                    "Используйте complete-pickup.",
                )
```

Add after `old_status = order.status` (line 394), before the `updated_order = ...` line.

- [ ] **Step 5: Commit**

```bash
git add src/modules/orders/services.py
git commit -m "feat: add complete_pickup, warehouse pickup fulfillment, and settlement"
```

---

### Task 8: Repository — sale_type filter

**Files:**
- Modify: `src/modules/orders/repositories.py:141-203`

- [ ] **Step 1: Add sale_type filter to search_orders**

Add `sale_type` parameter to `search_orders` method in `OrderRepository`:

```python
    async def search_orders(
        self,
        skip: int = 0,
        limit: int = 50,
        statuses: list[OrderStatus] | None = None,
        payment_methods: list[PaymentMethod] | None = None,
        courier_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
        client_inventory_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_amount: int | None = None,
        max_amount: int | None = None,
        sale_type: str | None = None,
    ) -> Sequence[Order]:
```

Add the filter logic after the `client_inventory_id` check:

```python
        if sale_type:
            query = query.where(self.model.sale_type == sale_type)
```

- [ ] **Step 2: Update search_orders in BaseOrderService**

In `src/modules/orders/services.py`, update `search_orders` to pass through the `sale_type` parameter:

```python
    async def search_orders(
        self,
        skip: int = 0,
        limit: int = 100,
        statuses: list[OrderStatus] | None = None,
        payment_methods: list[PaymentMethod] | None = None,
        courier_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
        client_inventory_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_amount: int | None = None,
        max_amount: int | None = None,
        sale_type: str | None = None,
    ) -> list[Order]:
        async with self.uow:
            return list(
                await self.uow.orders.search_orders(
                    skip=skip,
                    limit=limit,
                    statuses=statuses,
                    payment_methods=payment_methods,
                    courier_id=courier_id,
                    client_id=client_id,
                    client_inventory_id=client_inventory_id,
                    date_from=date_from,
                    date_to=date_to,
                    min_amount=min_amount,
                    max_amount=max_amount,
                    sale_type=sale_type,
                )
            )
```

- [ ] **Step 3: Commit**

```bash
git add src/modules/orders/repositories.py src/modules/orders/services.py
git commit -m "feat: add sale_type filter to order search"
```

---

### Task 9: API Endpoints

**Files:**
- Modify: `src/api/v1/backoffice/orders.py:1-225`

- [ ] **Step 1: Add imports**

Add to imports in `src/api/v1/backoffice/orders.py`:

```python
from src.modules.orders.schemas import (
    OrderCreate,
    OrderResponse,
    TaraCheckRequest,
    TaraCheckResponse,
    WarehouseSaleCreate,
    WarehouseSaleCapitalizeTaraRequest,
)
from src.modules.orders.enums import OrderStatus, PaymentMethod, SaleType
```

Add capitalize tara service dependency:

```python
from src.modules.inventory.dependencies import get_capitalize_tara_service
from src.modules.inventory.services import CapitalizeTaraService
from src.modules.inventory.schemas import CapitalizeTaraRequest, CapitalizeTaraItem
from src.core.constants import WALKIN_USER_ID
```

- [ ] **Step 2: Add warehouse-sale endpoint**

Add before the `/{orderId}` GET endpoint (to avoid route conflicts with path params):

```python
@orders_router.post("/warehouse-sale", status_code=201, response_model=OrderResponse)
async def create_warehouse_sale(
    dto: WarehouseSaleCreate,
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])
    ],
    order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
    client_id: Annotated[
        uuid.UUID | None,
        Query(alias="clientId", description="ID клиента (если не передан — анонимная продажа)"),
    ] = None,
):
    """Создание заказа на самовывоз со склада."""
    return await order_service.create_warehouse_sale(
        dto=dto, client_id=client_id, created_by_id=admin.id
    )
```

- [ ] **Step 3: Add capitalize-tara endpoint**

```python
@orders_router.post(
    "/warehouse-sale/capitalize-tara",
    status_code=201,
)
async def capitalize_tara_for_sale(
    dto: WarehouseSaleCapitalizeTaraRequest,
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])
    ],
    capitalize_service: Annotated[
        CapitalizeTaraService, Depends(get_capitalize_tara_service)
    ],
    client_id: Annotated[
        uuid.UUID | None,
        Query(alias="clientId", description="ID клиента (если не передан — walk-in)"),
    ] = None,
):
    """Оприходование тары, принесённой покупателем на склад перед самовывозом."""
    effective_client_id = client_id or WALKIN_USER_ID

    # Получаем inventory клиента
    async with capitalize_service.uow:
        client_inv = await capitalize_service.uow.inventories.get_client_inventory(
            effective_client_id
        )
        if not client_inv:
            raise ValueError(f"Инвентарь клиента {effective_client_id} не найден")
        client_inventory_id = client_inv.id

    return await capitalize_service.capitalize_tara(
        dto=CapitalizeTaraRequest(
            client_inventory_id=client_inventory_id,
            items=[
                CapitalizeTaraItem(product_id=item.product_id, quantity=item.quantity)
                for item in dto.items
            ],
        ),
        created_by_id=admin.id,
    )
```

- [ ] **Step 4: Add complete-pickup endpoint**

```python
@orders_router.patch(
    "/{orderId}/complete-pickup", response_model=OrderResponse
)
async def complete_pickup(
    order_id: Annotated[uuid.UUID, Path(alias="orderId")],
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])
    ],
    order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Подтверждение выдачи товара со склада (NEW → PICKUP_COMPLETED)."""
    return await order_service.complete_pickup(
        order_id=order_id, completed_by_id=admin.id
    )
```

- [ ] **Step 5: Add sale_type filter to search_orders endpoint**

Add `sale_type` parameter to the `search_orders` endpoint:

```python
    sale_type: Annotated[
        SaleType | None,
        Query(alias="saleType", description="Фильтр по типу продажи"),
    ] = None,
```

And pass it to the service call:

```python
        sale_type=sale_type,
```

- [ ] **Step 6: Check get_capitalize_tara_service dependency exists**

Verify `src/modules/inventory/dependencies.py` has `get_capitalize_tara_service`. If not, add it:

```python
def get_capitalize_tara_service(
    uow: Annotated[InventoryUnitOfWork, Depends(get_inventory_uow)],
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> CapitalizeTaraService:
    return CapitalizeTaraService(uow=uow, catalog_service=catalog_service)
```

- [ ] **Step 7: Commit**

```bash
git add src/api/v1/backoffice/orders.py src/modules/inventory/dependencies.py
git commit -m "feat: add warehouse sale, capitalize-tara, and complete-pickup endpoints"
```

---

### Task 10: Smoke Test

- [ ] **Step 1: Start the application**

```bash
cd C:/Users/Sanjar/Desktop/munavvar-a && uv run fastapi dev src/main.py
```

Verify it starts without import errors.

- [ ] **Step 2: Check OpenAPI docs**

Open `http://localhost:8000/docs` and verify:
- `POST /api/v1/backoffice/orders/warehouse-sale` appears
- `POST /api/v1/backoffice/orders/warehouse-sale/capitalize-tara` appears
- `PATCH /api/v1/backoffice/orders/{orderId}/complete-pickup` appears
- `GET /api/v1/backoffice/orders/` now has `saleType` query parameter

- [ ] **Step 3: Commit final state**

```bash
git add -A
git commit -m "feat: warehouse pickup sales — complete implementation"
```
