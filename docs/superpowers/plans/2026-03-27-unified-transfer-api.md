# Unified Transfer API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify all inventory movement operations into a single-step `POST /transfers/` endpoint, add FACTORY_SHIPMENT/FACTORY_RETURN types, and remove the old `/shifts/load-truck` and `/shifts/loss` endpoints.

**Architecture:** Replace the split ShiftService + StockTransferService pattern with a single `create_transfer()` method on `StockTransferService`. All transfer types use one request schema, one service method, one endpoint. Virtual inventories (VIRTUAL_VENDOR, VIRTUAL_LOSS) are auto-resolved server-side.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL, React 19, RTK Query

**Spec:** `docs/superpowers/specs/2026-03-27-unified-transfer-api-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/modules/inventory/enums.py` | Add FACTORY_SHIPMENT, FACTORY_RETURN to TransferType |
| Modify | `src/modules/inventory/models.py` | Add `reason`, `route_sheet_id` columns to StockTransfer |
| Modify | `src/modules/inventory/schemas.py` | Add `CreateTransferRequest`, remove old request schemas |
| Modify | `src/modules/inventory/services.py` | Add `create_transfer()`, update `_VALID_ROUTES`, remove draft methods |
| Modify | `src/modules/inventory/shift_service.py` | Remove `load_courier_truck()` and `write_off_loss()` |
| Modify | `src/api/v1/backoffice/transfers.py` | Replace draft endpoints with single `POST /` |
| Modify | `src/api/v1/backoffice/shifts.py` | Remove `/load-truck` and `/loss` routes |
| Create | `alembic/versions/c1d2e3f4g5h6_unified_transfer_api.py` | Migration: enum values + columns |
| Modify | `frontend/src/services/transfersApi.js` | Rewrite: single `createTransfer` mutation |
| Modify | `frontend/src/services/shiftsApi.js` | Remove `loadTruck`, `writeOffLoss` |
| Modify | `frontend/src/pages/Warehouse.jsx` | Update all `handleSubmit` cases to use unified API |

---

### Task 1: Add New Enum Values

**Files:**
- Modify: `src/modules/inventory/enums.py:13-21`

- [ ] **Step 1: Add FACTORY_SHIPMENT and FACTORY_RETURN to TransferType**

In `src/modules/inventory/enums.py`, replace the `TransferType` class:

```python
class TransferType(enum.StrEnum):
    FACTORY_RECEIPT = "FACTORY_RECEIPT"
    FACTORY_SHIPMENT = "FACTORY_SHIPMENT"  # Отправка на завод (Склад → Завод)
    FACTORY_RETURN = "FACTORY_RETURN"  # Приёмка с завода (Завод → Склад)
    COURIER_LOAD = "COURIER_LOAD"  # Загрузка
    COURIER_RETURN = "COURIER_RETURN"  # Выгрузка
    CLIENT_DELIVERY = "CLIENT_DELIVERY"  # Передача полной бутыли клиенту
    CLIENT_RETURN = "CLIENT_RETURN"  # Забор пустой бутыли у клиента
    LOSS_WRITE_OFF = "LOSS_WRITE_OFF"  # Списание
    INVENTORY_FINDING = "INVENTORY_FINDING"  # Оприходование
    INITIAL_BALANCE = "INITIAL_BALANCE"  # Ввод начальных остатков
```

- [ ] **Step 2: Commit**

```bash
git add src/modules/inventory/enums.py
git commit -m "feat: add FACTORY_SHIPMENT and FACTORY_RETURN transfer types"
```

---

### Task 2: Add Model Columns

**Files:**
- Modify: `src/modules/inventory/models.py:111-117`

- [ ] **Step 1: Add `reason` and `route_sheet_id` columns to StockTransfer**

In `src/modules/inventory/models.py`, after the `order_id` column (line ~117) and before the `type` column (line ~119), add:

```python
    reason: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
        comment="Причина (для списания LOSS_WRITE_OFF)",
    )
    route_sheet_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID,
        nullable=True,
        index=True,
        comment="ID маршрутного листа (для COURIER_LOAD)",
    )
```

