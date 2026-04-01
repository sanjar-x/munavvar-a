# Moliya + Kassa — Design & Business Requirements

> Frontend sahifasi: `/finances` (mavjud) + `/cashbox` (yangi)
> Backend: `src/api/v1/backoffice/finances.py` — 11 ta endpoint tayyor

---

## 1. Hozirgi holat (As-Is)

### Backend — 100% tayyor

| #   | Endpoint                             | Method | Scope             | Vazifasi                                             |
| --- | ------------------------------------ | ------ | ----------------- | ---------------------------------------------------- |
| 1   | `/finances/dashboard`                | GET    | `finances:read`   | KPI kartalari: tushum, kassa, karta, qarz, kuryer    |
| 2   | `/finances/accounts`                 | GET    | `finances:read`   | Hisob-kitoblar ro'yxati (filter, search, pagination) |
| 3   | `/finances/accounts/{id}`            | GET    | `finances:read`   | Hisob tafsiloti + oxirgi 10 tranzaksiya              |
| 4   | `/finances/accounts/{id}/statement`  | GET    | `finances:read`   | Hisob bo'yicha ko'chirma (period, running balance)   |
| 5   | `/finances/transactions`             | GET    | `finances:read`   | Tranzaksiyalar ro'yxati (8 ta filter, pagination)    |
| 6   | `/finances/transactions`             | POST   | `finances:write`  | Qo'lda provodka yaratish (COMPLETED darhol)          |
| 7   | `/finances/transactions/{id}/verify` | PATCH  | `finances:write`  | PENDING → COMPLETED                                  |
| 8   | `/finances/transactions/{id}/reject` | PATCH  | `finances:write`  | PENDING → REJECTED (sabab bilan)                     |
| 9   | `/finances/couriers/summary`         | GET    | `finances:read`   | Kuryerlar kassalari svodkasi                         |
| 10  | `/finances/clients/debts`            | GET    | `finances:read`   | Qarzdor mijozlar ro'yxati                            |
| 11  | `/finances/cashbox/accept-payment`   | POST   | `payments:create` | Kassa: to'lovni qabul qilish (cash/card)             |

### Frontend — qisman tayyor

**`Finances.jsx`** sahifasi mavjud, 4 ta tab:

- **Umumiy** — dashboard KPI kartalari (5 ta)
- **Tranzaksiyalar** — jadval + verify/reject + status filter
- **Qarzdorlar** — qarzdor mijozlar jadvali
- **Kuryer kassalari** — kuryerlar svodka jadvali
- **+ Tranzaksiya** tugmasi — yangi provodka modal

**RTK Query** (`financesApi.js`) — 11 ta endpoint to'liq ulangan.

---

## 2. Yetishmayotgan funksionallik (Gap Analysis)

### 2.1. Finances sahifasiga qo'shilishi kerak

| #   | Xususiyat                        | Backend endpoint               | Holat                                                                |
| --- | -------------------------------- | ------------------------------ | -------------------------------------------------------------------- |
| A   | Hisoblar (Accounts) tab          | `GET /accounts`                | API tayyor, frontend YO'Q                                            |
| B   | Hisob tafsiloti (Account Detail) | `GET /accounts/{id}`           | API tayyor, frontend YO'Q                                            |
| C   | Hisob ko'chirmasi (Statement)    | `GET /accounts/{id}/statement` | API tayyor, frontend YO'Q                                            |
| D   | Tranzaksiya filtrlari (advanced) | `GET /transactions`            | API 8 filter qo'llab-quvvatlaydi, frontendda faqat `status` ishlaydi |
| E   | Qarzdorlar — `min_debt` filter   | `GET /clients/debts`           | API tayyor, frontend YO'Q                                            |

### 2.2. Kassa (Cashbox) sahifasi — butunlay yangi

| #   | Xususiyat                              | Backend endpoint                      |
| --- | -------------------------------------- | ------------------------------------- |
| F   | To'lovni qabul qilish (Accept Payment) | `POST /cashbox/accept-payment`        |
| G   | Kassa jurnali (bugungi tranzaksiyalar) | `GET /transactions` (date_from=today) |

---

## 3. Data Model — Tushunish uchun

