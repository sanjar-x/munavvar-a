# Unified Transfer API Design

**Date:** 2026-03-27
**Status:** Approved

## Problem

Inventory movements (nakladnye) are split across two services and two routers:

- `ShiftService` handles `load-truck`, `loss`, `close`, `factory-exchange` via `/shifts/*` — all single-step (immediate COMPLETED)
- `StockTransferService` handles generic transfers via `/transfers/*` — 3-step draft workflow

Operations like loss write-off and courier loading have nothing to do with "shifts" — they are warehouse operations that ended up in the wrong service for historical reasons.

Additionally, there is no way to track direct warehouse-to-factory shipments (sending goods to the factory for processing and receiving them back).

## Solution

### Unified Single-Step Transfer API

All inventory movements go through one endpoint:

```
POST /transfers/    — create and execute a transfer (single-step, immediately COMPLETED)
GET  /transfers/    — journal of all transfers (unchanged)
```

The 3-step draft workflow (`create_draft` -> `update_items` -> `complete`) is removed. All transfers are created with items and completed atomically in one request.

### New Transfer Types

Two new enum values added to `TransferType`:

| Type | Route | Description |
|------|-------|-------------|
| `FACTORY_SHIPMENT` | WAREHOUSE -> FACTORY | Send goods to factory (e.g. empty bottles for refilling) |
| `FACTORY_RETURN` | FACTORY -> WAREHOUSE | Receive goods from factory (e.g. filled water bottles) |

**Business process:** Warehouse worker loads empty bottles onto a truck, records a `FACTORY_SHIPMENT` transfer. Truck goes to factory, exchanges goods (untracked). Truck returns, warehouse worker records a `FACTORY_RETURN` transfer with filled bottles. The truck is not tracked as an inventory point in this flow — only warehouse and factory balances matter.

### Complete Transfer Type Table

| Operation (UZ) | Operation (RU) | Type | Allowed From | Allowed To |
|---|---|---|---|---|
| Yuklash | Загрузка курьера | `COURIER_LOAD` | WAREHOUSE, FACTORY | COURIER |
| Tushurib olish | Выгрузка курьера | `COURIER_RETURN` | COURIER | WAREHOUSE, FACTORY |
| Hisobga qo'shish | Оприходование | `INVENTORY_FINDING` | VIRTUAL_VENDOR | WAREHOUSE, COURIER, FACTORY |
| Hisobdan chiqarish | Списание | `LOSS_WRITE_OFF` | WAREHOUSE, COURIER, FACTORY | VIRTUAL_LOSS |
| Zavodga jo'natish | Отправка на завод | `FACTORY_SHIPMENT` | WAREHOUSE | FACTORY |
| Zavoddan qabul | Приёмка с завода | `FACTORY_RETURN` | FACTORY | WAREHOUSE |
| Yetkazib berish | Доставка клиенту | `CLIENT_DELIVERY` | COURIER | CLIENT |
| Qaytarib olish | Забор у клиента | `CLIENT_RETURN` | CLIENT | COURIER |
| Yangi tara | Приход от поставщика | `FACTORY_RECEIPT` | VIRTUAL_VENDOR | WAREHOUSE, FACTORY |
| Boshlang'ich qoldiq | Нач. остатки | `INITIAL_BALANCE` | VIRTUAL_VENDOR | CLIENT, WAREHOUSE, COURIER, FACTORY |

### Unified Request Schema

```python
class CreateTransferRequest(BaseModel):
    type: TransferType
    from_id: uuid.UUID | None = None   # optional: auto-resolved for types with virtual source
    to_id: uuid.UUID | None = None     # optional: auto-resolved for types with virtual destination
    items: list[Item] = Field(min_length=1)
    reason: str | None = Field(None, min_length=3, max_length=255)  # required for LOSS_WRITE_OFF
    route_sheet_id: uuid.UUID | None = None                          # for COURIER_LOAD
```

**Auto-resolved fields (frontend omits these):**
- `LOSS_WRITE_OFF`: `to_id` auto-resolved to VIRTUAL_LOSS. `from_id` required.
- `INVENTORY_FINDING`: `from_id` auto-resolved to VIRTUAL_VENDOR. `to_id` required.
- `FACTORY_RECEIPT`, `INITIAL_BALANCE`: `from_id` auto-resolved to VIRTUAL_VENDOR. `to_id` required.
- All other types: both `from_id` and `to_id` required.

**Validation (model_validator):**
- If `from_id` is None and type not in (`LOSS_WRITE_OFF`, ... virtual-source types) -> error
- If `to_id` is None and type not in (`INVENTORY_FINDING`, ... virtual-dest types) -> error
- `reason` is required when type == `LOSS_WRITE_OFF`

### Service Method: `StockTransferService.create_transfer()`

Single method handles all transfer types:

1. Auto-resolve virtual inventory IDs (VIRTUAL_VENDOR, VIRTUAL_LOSS) based on type
2. Validate route against `_VALID_ROUTES` map
3. Acquire `FOR UPDATE` lock on source inventory (skip for VIRTUAL_VENDOR)
4. Check balance sufficiency (skip for VIRTUAL_VENDOR)
5. Create `StockTransfer` with `status=COMPLETED`
6. Create `StockTransferItem` + `StockTransaction` per item
7. Commit atomically

### What Gets Removed

| Removed | Replaced By |
|---------|-------------|
| `POST /shifts/load-truck` | `POST /transfers/` with type=`COURIER_LOAD` |
| `POST /shifts/loss` | `POST /transfers/` with type=`LOSS_WRITE_OFF` |
| `ShiftService.load_courier_truck()` | `StockTransferService.create_transfer()` |
| `ShiftService.write_off_loss()` | `StockTransferService.create_transfer()` |
| `LoadCourierTruckRequest` schema | `CreateTransferRequest` |
| `LossWriteOffRequest` schema | `CreateTransferRequest` |
| `StockTransferService.create_draft_transfer()` | `StockTransferService.create_transfer()` |
| `StockTransferService.update_draft_items()` | removed (no more drafts) |
| `StockTransferService.complete_transfer()` | removed (no more drafts) |
| `PUT /transfers/{id}/items` | removed |
| `POST /transfers/{id}/complete` | removed |
| `TransferCreate` schema | `CreateTransferRequest` |
| `TransferItemCreate` schema | reuses `Item` |
| `TransferCompleteRequest` schema | removed |

### What Stays Unchanged

- `POST /shifts/close` — reconciliation + cash collection + shift deactivation (complex lifecycle, not a simple transfer)
- `POST /shifts/factory-exchange` — atomic 3-transfer courier-factory exchange (different use case: courier on route visits factory)
- `GET /transfers/` — journal endpoint (unchanged)

### Database Migration (Alembic)

1. Add `FACTORY_SHIPMENT` and `FACTORY_RETURN` to PostgreSQL enum `transfer_type_enum`
2. Add nullable `reason` column to `stock_transfers` (VARCHAR 255)
3. Add nullable `route_sheet_id` column to `stock_transfers` (UUID, FK to route_sheets)