Note: `route_sheet_id` is a plain UUID without FK constraint — the `route_sheets` table does not exist yet.

- [ ] **Step 2: Commit**

```bash
git add src/modules/inventory/models.py
git commit -m "feat: add reason and route_sheet_id columns to StockTransfer"
```

---

### Task 3: Alembic Migration

**Files:**
- Create: `alembic/versions/c1d2e3f4g5h6_unified_transfer_api.py`

- [ ] **Step 1: Create migration file**

Create `alembic/versions/c1d2e3f4g5h6_unified_transfer_api.py`:

```python
"""unified_transfer_api

Revision ID: c1d2e3f4g5h6
Revises: 8e058e9a7678
Create Date: 2026-03-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4g5h6"
down_revision: Union[str, Sequence[str], None] = "8e058e9a7678"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new enum values
    op.execute("ALTER TYPE transfer_type_enum ADD VALUE IF NOT EXISTS 'FACTORY_SHIPMENT'")
    op.execute("ALTER TYPE transfer_type_enum ADD VALUE IF NOT EXISTS 'FACTORY_RETURN'")

    # 2. Add columns to stock_transfers
    op.add_column(
        "stock_transfers",
        sa.Column(
            "reason",
            sa.String(255),
            nullable=True,
            comment="Причина (для списания LOSS_WRITE_OFF)",
        ),
    )
    op.add_column(
        "stock_transfers",
        sa.Column(
            "route_sheet_id",
            sa.UUID(),
            nullable=True,
            comment="ID маршрутного листа (для COURIER_LOAD)",
        ),
    )
    op.create_index(
        op.f("ix_stock_transfers_route_sheet_id"),
        "stock_transfers",
        ["route_sheet_id"],
        unique=False,
    )


def downgrade() -> None:
    # Note: PostgreSQL does not support removing enum values.
    op.drop_index(op.f("ix_stock_transfers_route_sheet_id"), table_name="stock_transfers")
    op.drop_column("stock_transfers", "route_sheet_id")
    op.drop_column("stock_transfers", "reason")
```

- [ ] **Step 2: Commit**

```bash
git add alembic/versions/c1d2e3f4g5h6_unified_transfer_api.py
git commit -m "feat: migration for unified transfer API (enum values + columns)"
```

---

### Task 4: Unified Request Schema

**Files:**
- Modify: `src/modules/inventory/schemas.py`

- [ ] **Step 1: Add `CreateTransferRequest` schema**

In `src/modules/inventory/schemas.py`, after the `CloseShiftRequest` class (line ~146) and before `FactoryExchangeRequest` (line ~148), add:

```python
# Типы, для которых from_id вычисляется автоматически (VIRTUAL_VENDOR)
_VIRTUAL_SOURCE_TYPES = {
    TransferType.INVENTORY_FINDING,
    TransferType.FACTORY_RECEIPT,
    TransferType.INITIAL_BALANCE,
}
# Типы, для которых to_id вычисляется автоматически (VIRTUAL_LOSS)
_VIRTUAL_DEST_TYPES = {
    TransferType.LOSS_WRITE_OFF,
}


class CreateTransferRequest(BaseModel):
    """Единый запрос на создание и проведение накладной (single-step)."""

    type: TransferType
    from_id: uuid.UUID | None = Field(
        None, description="ID склада-отправителя (авто для INVENTORY_FINDING, FACTORY_RECEIPT, INITIAL_BALANCE)"
    )
    to_id: uuid.UUID | None = Field(
        None, description="ID склада-получателя (авто для LOSS_WRITE_OFF)"
    )
    items: list[Item] = Field(min_length=1, description="Список товаров")
    reason: str | None = Field(
        None, min_length=3, max_length=255,
        description="Причина списания (обязательно для LOSS_WRITE_OFF)",
    )
    route_sheet_id: uuid.UUID | None = Field(
        None, description="ID маршрутного листа (для COURIER_LOAD)"
    )

    @model_validator(mode="after")
    def validate_ids_and_reason(self) -> Self:
        if self.type not in _VIRTUAL_SOURCE_TYPES and self.from_id is None:
            raise ValueError(f"from_id обязателен для типа {self.type}")
        if self.type not in _VIRTUAL_DEST_TYPES and self.to_id is None:
            raise ValueError(f"to_id обязателен для типа {self.type}")
        if self.type == TransferType.LOSS_WRITE_OFF and not self.reason:
            raise ValueError("reason обязателен для LOSS_WRITE_OFF")
        return self
```

