# Requirements: HOD (Home & Office Delivery)

**Defined:** 2026-03-28
**Core Value:** Dual ledger integrity -- every stock movement and financial transaction traceable through double-entry bookkeeping

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Architecture

- [ ] **ARCH-01**: All 6 bounded contexts cleanly separated with own models, repositories, services, schemas
- [ ] **ARCH-02**: Each module exposes `public.py` facade -- other modules import only from this
- [ ] **ARCH-03**: Unified Repository -> Service -> frozen DTO (`dataclasses(frozen=True, slots=True)`) pattern across all modules
- [ ] **ARCH-04**: Composite UoWs decomposed -- each module UoW contains only its own repositories
- [ ] **ARCH-05**: Application-layer orchestrators (FulfillmentService, OnboardingService) handle cross-domain transactions
- [ ] **ARCH-06**: Orders God Service (1,151 lines) decomposed -- fulfillment logic extracted to application layer
- [ ] **ARCH-07**: Stock Ledger (INVENTORY) and Financial Ledger (BILLING) cleanly separated as independent modules
- [ ] **ARCH-08**: LOGISTICS module owns StockTransfer documents and StockTransaction entries
- [ ] **ARCH-09**: CRM module owns clients, addresses, contracts, pricing
- [ ] **ARCH-10**: STAFF module owns employees, roles, couriers

### Testing

- [ ] **TEST-01**: Characterization tests for order delivery fulfillment flow (stock + financial atomicity)
- [ ] **TEST-02**: Characterization tests for warehouse pickup flow
- [ ] **TEST-03**: Characterization tests for walk-in sale flow
- [ ] **TEST-04**: Characterization tests for courier shift close flow
- [ ] **TEST-05**: Architecture boundary tests (pytest-archon) enforcing module import rules

### Database

- [ ] **DB-01**: Alembic migrations rebuilt from scratch (clean schema)
- [ ] **DB-02**: PG triggers preserved for ledger balance enforcement (stock + financial)

### Auth & Security

- [ ] **AUTH-01**: Courier endpoints use `ORDERS_DELIVER` scope (not `ORDERS_EDIT`)
- [ ] **AUTH-02**: Client endpoints use `ORDERS_CREATE` scope (not `ORDERS_EDIT`)
- [ ] **AUTH-03**: JWT `aud` (audience) claim distinguishes 3 API audiences (courier, client, staff)
- [ ] **AUTH-04**: IDOR protection wired on all client and courier endpoints

### Courier API

- [ ] **COUR-01**: Courier sees daily task list sorted by delivery sequence with address + phone
- [ ] **COUR-02**: Courier views order detail (items, quantities, client address, phone, payment method)
- [ ] **COUR-03**: Courier signals accept/start delivery (triggers IN_TRANSIT status)
- [ ] **COUR-04**: Courier signals arrival at client (triggers ARRIVED status)
- [ ] **COUR-05**: Courier confirms delivery with actual items delivered, tara returned, payment collected
- [ ] **COUR-06**: Courier views own van inventory (full bottles, empty bottles, equipment)
- [ ] **COUR-07**: Courier views cash/payment summary for reconciliation
- [ ] **COUR-08**: Courier views own profile (name, phone, assigned warehouse)
- [ ] **COUR-09**: Courier browses product catalog with prices
- [ ] **COUR-10**: Courier records partial delivery / rejection (auto-adjusts stock + financials)
- [ ] **COUR-11**: Courier creates and fulfills order on-site at client location
- [ ] **COUR-12**: Courier adds delivery notes/comments to completed delivery

### Client API

- [ ] **CLNT-01**: Client places order (select products, choose address, pick payment method)
- [ ] **CLNT-02**: Client checks tara availability before ordering
- [ ] **CLNT-03**: Client views order history with pagination and date filters
- [ ] **CLNT-04**: Client sees active order status with courier contact info when assigned
- [ ] **CLNT-05**: Client cancels order before it enters transit
- [ ] **CLNT-06**: Client views tara (bottle) balance per delivery address
- [ ] **CLNT-07**: Client views delivery addresses (inventory points)
- [ ] **CLNT-08**: Client views own profile (name, phone, addresses)
- [ ] **CLNT-09**: Client browses product catalog with prices
- [ ] **CLNT-10**: Client views financial balance (debt/credit for B2B, payment history for B2C)
- [ ] **CLNT-11**: Client reschedules delivery to different date before dispatch
- [ ] **CLNT-12**: Client manages own delivery addresses (add, edit, remove)
- [ ] **CLNT-13**: Client reorders from history (copy past order into new draft)

### Staff API

