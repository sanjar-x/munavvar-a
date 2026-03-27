# Warehouse Ledger Page — Design Spec

**Date:** 2026-03-27
**Status:** Approved

---

## Overview

A new `/warehouse` page that implements a Ledger system for managing inventory locations (warehouses) and stock movement documents (transfers / накладные). The page follows the existing master-detail UI pattern used across the app.

---

## UX/UI Quality Requirement

> **Приоритет:** Каждый блок страницы должен быть максимально проработан с точки зрения UX/UI.
> Страница предназначена для **ежедневного учёта приходов и расходов** склада — пользователь (кладовщик/бухгалтер) работает с ней весь рабочий день. Это означает:

- **Ясность данных:** таблицы остатков и накладных должны быть читаемы с первого взгляда — правильные отступы, типографика, выравнивание числовых колонок по правому краю
- **Цветовая индикация:** статусы накладных (DRAFT / COMPLETED / CANCELLED) и типы операций (приход / расход / перемещение) выделяются цветными бейджами
- **Тип операции — приход или расход:** типы `FACTORY_RECEIPT`, `PURCHASE`, `PRODUCTION`, `INITIAL_BALANCE`, `INVENTORY_FINDING` — приход (зелёный), типы `COURIER_LOAD`, `CLIENT_DELIVERY`, `LOSS_WRITE_OFF` — расход (красный), остальные — нейтральные (серый/синий)
- **Wizard шаг-за-шагом:** чёткий индикатор шагов (1 → 2 → 3) с названиями, активный шаг выделен, пройденные шаги отмечены галочкой
- **Пустые состояния:** вместо пустой таблицы — информативный placeholder с иконкой и подсказкой действия (напр. "Накладных пока нет. Создайте первую накладную →")
- **Мгновенная обратная связь:** кнопки показывают состояние загрузки ("Saqlanmoqda..."), успешные операции — flash-сообщение зелёного цвета, ошибки — красного
- **Левая панель:** активный склад выделен цветом фона + левой полосой акцента; баланс позиций виден без клика (число товарных позиций в бейдже)
- **Detail modal накладной:** показывает полную информацию читаемо: шапка с метаданными + таблица товаров с итоговой строкой
- **Адаптивность форм:** select-поля достаточной ширины, placeholder-тексты подсказывают что выбирать

---

## Layout

Master-detail split layout — two columns:

```
┌─────────────────────┬──────────────────────────────────────────────┐
│  Warehouses (left)  │  Detail panel (right)                        │
│  ─────────────────  │  ─────────────────────────────────────────── │
│  [+ Yaratish]       │  Warehouse name                              │
│                     │  [Qoldiqlar] [Nakладные] [Nakладная yaratish]│
│  > Склад А  ←active │                                              │
│    Склад Б          │  <active tab content>                        │
│    Склад В          │                                              │
└─────────────────────┴──────────────────────────────────────────────┘
```

- Left column: fixed ~280px width, independent scroll
- Right column: flex-grow, three tabs
- If no warehouse selected: right panel shows a placeholder "Omborni tanlang"

---

## Left Panel — Warehouse List

**Data source:** `GET /api/v1/backoffice/warehouses/` → `WarehouseDetailResponse[]`
- API returns full list (no pagination needed)

**Each list item displays:**
- Warehouse name
- Number of distinct product lines in balances (as a badge)

**Interaction:**
- Click item → selects warehouse, loads detail in right panel
- Active item highlighted (same pattern as Sidebar `styles.active`)

**Create warehouse button** ("Yaratish") above the list:
- Opens a modal with:
  - `name` (text input, required)
  - `user_id` (select from users — responsible person, required)
- Calls `POST /api/v1/backoffice/warehouses/`
- On success: flash message, list refreshes, new warehouse auto-selected

**States:** skeleton (3–5 placeholder rows), error, empty list

---

## Right Panel — Tab: Остатки (Qoldiqlar)

**Data source:** `GET /api/v1/backoffice/warehouses/{warehouse_id}` → `balances[]`

**Table columns:** Mahsulot | Turi | Miqdor

**States:** skeleton while loading, "Qoldiq yo'q" when empty, inline error

---

## Right Panel — Tab: Накладные (Nakладные)

**Data source:** `GET /api/v1/backoffice/transfers/` with pagination (`page`, `size`)
- Global journal — not filtered by warehouse (API limitation)

**Table columns:** Turi | Kimdan | Kimga | Holat | Sana