- [ ] **Step 2: Remove old request schemas that are being replaced**

Delete these classes from `src/modules/inventory/schemas.py`:
- `LoadCourierTruckRequest` (lines 129-137)
- `LossWriteOffRequest` (lines 173-184)
- `TransferCreate` (lines 389-392)
- `TransferItemCreate` (lines 395-397)
- `TransferCompleteRequest` (lines 400-401)

Also remove the now-unused `DraftTransferRequest` (lines 86-92) and `CompleteTransferRequest` (lines 94-97) if they exist only as dead code.

- [ ] **Step 3: Commit**

```bash
git add src/modules/inventory/schemas.py
git commit -m "feat: add CreateTransferRequest, remove old transfer schemas"
```

---

### Task 5: Unified Service Method

**Files:**
- Modify: `src/modules/inventory/services.py:33-73` (routes map)
- Modify: `src/modules/inventory/services.py:214-366` (StockTransferService)

- [ ] **Step 1: Update `_VALID_ROUTES` with new types**

In `src/modules/inventory/services.py`, add the two new entries to `_VALID_ROUTES` (after `FACTORY_RECEIPT`, around line 39):

```python
    TransferType.FACTORY_SHIPMENT: (
        frozenset({InventoryType.WAREHOUSE}),
        frozenset({InventoryType.FACTORY}),
    ),
    TransferType.FACTORY_RETURN: (
        frozenset({InventoryType.FACTORY}),
        frozenset({InventoryType.WAREHOUSE}),
    ),
```

- [ ] **Step 2: Update imports in `services.py`**

Replace the schema imports at the top of `src/modules/inventory/services.py`:

```python
from src.modules.inventory.schemas import (
    CapitalizeDeficitRequest,
    CapitalizeTaraItem,
    CapitalizeTaraRequest,
    CreateTransferRequest,
    TransportCreate,
    TransportUpdate,
    WarehouseCreate,
)
```

Remove: `TransferCreate`, `TransferItemCreate`. Add: `CreateTransferRequest`.

Also add `InsufficientStockError` to the exceptions import:

```python
from src.modules.inventory.exceptions import (
    CourierAlreadyAssignedError,
    InsufficientStockError,
    InventoryNotFoundError,
    InventoryTypeMismatchError,
    RouteLoopError,
)
```

- [ ] **Step 3: Replace draft methods with `create_transfer()`**

In `StockTransferService`, remove methods: `create_draft_transfer`, `update_draft_items`, `complete_transfer`. Replace them with a single method:

```python
    async def create_transfer(
        self,
        created_by_id: uuid.UUID,
        schema: CreateTransferRequest,
    ) -> StockTransfer:
        """
        Единый метод создания и проведения накладной (single-step).
        1. Авто-подставляет виртуальные склады (VIRTUAL_VENDOR / VIRTUAL_LOSS)
        2. Валидирует маршрут
        3. Проверяет остатки
        4. Создаёт Transfer + Items + Transactions атомарно
        """
        async with self.uow:
            # 1. Авто-подстановка виртуальных складов
            from_id = schema.from_id
            to_id = schema.to_id

            if schema.type in (
                TransferType.INVENTORY_FINDING,
                TransferType.FACTORY_RECEIPT,
                TransferType.INITIAL_BALANCE,
            ):
                vendor_inv = await self.uow.inventories.get_system_inventory(
                    InventoryType.VIRTUAL_VENDOR
                )
                from_id = vendor_inv.id

            if schema.type == TransferType.LOSS_WRITE_OFF:
                loss_inv = await self.uow.inventories.get_system_inventory(
                    InventoryType.VIRTUAL_LOSS
                )
                to_id = loss_inv.id

            # 2. Защита от петли
            if from_id == to_id:
                raise RouteLoopError(inventory_id=from_id)

            # 3. Валидация маршрута
            from_inventory = await self.uow.inventories.get(from_id)
            if not from_inventory:
                raise InventoryNotFoundError(inventory_id=from_id)
            to_inventory = await self.uow.inventories.get(to_id)
            if not to_inventory:
                raise InventoryNotFoundError(inventory_id=to_id)

            route = _VALID_ROUTES.get(schema.type)
            if route:
                allowed_from, allowed_to = route
                if from_inventory.type not in allowed_from:
                    raise InventoryTypeMismatchError(
                        inventory_id=from_inventory.id,
                        expected_type=str(allowed_from),
                        actual_type=from_inventory.type,
                    )
                if to_inventory.type not in allowed_to:
                    raise InventoryTypeMismatchError(
                        inventory_id=to_inventory.id,
                        expected_type=str(allowed_to),
                        actual_type=to_inventory.type,
                    )

            # 4. Блокировка и проверка остатков (пропуск для VIRTUAL_VENDOR)
            if from_inventory.type != InventoryType.VIRTUAL_VENDOR:
                from_inventory = await self.uow.inventories.get_inventory_with_balances(
                    from_id, with_for_update=True
                )
                balances = {b.product_id: b.quantity for b in from_inventory.balances}
                shortages: dict[uuid.UUID, int] = {}
                for item in schema.items:
                    available = balances.get(item.product_id, 0)
                    if available < item.quantity:
                        shortages[item.product_id] = item.quantity - available
                if shortages:
                    raise InsufficientStockError(shortages=shortages)

            # 5. Создаём накладную (сразу COMPLETED)
            transfer = await self.uow.transfers.add({
                "from_id": from_id,
                "to_id": to_id,
                "type": schema.type,
                "status": TransferStatus.COMPLETED,
                "created_by_id": created_by_id,
                "accepted_by_id": created_by_id,
                "reason": schema.reason,
                "route_sheet_id": schema.route_sheet_id,
            })

            # 6. Строки накладной и проводки в леджере
            for item in schema.items:
                await self.uow.transfer_items.add({
                    "transfer_id": transfer.id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                })
                await self.uow.transactions.add({
                    "product_id": item.product_id,
                    "transfer_id": transfer.id,
                    "from_id": from_id,
                    "to_id": to_id,
                    "quantity": item.quantity,
                })

            await self.uow.commit()
            return transfer
```

Keep the existing `search_transfers()` method unchanged.

- [ ] **Step 4: Commit**

```bash
git add src/modules/inventory/services.py
git commit -m "feat: unified create_transfer() method, remove draft workflow"
```

---

### Task 6: Clean Up ShiftService

**Files:**
- Modify: `src/modules/inventory/shift_service.py:1-93, 95-166`

- [ ] **Step 1: Remove `load_courier_truck()` and `write_off_loss()` from ShiftService**

In `src/modules/inventory/shift_service.py`:
- Delete the `load_courier_truck()` method (lines 29-93)
- Delete the `write_off_loss()` method (lines 95-166)
- Remove the now-unused imports: `LoadCourierTruckRequest`, `LossWriteOffRequest`
- Remove `InsufficientStockError` and `InventoryTypeMismatchError` from imports if no longer used by remaining methods (`factory_exchange` and `close_shift`)

Check remaining methods: `factory_exchange` uses `InsufficientStockError` and `InventoryNotFoundError`. `close_shift` uses neither. So keep `InsufficientStockError` and `InventoryNotFoundError`, remove `InventoryTypeMismatchError`.

Updated imports:

```python
from src.modules.inventory.exceptions import (
    InsufficientStockError,
    InventoryNotFoundError,
)
from src.modules.inventory.schemas import (
    CloseShiftRequest,
    FactoryExchangeRequest,
)
```

- [ ] **Step 2: Commit**

```bash
git add src/modules/inventory/shift_service.py
git commit -m "refactor: remove load_courier_truck and write_off_loss from ShiftService"
```