### 3.1. Account (Hisob) turlari

```
AccountType (enum):
├── revenue   — Tizim: Umumiy tushum hisobi (manfiy = yaxshi)
├── cash      — Tizim: Markaziy kassa (naqd pul)
├── card      — Tizim: Ekvayring (karta)
├── bank      — Tizim: Bank hisobi
├── discount  — Tizim: Chegirmalar hisobi
├── client    — Mijoz: Shaxsiy hisob (ijobiy = qarz)
└── courier   — Kuryer: Kuryer kassasi (ijobiy = topshirilmagan pul)
```

### 3.2. Transaction (Tranzaksiya) holatlari

```
TransactionStatus (enum):
├── pending    — Kutilmoqda (karta to'lovlari)
├── completed  — Tasdiqlangan (naqd yoki tasdiqlangan karta)
└── rejected   — Rad etilgan (sabab bilan)
```

### 3.3. Pul oqimi (Money Flow)

```
Naqd to'lov:   CLIENT hisob → CASH hisob     (COMPLETED darhol)
Karta to'lov:  CLIENT hisob → CARD hisob     (PENDING → buxgalter VERIFY)
Inkassatsiya:  COURIER hisob → CASH hisob    (qo'lda provodka)
```

### 3.4. Summalar

Barcha summalar **butun sonlarda** (integer, tiyinlarda).
`150000` = `1 500,00 so'm`.
Frontend `fmt()` funksiyasi bilan formatlaydi.

---

## 4. Design Requirements — Finances sahifasi

### 4.1. Tab tuzilishi (yangilangan)

```
Moliya
├── Tab: Umumiy        (mavjud, o'zgarishsiz)
├── Tab: Tranzaksiyalar (mavjud, kengaytirish kerak)
├── Tab: Hisoblar       (YANGI)
├── Tab: Qarzdorlar     (mavjud, filter qo'shish)
└── Tab: Kuryer kassalari (mavjud, o'zgarishsiz)
```

### 4.2. Tab: Hisoblar (YANGI)

**Maqsad:** Barcha moliyaviy hisoblarni ko'rish, qidirish va tafsilotga o'tish.

#### Filtrlar (toolbar)

| Filter           | Turi            | API param  | Qiymatlari                                                   |
| ---------------- | --------------- | ---------- | ------------------------------------------------------------ |
| Hisob turi       | Select          | `type`     | Hammasi, Mijoz, Kuryer, Kassa, Karta, Bank, Tushum, Chegirma |
| Qidiruv          | Text Input      | `search`   | Hisob nomi yoki foydalanuvchi ismi                           |
| Faqat qarzdorlar | Toggle/Checkbox | `has_debt` | true/false                                                   |

#### Jadval ustunlari

| #   | Ustun        | Manba                           | Tekislash |
| --- | ------------ | ------------------------------- | --------- |
| 1   | Hisob nomi   | `name`                          | Left      |
| 2   | Turi         | `type` → badge                  | Left      |
| 3   | Egasi (User) | `user_id` (kelgusida user_name) | Left      |
| 4   | Balans       | `balance` → `fmt()`             | Right     |
| 5   | Yaratilgan   | `created_at` → `fmtDate()`      | Left      |
| 6   | Amallar      | "Ko'rish" tugmasi               | Center    |

#### Badge ranglar (account type)

| Type     | Badge label | Background | Color     |
| -------- | ----------- | ---------- | --------- |
| client   | Mijoz       | `#dbeafe`  | `#1d4ed8` |
| courier  | Kuryer      | `#fef3c7`  | `#92400e` |
| cash     | Kassa       | `#dcfce7`  | `#15803d` |
| card     | Karta       | `#f3e8ff`  | `#7c3aed` |
| revenue  | Tushum      | `#dcfce7`  | `#15803d` |
| bank     | Bank        | `#e0e7ff`  | `#4338ca` |
| discount | Chegirma    | `#fee2e2`  | `#b91c1c` |

#### "Ko'rish" tugmasi bosilganda

**Account Detail Modal** ochiladi (yoki inline panel):