- [ ] **STAF-01**: Operator searches orders with filters (status, date, courier, client, amount)
- [ ] **STAF-02**: Operator creates order on behalf of client (phone orders)
- [ ] **STAF-03**: Dispatcher assigns/reassigns courier to order
- [ ] **STAF-04**: Operator manually overrides order status
- [ ] **STAF-05**: Full client management (onboard, CRUD, view client card with balance + tara + orders)
- [ ] **STAF-06**: Full courier management (CRUD, view courier card with van stock + tasks)
- [ ] **STAF-07**: Warehouse management (create warehouses, view stock levels)
- [ ] **STAF-08**: Stock transfer management (create/manage supply, inter-warehouse, courier load/return)
- [ ] **STAF-09**: Shift close (reconcile courier cash, collect money, verify van stock)
- [ ] **STAF-10**: Warehouse pickup sale (walk-in customer at counter)
- [ ] **STAF-11**: Dedicated courier loading endpoint (load van from warehouse before shift)
- [ ] **STAF-12**: Dedicated courier return endpoint (unload van to warehouse after shift)
- [ ] **STAF-13**: Client tara capitalization (manual set/adjust tara balance)
- [ ] **STAF-14**: Dashboard summaries (today's orders, revenue, deliveries, courier utilization)
- [ ] **STAF-15**: Client debt report (who owes, sorted by amount/age)
- [ ] **STAF-16**: Tara reconciliation report (bottle holding by client, unreturned alerts)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Client Features

- **CLNT-V2-01**: Recurring order / subscription engine (auto-create orders on schedule)
- **CLNT-V2-02**: B2B invoice access with PDF generation

### Staff Features

- **STAF-V2-01**: Batch courier assignment (assign multiple orders to courier in one action)
- **STAF-V2-02**: Courier performance view (deliveries/day, average time, success rate)
- **STAF-V2-03**: Bulk order creation (create orders for multiple clients at once)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Real-time GPS tracking | WebSocket excluded per project constraints. Status-based tracking sufficient for water delivery |
| Push notifications | Requires mobile app infrastructure (FCM/APNS). Web-first approach |
| Route optimization / navigation | Water delivery routes are fixed weekly patterns. Third-party API cost not justified |
| Payment gateway (Stripe, etc.) | Cash and P2P card transfers are the payment reality. Manual recording sufficient |
| Photo proof of delivery | Tara count serves as delivery proof. File storage complexity not justified |
| Multi-language (i18n) | Single-market deployment (Uzbekistan) |
| Courier earnings/payroll | Out of scope for delivery management. Handled by external HR/payroll |
| Customer ratings/reviews | Water delivery is a utility, not a marketplace |
| Chat / messaging | Phone calls sufficient. Real-time infrastructure not justified |
| Mobile app | Web-first. Mobile deferred to future milestone |
| Offline delivery confirmation | Requires mobile app with sync engine |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ARCH-01 | Phase 6 | Pending |
| ARCH-02 | Phase 2 | Pending |
| ARCH-03 | Phase 2 | Pending |
| ARCH-04 | Phase 6 | Pending |
| ARCH-05 | Phase 6 | Pending |
| ARCH-06 | Phase 6 | Pending |
| ARCH-07 | Phase 4 | Pending |
| ARCH-08 | Phase 5 | Pending |
| ARCH-09 | Phase 5 | Pending |
| ARCH-10 | Phase 3 | Pending |
| TEST-01 | Phase 1 | Pending |
| TEST-02 | Phase 1 | Pending |
| TEST-03 | Phase 1 | Pending |
| TEST-04 | Phase 1 | Pending |
| TEST-05 | Phase 6 | Pending |
| DB-01 | Phase 2 | Pending |
| DB-02 | Phase 2 | Pending |
| AUTH-01 | Phase 7 | Pending |
| AUTH-02 | Phase 7 | Pending |
| AUTH-03 | Phase 7 | Pending |
| AUTH-04 | Phase 7 | Pending |
| COUR-01 | Phase 8 | Pending |
| COUR-02 | Phase 8 | Pending |
| COUR-03 | Phase 8 | Pending |
| COUR-04 | Phase 8 | Pending |
| COUR-05 | Phase 8 | Pending |
| COUR-06 | Phase 8 | Pending |
| COUR-07 | Phase 8 | Pending |
| COUR-08 | Phase 8 | Pending |
| COUR-09 | Phase 8 | Pending |
| COUR-10 | Phase 8 | Pending |
| COUR-11 | Phase 8 | Pending |
| COUR-12 | Phase 8 | Pending |
| CLNT-01 | Phase 9 | Pending |
| CLNT-02 | Phase 9 | Pending |
| CLNT-03 | Phase 9 | Pending |
| CLNT-04 | Phase 9 | Pending |
| CLNT-05 | Phase 9 | Pending |
| CLNT-06 | Phase 9 | Pending |
| CLNT-07 | Phase 9 | Pending |
| CLNT-08 | Phase 9 | Pending |
| CLNT-09 | Phase 9 | Pending |
| CLNT-10 | Phase 9 | Pending |
| CLNT-11 | Phase 9 | Pending |
| CLNT-12 | Phase 9 | Pending |
| CLNT-13 | Phase 9 | Pending |
| STAF-01 | Phase 10 | Pending |
| STAF-02 | Phase 10 | Pending |
| STAF-03 | Phase 10 | Pending |
| STAF-04 | Phase 10 | Pending |
| STAF-05 | Phase 10 | Pending |
| STAF-06 | Phase 10 | Pending |
| STAF-07 | Phase 10 | Pending |
| STAF-08 | Phase 10 | Pending |
| STAF-09 | Phase 10 | Pending |
| STAF-10 | Phase 10 | Pending |
| STAF-11 | Phase 10 | Pending |
| STAF-12 | Phase 10 | Pending |
| STAF-13 | Phase 10 | Pending |
| STAF-14 | Phase 10 | Pending |
| STAF-15 | Phase 10 | Pending |
| STAF-16 | Phase 10 | Pending |

**Coverage:**
- v1 requirements: 62 total
- Mapped to phases: 62
- Unmapped: 0

---
*Requirements defined: 2026-03-28*
*Last updated: 2026-03-28 after roadmap creation*