---

### Task 7: Update API Routes

**Files:**
- Modify: `src/api/v1/backoffice/transfers.py`
- Modify: `src/api/v1/backoffice/shifts.py`

- [ ] **Step 1: Rewrite transfers router**

Replace the entire content of `src/api/v1/backoffice/transfers.py`:

```python
# src/api/v1/backoffice/transfers.py
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.dependencies import get_stock_transfer_service
from src.modules.inventory.schemas import (
    CreateTransferRequest,
    TransferResponse,
)
from src.modules.inventory.services import StockTransferService

transfers_router = APIRouter()


@transfers_router.get(
    "/",
    response_model=list[TransferResponse],
    summary="Журнал всех накладных",
)
async def get_transfers(
    transfer_service: Annotated[
        StockTransferService, Depends(get_stock_transfer_service)
    ],
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    skip = (page - 1) * size
    return await transfer_service.search_transfers(skip=skip, limit=size)


@transfers_router.post(
    "/",
    response_model=TransferResponse,
    summary="Создание и проведение накладной",
)
async def create_transfer(
    schema: CreateTransferRequest,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.INVENTORY_WRITE])
    ],
    transfer_service: Annotated[
        StockTransferService, Depends(get_stock_transfer_service)
    ],
):
    return await transfer_service.create_transfer(current_admin.id, schema)
```

- [ ] **Step 2: Remove `/load-truck` and `/loss` from shifts router**

In `src/api/v1/backoffice/shifts.py`, remove:
- The `load_courier_truck` endpoint (lines 27-36)
- The `write_off_loss` endpoint (lines 39-48)
- Unused imports: `LoadCourierTruckRequest`, `LossWriteOffRequest`

The remaining file should only have `factory-exchange` and `close` endpoints:

```python
# src/api/v1/backoffice/shifts.py
from typing import Annotated

from fastapi import APIRouter, Depends, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.schemas import (
    CloseShiftRequest,
    FactoryExchangeRequest,
)
from src.modules.inventory.shift_service import ShiftService
from src.modules.inventory.uow import InventoryUnitOfWork

shifts_router = APIRouter()


def get_shift_service(
    uow: Annotated[InventoryUnitOfWork, Depends()],
) -> ShiftService:
    return ShiftService(uow)


@shifts_router.post("/factory-exchange")
async def factory_exchange(
    request: FactoryExchangeRequest,
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.INVENTORY_WRITE])
    ],
    shift_service: Annotated[ShiftService, Depends(get_shift_service)],
):
    """Обмен на заводе: курьер сдаёт пустые, забирает полные (COURIER→FACTORY→COURIER)."""
    return await shift_service.factory_exchange(
        request, created_by_id=admin.id
    )


@shifts_router.post("/close")
async def close_shift(
    request: CloseShiftRequest,
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.INVENTORY_WRITE])
    ],
    shift_service: Annotated[ShiftService, Depends(get_shift_service)],
):
    """Закрытие смены курьера и инкассация (Backoffice/Кладовщик)."""
    return await shift_service.close_shift(request)
```

- [ ] **Step 3: Commit**

```bash
git add src/api/v1/backoffice/transfers.py src/api/v1/backoffice/shifts.py
git commit -m "feat: unified POST /transfers/ endpoint, remove /shifts/load-truck and /shifts/loss"
```

---

### Task 8: Update Frontend — API Service Layer

**Files:**
- Modify: `frontend/src/services/transfersApi.js`
- Modify: `frontend/src/services/shiftsApi.js`

- [ ] **Step 1: Rewrite `transfersApi.js`**

Replace `frontend/src/services/transfersApi.js`:

```javascript
import { baseApi } from "./baseApi";

export const transfersApi = baseApi.injectEndpoints({
  endpoints: (build) => ({
    getTransfers: build.query({
      query: ({ page = 1, size = 20 } = {}) => ({
        url: "/api/v1/backoffice/transfers/",
        params: { page, size },
      }),
      providesTags: (result) => {
        const items = Array.isArray(result) ? result : [];
        return [
          { type: "Transfers", id: "LIST" },
          ...items.map((t) => ({ type: "Transfers", id: t?.id })),
        ];
      },
    }),

    createTransfer: build.mutation({
      query: (body) => ({
        url: "/api/v1/backoffice/transfers/",
        method: "POST",
        body,
      }),
      invalidatesTags: [
        { type: "Transfers", id: "LIST" },
        { type: "Transports", id: "LIST" },
        { type: "Warehouses", id: "LIST" },
      ],
    }),
  }),
  overrideExisting: false,
});

export const {
  useGetTransfersQuery,
  useCreateTransferMutation,
} = transfersApi;
```

Removed: `updateTransferItems`, `completeTransfer` endpoints and their hooks.

- [ ] **Step 2: Remove `loadTruck` and `writeOffLoss` from `shiftsApi.js`**

Replace `frontend/src/services/shiftsApi.js`:

```javascript
import { baseApi } from "./baseApi";

export const shiftsApi = baseApi.injectEndpoints({
  endpoints: (build) => ({
    factoryExchange: build.mutation({
      query: (body) => ({
        url: "/api/v1/backoffice/shifts/factory-exchange",
        method: "POST",
        body,
      }),
      invalidatesTags: [
        { type: "Transfers", id: "LIST" },
        { type: "Transports", id: "LIST" },
        { type: "Warehouses", id: "LIST" },
      ],
    }),

    closeShift: build.mutation({
      query: (body) => ({
        url: "/api/v1/backoffice/shifts/close",
        method: "POST",
        body,
      }),
      invalidatesTags: [
        { type: "Transfers", id: "LIST" },
        { type: "Transports", id: "LIST" },
        { type: "Warehouses", id: "LIST" },
      ],
    }),
  }),
  overrideExisting: false,
});

export const {
  useFactoryExchangeMutation,
  useCloseShiftMutation,
} = shiftsApi;
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/transfersApi.js frontend/src/services/shiftsApi.js
git commit -m "feat(frontend): update API services for unified transfer endpoint"
```

---

### Task 9: Update Frontend — Warehouse Page

**Files:**
- Modify: `frontend/src/pages/Warehouse.jsx`

- [ ] **Step 1: Update imports**

In `frontend/src/pages/Warehouse.jsx`, replace the imports (lines 16-28):

```javascript
import {
  useGetTransfersQuery,
  useCreateTransferMutation,
} from "@/services/transfersApi";
import { useGetTransportsQuery } from "@/services/transportsApi";
import {
  useCloseShiftMutation,
  useFactoryExchangeMutation,
} from "@/services/shiftsApi";
import { useGetCouriersQuery } from "@/services/couriersApi";
```

Removed: `useUpdateTransferItemsMutation`, `useCompleteTransferMutation`, `useLoadTruckMutation`, `useWriteOffLossMutation`.

- [ ] **Step 2: Update hook declarations**

Replace the hook calls block (lines ~715-721):

```javascript
  const [closeShift] = useCloseShiftMutation();
  const [factoryExchange] = useFactoryExchangeMutation();
  const [createTransfer] = useCreateTransferMutation();
```

Removed: `loadTruck`, `updateTransferItems`, `completeTransfer`, `writeOffLoss`.

- [ ] **Step 3: Update `handleSubmit` — `"load"` case**

Replace the `case "load"` block (lines ~759-769):

```javascript
        case "load": {
          if (!warehouseId || !courierId)
            throw { local: "Ombor va kuryer mashinasini tanlang" };
          if (v.length === 0) throw { local: "Kamida bitta mahsulot qo'shing" };
          await createTransfer({
            type: "COURIER_LOAD",
            from_id: warehouseId,
            to_id: courierId,
            items: v,
            route_sheet_id: crypto.randomUUID(),
          }).unwrap();
          break;
        }
```

- [ ] **Step 4: Update `handleSubmit` — `"loss"` case**

Replace the `case "loss"` block (lines ~795-804):