**Status badge colors:**
- `DRAFT` → grey
- `COMPLETED` → green
- `CANCELLED` → red

**Interaction:**
- Click row → opens a detail modal showing: transfer metadata + items list (product name + quantity)

**Pagination:** page/size controls at footer, same pattern as Transport.jsx

---

## Right Panel — Tab: Создать накладную (Nakладная yaratish)

Three-step wizard rendered inline inside the right panel (no modal).

### Step 1 — Transfer parameters

Fields:
- `type` (select): `FACTORY_RECEIPT`, `PURCHASE`, `PRODUCTION`, `COURIER_LOAD`, `COURIER_RETURN`, `CLIENT_DELIVERY`, `CLIENT_RETURN`, `WAREHOUSE_TRANSFER`, `LOSS_WRITE_OFF`, `INVENTORY_FINDING`, `INITIAL_BALANCE`
- `from_id` (select from warehouses list)
- `to_id` (select from warehouses list)

Action: "Keyingi →" button calls `POST /api/v1/backoffice/transfers/` → creates `DRAFT`

### Step 2 — Products

Dynamic list of rows: [Product (select from catalog) | Quantity (number input) | ✕ remove]

- "+ Qo'shish" button adds a new empty row
- Minimum 1 row required
- Action: "Keyingi →" calls `PUT /api/v1/backoffice/transfers/{id}/items`

### Step 3 — Confirmation & completion

- Summary: type, from → to, items list
- `accepted_by_id` (select from users list, required)
- "O'tkazish" (Провести) button calls `POST /api/v1/backoffice/transfers/{id}/complete`
- On success: wizard resets to Step 1, active tab switches to "Накладные", flash message shown

**Error handling:** each step shows inline error message if API call fails. If Step 2 fails, the draft transfer already exists — user can retry adding items without re-creating the draft.

---

## API Services

### `src/services/warehousesApi.js` (new)
```
getWarehouses()           → GET /api/v1/backoffice/warehouses/
getWarehouseDetail(id)    → GET /api/v1/backoffice/warehouses/{id}
createWarehouse(body)     → POST /api/v1/backoffice/warehouses/
```
Tag type: `"Warehouses"`

### `src/services/transfersApi.js` (new)
```
getTransfers({ page, size })           → GET /api/v1/backoffice/transfers/
createTransfer(body)                   → POST /api/v1/backoffice/transfers/
updateTransferItems({ id, items })     → PUT /api/v1/backoffice/transfers/{id}/items
completeTransfer({ id, accepted_by_id }) → POST /api/v1/backoffice/transfers/{id}/complete
```
Tag type: `"Transfers"`

---

## Files

### New files
| File | Purpose |
|------|---------|
| `src/services/warehousesApi.js` | RTK Query warehouse endpoints |
| `src/services/transfersApi.js` | RTK Query transfer endpoints |
| `src/pages/Warehouse.jsx` | Page component |
| `src/pages/Warehouse.module.css` | Page styles |

### Modified files
| File | Change |
|------|--------|
| `src/services/baseApi.js` | Add `"Warehouses"` and `"Transfers"` to `tagTypes` |
| `src/App.jsx` | Add `<Route path="/warehouse" element={<Warehouse />} />` |
| `src/components/layout/Sidebar.jsx` | Add "Ombor" entry in "Inventarizatsiya" section with warehouse icon |

### Reused existing services
- `src/services/catalogApi.js` — for product select in wizard Step 2
- `src/services/usersApi.js` — for user select in create warehouse modal and wizard Step 3

---

## Component Structure (Warehouse.jsx)

```
<Warehouse>
  ├── Left panel
  │   ├── <WarehouseList> (map over warehouses)
  │   └── Create warehouse modal
  └── Right panel
      ├── Tabs: Qoldiqlar | Nakładные | Nakładная yaratish
      ├── <BalancesTab> (balances table)
      ├── <TransfersTab> (transfers table + detail modal)
      └── <CreateTransferTab> (3-step wizard)
          ├── <WizardStep1> (type, from, to)
          ├── <WizardStep2> (dynamic items)
          └── <WizardStep3> (summary + accepted_by + complete)
```

All sub-components are defined in the same `Warehouse.jsx` file (consistent with existing pages like Transport.jsx).

---

## Language

UI labels in Uzbek, consistent with rest of the app:
- Склад → Ombor
- Остатки → Qoldiqlar
- Накладные → Nakładные
- Создать накладную → Nakładная yaratish
- Провести → O'tkazish
- Откуда → Kimdan
- Куда → Kimga