```
┌──────────────────────────────────────────┐
│  Hisob: Kassal kuryer: Alisher           │
│  Turi: courier    Balans: 450 000 so'm   │
│  Egasi: Alisher Karimov                  │
│  Yaratilgan: 15.03.2026                  │
│                                          │
│  ── Oxirgi tranzaksiyalar ──             │
│  # | Kimdan      | Kimga    | Summa | ...│
│  1 | Mijoz Ali   | Bu hisob | 50000 | ...│
│  2 | Bu hisob    | Kassa    | 30000 | ...│
│                                          │
│  [Ko'chirma ko'rish]  [Yopish]           │
└──────────────────────────────────────────┘
```

**API:** `GET /accounts/{id}` → `AccountDetail` schema

#### "Ko'chirma ko'rish" bosilganda

**Statement Modal** (yoki alohida panel):

```
┌──────────────────────────────────────────────┐
│  Ko'chirma: Kassal kuryer: Alisher           │
│  Davr: [01.03.2026] — [31.03.2026]          │
│                                              │
│  Ochilish balansi:  120 000 so'm             │
│  Yopilish balansi:  450 000 so'm             │
│  Jami kirim:        380 000 so'm             │
│  Jami chiqim:        50 000 so'm             │
│                                              │
│  ── Tranzaksiyalar ──                        │
│  # | Yo'nalish | Kontragent | Summa | Qoldiq │
│  1 | Kirim     | Mijoz Ali  | 50000 | 170000 │
│  2 | Chiqim    | Kassa      | 30000 | 140000 │
│  ...                                         │
│  [◁ Oldingi] Sahifa 1 [Keyingi ▷]           │
└──────────────────────────────────────────────┘
```

**API:** `GET /accounts/{id}/statement`

**Statement response:**

```json
{
  "account": { "id": "...", "name": "...", "type": "courier" },
  "period": {
    "date_from": "2026-03-01",
    "date_to": "2026-03-31",
    "opening_balance": 120000,
    "closing_balance": 450000,
    "total_incoming": 380000,
    "total_outgoing": 50000
  },
  "transactions": [
    {
      "id": "...",
      "direction": "incoming",
      "counterparty": { "id": "...", "name": "Mijoz Ali", "type": "client" },
      "amount": 50000,
      "running_balance": 170000,
      "status": "completed",
      "reason": "To'lov buyurtma uchun",
      "order_id": null,
      "created_at": "2026-03-15T10:30:00"
    }
  ]
}
```

### 4.3. Tab: Tranzaksiyalar (kengaytirish)

Mavjud tab ga quyidagi filtrlar qo'shiladi:

#### Qo'shimcha filtrlar

| Filter           | UI element              | API param    |
| ---------------- | ----------------------- | ------------ |
| Hisob            | SearchSelect (accounts) | `account_id` |
| Buyurtma ID      | Text Input (UUID)       | `order_id`   |
| Sana boshlanishi | Date Input              | `date_from`  |
| Sana tugashi     | Date Input              | `date_to`    |
| Min summa        | Number Input            | `min_amount` |
| Maks summa       | Number Input            | `max_amount` |

#### Filter UI layout

```
┌────────────────────────────────────────────────────────────┐
│ [Hammasi] [Kutilmoqda] [Tasdiqlangan] [Rad etilgan]       │   ← mavjud
│                                                            │
│ Hisob: [▼ Tanlang]  Sana: [__/__/____] — [__/__/____]    │   ← YANGI
│ Summa: [min___] — [max___]  Buyurtma: [UUID___]           │   ← YANGI
│                                        [Tozalash]          │
└────────────────────────────────────────────────────────────┘
```

### 4.4. Tab: Qarzdorlar (kengaytirish)

Mavjud tab ga `min_debt` filter qo'shiladi:

```
┌─────────────────────────────────────────┐
│ Minimal qarz: [input___] so'm           │
└─────────────────────────────────────────┘
```

---

## 5. Design Requirements — Kassa sahifasi (YANGI)

### 5.1. Umumiy tushuncha

**Kassa** — kassir uchun alohida sahifa. Naqd yoki karta to'lovlarni qabul qilish uchun.