```javascript
        case "loss": {
          if (!warehouseId) throw { local: "Omborni tanlang" };
          if (v.length === 0) throw { local: "Kamida bitta mahsulot qo'shing" };
          if (!reason.trim()) throw { local: "Sababini kiriting" };
          await createTransfer({
            type: "LOSS_WRITE_OFF",
            from_id: warehouseId,
            items: v,
            reason: reason.trim(),
          }).unwrap();
          break;
        }
```

Note: `to_id` is omitted — the backend auto-resolves it to VIRTUAL_LOSS.

- [ ] **Step 5: Update `handleSubmit` — `"capitalize"` case**

Replace the `case "capitalize"` block (lines ~781-793). Previously used 3-step draft flow, now single-step:

```javascript
        case "capitalize": {
          if (!warehouseId) throw { local: "Omborni tanlang" };
          if (v.length === 0) throw { local: "Kamida bitta mahsulot qo'shing" };
          await createTransfer({
            type: "INVENTORY_FINDING",
            to_id: warehouseId,
            items: v,
          }).unwrap();
          break;
        }
```

Note: `from_id` is omitted — backend auto-resolves to VIRTUAL_VENDOR. No more `virtualVendorId` dependency.

- [ ] **Step 6: Update `handleSubmit` — `"initial-balance"` case**

Replace the `case "initial-balance"` block (lines ~806-818):

```javascript
        case "initial-balance": {
          if (!warehouseId) throw { local: "Omborni tanlang" };
          if (v.length === 0) throw { local: "Kamida bitta mahsulot qo'shing" };
          await createTransfer({
            type: "INITIAL_BALANCE",
            to_id: warehouseId,
            items: v,
          }).unwrap();
          break;
        }
```

- [ ] **Step 7: Remove `virtualVendorId` state/logic if no longer needed**

Search the file for `virtualVendorId`. If it's only used in the `capitalize` and `initial-balance` cases (which no longer need it), remove:
- The state declaration: `const [virtualVendorId, setVirtualVendorId] = ...`
- Any effect or logic that sets it

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Warehouse.jsx
git commit -m "feat(frontend): use unified createTransfer for all nakladnoy operations"
```

---

### Task 10: Verify and Clean Up

- [ ] **Step 1: Check for import errors in Python**

Run:
```bash
cd C:/Users/Sanjar/Desktop/munavvar-a && python -c "from src.api.v1.backoffice.transfers import transfers_router; from src.api.v1.backoffice.shifts import shifts_router; from src.modules.inventory.services import StockTransferService; print('OK')"
```

Expected: `OK` with no import errors.

- [ ] **Step 2: Check that `InsufficientStockError` import is at module top level in services.py**

The `create_transfer` method uses `InsufficientStockError`. Ensure it's imported at the top of `src/modules/inventory/services.py`, not inside the method. Update the imports:

```python
from src.modules.inventory.exceptions import (
    CourierAlreadyAssignedError,
    InsufficientStockError,
    InventoryNotFoundError,
    InventoryTypeMismatchError,
    RouteLoopError,
)
```

- [ ] **Step 3: Verify the TransferResponse schema still works**

The `TransferResponse` in `schemas.py` (lines 411-422) must include the new fields. Add `reason` and `route_sheet_id`:

```python
class TransferResponse(BaseModel):
    id: uuid.UUID
    from_id: uuid.UUID
    to_id: uuid.UUID
    created_by_id: uuid.UUID
    accepted_by_id: uuid.UUID | None
    status: TransferStatus
    type: TransferType
    items: list[TransferItemResponse] = []
    reason: str | None = None
    route_sheet_id: uuid.UUID | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 4: Start the server and verify**

Run:
```bash
cd C:/Users/Sanjar/Desktop/munavvar-a && python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000
```

Check Swagger at `http://localhost:8000/docs`:
- `POST /api/v1/backoffice/transfers/` should accept `CreateTransferRequest`
- `GET /api/v1/backoffice/transfers/` should still work
- `/shifts/load-truck` and `/shifts/loss` should be gone
- `/shifts/factory-exchange` and `/shifts/close` should still be present

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "fix: add missing fields to TransferResponse, ensure clean imports"
```