**Route:** `/cashbox`
**Roles:** `admin`, `manager` (ROUTE_ROLES ga qo'shish)
**Sidebar:** "Moliya" guruhida, "Moliya" ostida "Kassa" link qo'shiladi

### 5.2. Sahifa tuzilishi

```
┌─────────────────────────────────────────────────────────────────┐
│  Kassa                                                          │
│  [Umumiy]  [To'lov qabul qilish]                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │ Bugungi      │ │ Naqd        │ │ Karta        │              │
│  │ tushum       │ │ 2 450 000   │ │ 850 000      │              │
│  │ 3 300 000    │ │ so'm        │ │ so'm         │              │
│  │ so'm         │ │             │ │ (kutilmoqda) │              │
│  └─────────────┘ └─────────────┘ └─────────────┘               │
│                                                                 │
│  ── Bugungi tranzaksiyalar ──                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ # │ Vaqt  │ Mijoz      │ Summa       │ Usul  │ Holat       ││
│  │ 1 │ 14:30 │ Ali Valiev │ 150 000     │ Naqd  │ Tasdiqlangan││
│  │ 2 │ 14:15 │ OOO Suv    │ 500 000     │ Karta │ Kutilmoqda  ││
│  │ 3 │ 13:50 │ Bobur Sh.  │  75 000     │ Naqd  │ Tasdiqlangan││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3. Tab: Umumiy (Kassa Dashboard)

**KPI kartalari:**

| #   | Karta          | Ma'lumot manbai                                                        | Rang              |
| --- | -------------- | ---------------------------------------------------------------------- | ----------------- |
| 1   | Bugungi tushum | `dashboard.totals.total_revenue` (yoki bugungi tranzaksiyalar summasi) | positive (yashil) |
| 2   | Naqd tushum    | Bugungi COMPLETED tranzaksiyalar, `to_id = CASH account`               | positive          |
| 3   | Karta tushum   | Bugungi tranzaksiyalar, `to_id = CARD account`                         | neutral (ko'k)    |
| 4   | Kutilmoqda     | `dashboard.pending_transactions_count`                                 | neutral           |

**Bugungi tranzaksiyalar jadvali:**

Faqat bugungi tranzaksiyalarni ko'rsatadi. Filter:

```js
getTransactions({
  date_from: todayStart.toISOString(),
  size: 50,
  page: 1,
});
```

| #   | Ustun | Manba                                           |
| --- | ----- | ----------------------------------------------- |
| 1   | Vaqt  | `created_at` → soat:daqiqa                      |
| 2   | Mijoz | `from_account.name`                             |
| 3   | Summa | `amount` → `fmt()`                              |
| 4   | Usul  | `to_account.type === 'cash'` ? "Naqd" : "Karta" |
| 5   | Holat | `status` → badge                                |
| 6   | Izoh  | `reason`                                        |

### 5.4. Tab: To'lov qabul qilish (Accept Payment Form)

**Forma tuzilishi:**

```
┌──────────────────────────────────────────┐
│  To'lov qabul qilish                     │
│                                          │
│  Mijoz *                                 │
│  [▼ Mijozni qidiring...]                │  ← SearchSelect (clientsApi dan)
│                                          │
│  Buyurtma (ixtiyoriy)                    │
│  [▼ Buyurtmani tanlang...]              │  ← SearchSelect (ordersApi dan)
│                                          │
│  To'lov usuli *                          │
│  ( ) Naqd    ( ) Karta                  │  ← Radio buttons
│                                          │
│  Summa *                                 │
│  [____________] so'm                     │
│                                          │
│  Izoh *                                  │
│  [____________]                          │
│                                          │
│     [Bekor qilish]   [To'lovni qabul qilish]
│                                          │
│  ───────────────────────────────────────  │
│  ℹ Naqd to'lov darhol tasdiqlanadi.      │
│    Karta to'lov buxgalter tasdiqlashini  │
│    kutadi.                               │
└──────────────────────────────────────────┘
```

#### Forma maydonlari

| #   | Maydon       | Turi         | Validatsiya                  | API param            |
| --- | ------------ | ------------ | ---------------------------- | -------------------- |
| 1   | Mijoz        | SearchSelect | Majburiy, UUID               | `client_id`          |
| 2   | Buyurtma     | SearchSelect | Ixtiyoriy, UUID              | `order_id`           |
| 3   | To'lov usuli | Radio        | Majburiy, "cash" yoki "card" | `payment_method`     |
| 4   | Summa        | Number Input | Majburiy, > 0                | `amount` (butun son) |
| 5   | Izoh         | Text Input   | Majburiy, 3-255 belgi        | `reason`             |

#### Biznes qoidalar

1. **Naqd to'lov:** `CLIENT → CASH`, status = `COMPLETED` darhol
2. **Karta to'lov:** `CLIENT → CARD`, status = `PENDING` (buxgalter tasdiqlaguncha)
3. Muvaffaqiyatdan keyin: `toast.success()` + formani tozalash
4. Xatolikda: `toast.error(err.data.error.message)`

#### API chaqiruv

```js
// acceptPayment mutation
POST /api/v1/backoffice/finances/cashbox/accept-payment
Body: {
  "client_id": "uuid",
  "amount": 150000,
  "payment_method": "cash",
  "reason": "Suv to'lovi",
  "order_id": "uuid | null"
}
```

#### Muvaffaqiyatli javob

```json
{
  "id": "txn-uuid",
  "from_id": "client-account-uuid",
  "to_id": "cash-account-uuid",
  "from_account": {
    "id": "...",
    "name": "Mijoz hisobi: Ali",
    "type": "client"
  },
  "to_account": { "id": "...", "name": "Markaziy kassa", "type": "cash" },
  "amount": 150000,
  "status": "completed",
  "reason": "Suv to'lovi",
  "verified_by_id": "cashier-user-uuid",
  "created_at": "2026-04-01T14:30:00"
}
```

---

## 6. Rol va ruxsatlar

### Kimlar ko'radi

| Sahifa                | Rollar                                           | Scope                             |
| --------------------- | ------------------------------------------------ | --------------------------------- |
| `/finances` (hammasi) | admin, accountant                                | `finances:read`, `finances:write` |
| `/cashbox`            | admin, cashier, (courier - faqat o'z sahifasida) | `payments:create`                 |

### Frontend rol tekshiruvi

```js
// routeConfig.js ga qo'shish
ROUTE_ROLES["/finances"] = ["admin", "accountant"];
ROUTE_ROLES["/cashbox"] = ["admin", "cashier"];
```

### Sidebar yangilanishi

```js
// Sidebar.jsx SECTIONS ga qo'shish
{
  title: "Moliya",
  items: [
    { path: "/finances", label: "Moliya", icon: "..." },
    { path: "/cashbox", label: "Kassa", icon: "..." },  // YANGI
  ]
}
```

---

## 7. RTK Query — Cache invalidation

### Tag turlari (mavjud)

```
Finances: DASHBOARD, ACCOUNTS, TRANSACTIONS, WALLETS, DEBTS
```

### Invalidation matritsasi

| Mutation            | Invalidates                      |
| ------------------- | -------------------------------- |
| `createTransaction` | TRANSACTIONS, DASHBOARD, WALLETS |
| `verifyTransaction` | TRANSACTIONS, DASHBOARD          |
| `rejectTransaction` | TRANSACTIONS, DASHBOARD          |
| `acceptPayment`     | TRANSACTIONS, DASHBOARD, DEBTS   |

---

## 8. Xatolik holatlari

### Backend xatoliklar

| Error Code                   | HTTP | Sabab                                                 |
| ---------------------------- | ---- | ----------------------------------------------------- |
| `ACCOUNT_NOT_FOUND`          | 404  | Hisob topilmadi                                       |
| `TRANSACTION_NOT_FOUND`      | 404  | Tranzaksiya topilmadi                                 |
| `INSUFFICIENT_FUNDS`         | 409  | Yetarli mablag' yo'q                                  |
| `SELF_TRANSFER_NOT_ALLOWED`  | 409  | O'ziga o'tkazish taqiqlangan                          |
| `INVALID_TRANSACTION_STATUS` | 409  | Noto'g'ri holat (masalan, COMPLETED ni verify qilish) |
| `INVALID_TRANSACTION_AMOUNT` | 400  | Summa <= 0                                            |

### Frontend xatolik ko'rsatish

```js
// Barcha mutation xatoliklar uchun yagona pattern
catch (err) {
  const msg = err?.data?.error?.message ?? "Xatolik yuz berdi";
  toast.error(msg);
}
```

---

## 9. Implementation Flow (Bajarish tartibi)

### Phase 1: Finances sahifasini kengaytirish

```
1.1  Hisoblar (Accounts) tab qo'shish
     ├── Filter toolbar (type, search, has_debt)
     ├── Accounts jadval
     └── Pagination

1.2  Account Detail modal
     ├── Hisob ma'lumotlari
     └── Oxirgi 10 tranzaksiya jadvali

1.3  Account Statement modal
     ├── DateRange picker (date_from, date_to)
     ├── Period summary kartalari
     └── Tranzaksiyalar jadvali (running_balance bilan)

1.4  Tranzaksiyalar tab — advanced filtrlar
     ├── Account SearchSelect
     ├── Date range inputs
     ├── Amount range inputs
     └── Order ID input

1.5  Qarzdorlar tab — min_debt filter
```

### Phase 2: Kassa sahifasi (yangi)

```
2.1  Sahifa yaratish
     ├── pages/Cashbox.jsx
     ├── pages/Cashbox.module.css
     ├── Route qo'shish (App.jsx)
     ├── ROUTE_ROLES qo'shish (routeConfig.js)
     └── Sidebar link qo'shish

2.2  Kassa Dashboard tab
     ├── KPI summary kartalari (bugungi statistika)
     └── Bugungi tranzaksiyalar jadvali

2.3  To'lov qabul qilish tab
     ├── Forma (SearchSelect + radio + inputs)
     ├── Validatsiya
     ├── acceptPayment mutation chaqiruvi
     └── Toast success/error
```

### Phase 3: Polish

```
3.1  Loading states (Skeleton)
3.2  Empty states
3.3  Responsive layout
3.4  Edge cases (0 balans, juda katta raqamlar)
```

---

## 10. Komponent arxitekturasi

### Fayl tuzilishi

```
frontend/src/
├── pages/
│   ├── Finances.jsx          # Mavjud — kengaytirish
│   ├── Finances.module.css   # Mavjud — yangi stillar qo'shish
│   ├── Cashbox.jsx           # YANGI
│   └── Cashbox.module.css    # YANGI
├── services/
│   └── financesApi.js        # Mavjud — to'liq (11 endpoint)
└── config/
    └── routeConfig.js        # ROUTE_ROLES ga /cashbox qo'shish
```

### Komponent ierarxiyasi — Finances.jsx

```
<Finances>
  ├── <Header> (title + tabs + "+ Tranzaksiya" button)
  ├── Tab: "overview"      → <OverviewTab />          (mavjud)
  ├── Tab: "transactions"  → <TransactionsTab />       (kengaytirish)
  ├── Tab: "accounts"      → <AccountsTab />           (YANGI)
  │   ├── <AccountsToolbar />
  │   ├── <AccountsTable />
  │   └── <Pagination />
  ├── Tab: "debts"         → <DebtsTab />              (kengaytirish)
  ├── Tab: "wallets"       → <WalletsTab />            (mavjud)
  ├── <CreateTransactionModal />                        (mavjud)
  ├── <AccountDetailModal />                            (YANGI)
  └── <AccountStatementModal />                         (YANGI)
```

### Komponent ierarxiyasi — Cashbox.jsx

```
<Cashbox>
  ├── <Header> (title + tabs)
  ├── Tab: "dashboard"  → <CashboxDashboard />
  │   ├── <SummaryCards />
  │   └── <TodayTransactionsTable />
  └── Tab: "accept"     → <AcceptPaymentForm />
      ├── <SearchSelect /> (mijoz)
      ├── <SearchSelect /> (buyurtma)
      ├── <RadioGroup /> (naqd/karta)
      ├── <Input /> (summa)
      ├── <Input /> (izoh)
      └── <Button /> (submit)
```

---

## 11. API Response Schemas — Frontend uchun muhim

### Dashboard Response

```typescript
{
  system_accounts: {
    [type: string]: {
      id: string,
      balance: number,      // tiyinda
      name: string
    }
  },
  totals: {
    total_revenue: number,       // doimo manfiy → ijobiy qilib ko'rsatiladi
    total_cash_in_hand: number,
    total_card_pending: number,
    total_client_debt: number,
    total_courier_cash: number
  },
  pending_transactions_count: number
}
```

### Accounts List Response

```typescript
{
  total_count: number,
  accounts: [{
    id: string,
    user_id: string,
    name: string,
    type: "revenue" | "cash" | "card" | "bank" | "discount" | "client" | "courier",
    balance: number,
    created_at: string,      // ISO datetime
    updated_at: string
  }]
}
```

### Account Detail Response

```typescript
{
  id: string,
  user_id: string,
  name: string,
  type: string,
  balance: number,
  created_at: string,
  updated_at: string,
  user_name: string | null,
  recent_transactions: [{
    id: string,
    from_account: { id: string, name: string, type: string },
    to_account: { id: string, name: string, type: string },
    amount: number,
    status: "pending" | "completed" | "rejected",
    reason: string,
    order_id: string | null,
    verified_by_id: string | null,
    created_at: string
  }]
}
```

### Account Statement Response

```typescript
{
  account: { id: string, name: string, type: string },
  period: {
    date_from: string,        // "2026-03-01"
    date_to: string,          // "2026-03-31"
    opening_balance: number,
    closing_balance: number,
    total_incoming: number,
    total_outgoing: number
  },
  transactions: [{
    id: string,
    direction: "incoming" | "outgoing",
    counterparty: { id: string, name: string, type: string },
    amount: number,
    running_balance: number,
    status: string,
    reason: string,
    order_id: string | null,
    created_at: string
  }]
}
```

### Transactions List Response

```typescript
{
  total_count: number,
  transactions: [{
    id: string,
    from_account: { id: string, name: string, type: string },
    to_account: { id: string, name: string, type: string },
    amount: number,
    status: "pending" | "completed" | "rejected",
    reason: string,
    order_id: string | null,
    verified_by_id: string | null,
    created_at: string
  }]
}
```

### Couriers Summary Response

```typescript
{
  couriers: [{
    courier_id: string,
    courier_name: string,
    account_id: string,
    cash_balance: number,
    today_collected: number,
    today_deposited: number,
    pending_deposit: number
  }],
  total_courier_cash: number,
  total_pending_deposit: number
}
```

### Client Debts Response

```typescript
{
  total_debt: number,
  debtors_count: number,
  clients: [{
    client_id: string,
    client_name: string,
    role: string,
    phone: string | null,
    account_id: string,
    balance: number,
    last_payment_date: string | null
  }]
}
```

### Accept Payment Response

```typescript
{
  id: string,
  from_id: string,
  to_id: string,
  from_account: { id: string, name: string, type: string } | null,
  to_account: { id: string, name: string, type: string } | null,
  order_id: string | null,
  amount: number,
  status: "completed" | "pending",
  reason: string,
  verified_by_id: string | null,
  created_at: string
}
```

---

## 12. Muhim biznes qoidalar (Business Rules)

1. **Balanslar faqat PG trigger orqali o'zgaradi** — frontend hech qachon balansni o'zi hisoblamaydi, faqat API dan oladi
2. **Append-only ledger** — tranzaksiyalar o'chirilmaydi va tahrirlanmaydi, faqat status o'zgaradi
3. **Revenue hisob doimo manfiy** — `total_revenue = -revenue_balance` (backend buni qiladi)
4. **Mijoz balansi ijobiy = qarz** — mijoz hisobida `balance > 0` degani u bizga qarzdor
5. **Kuryer balansi ijobiy = topshirilmagan pul** — kuryer yig'gan pul, kassaga topshirilmagan
6. **Naqd to'lov = darhol COMPLETED** — kassir tasdiqlamasdan
7. **Karta to'lov = PENDING** — buxgalter VERIFY yoki REJECT qilishi kerak
8. **from_id != to_id** — o'ziga o'tkazish mumkin emas (DB constraint + backend validation)
9. **amount > 0** — manfiy yoki nol summa mumkin emas (DB constraint + Pydantic validation)
10. **Summalar tiyinda** — `1 so'm = 1 unit` (aslida integer sifatida saqlanadi, lekin biznes mantiqda 1:1)
