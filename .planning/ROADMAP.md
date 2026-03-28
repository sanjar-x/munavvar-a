# Roadmap: HOD (Home & Office Delivery)

## Overview

This roadmap restructures the HOD water delivery platform from a working MVP with leaky bounded contexts into a clean DDD modular monolith, then builds three API audiences (Courier, Client, Staff) on top of the solid foundations. The approach is refactor-first: characterization tests lock current behavior, then modules are extracted one by one (STAFF/CATALOG first since they have no dependencies, then ledger separation, then LOGISTICS/CRM, then Orders decomposition), and finally the API layer is built on stable service interfaces.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Characterization Tests** - Lock existing business flows with tests before any refactoring
- [ ] **Phase 2: Module Convention & Database Foundation** - Establish the public.py facade pattern, frozen DTO convention, and rebuild Alembic migrations from scratch
- [ ] **Phase 3: STAFF & CATALOG Extraction** - Extract the first bounded contexts (no inter-module dependencies)
- [ ] **Phase 4: Ledger Separation** - Split Stock Ledger (INVENTORY) and Financial Ledger (BILLING) into independent modules
- [ ] **Phase 5: LOGISTICS & CRM Extraction** - Extract transfer documents into LOGISTICS and client data into CRM
- [ ] **Phase 6: Orders Decomposition & Application Orchestrators** - Slim the Orders god service, build FulfillmentService and OnboardingService, enforce architecture boundaries
- [ ] **Phase 7: Auth & Security Wiring** - Wire role-based auth for 3 API audiences with proper scopes and IDOR protection
- [ ] **Phase 8: Courier API** - Complete courier-facing API for route sheets, delivery, payment, and tara
- [ ] **Phase 9: Client API** - Complete client-facing API for ordering, history, balance, and address management
- [ ] **Phase 10: Staff API** - Complete staff-facing API for order management, warehouse ops, courier management, and reports

## Phase Details

### Phase 1: Characterization Tests
**Goal**: Existing business flows are locked by tests so refactoring cannot silently break them
**Depends on**: Nothing (first phase)
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. Order delivery fulfillment flow (stock debit + financial credit atomicity) is covered by a passing test
  2. Warehouse pickup flow is covered by a passing test
  3. Walk-in sale flow is covered by a passing test
  4. Courier shift close flow (cash reconciliation + van stock verification) is covered by a passing test
**Plans**: TBD

Plans:
- [ ] 01-01: TBD
- [ ] 01-02: TBD

### Phase 2: Module Convention & Database Foundation
**Goal**: Every module follows the same structural convention and the database starts clean
**Depends on**: Phase 1
**Requirements**: ARCH-02, ARCH-03, DB-01, DB-02
**Success Criteria** (what must be TRUE):
  1. At least one module demonstrates the complete public.py facade pattern (other modules import only from it)
  2. At least one module demonstrates the Repository -> Service -> frozen DTO return chain end-to-end
  3. Alembic migrations are rebuilt from scratch and produce a working schema with `alembic upgrade head`
  4. PG triggers for stock balance and financial balance enforcement exist in the fresh migration set
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD

### Phase 3: STAFF & CATALOG Extraction
**Goal**: STAFF and CATALOG exist as independent bounded contexts following the established convention
**Depends on**: Phase 2
**Requirements**: ARCH-10
**Success Criteria** (what must be TRUE):
  1. STAFF module owns employees, roles, and couriers with its own models, repository, service, and public.py facade
  2. CATALOG module owns products and pricing with its own models, repository, service, and public.py facade
  3. Other modules reference STAFF and CATALOG only through their public.py facades
  4. Characterization tests from Phase 1 still pass
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

### Phase 4: Ledger Separation
**Goal**: Stock Ledger and Financial Ledger operate as independent modules with clear ownership boundaries
**Depends on**: Phase 3
**Requirements**: ARCH-07
**Success Criteria** (what must be TRUE):
  1. INVENTORY module owns warehouses, stock balances, and the Stock Ledger (double-entry stock entries)
  2. BILLING module owns the Financial Ledger (double-entry financial entries), payments, and debt tracking
  3. Neither module imports from the other -- they are fully independent
  4. PG triggers still enforce balance consistency on both ledgers
  5. Characterization tests from Phase 1 still pass
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

### Phase 5: LOGISTICS & CRM Extraction
**Goal**: Transfer document management and client data each have dedicated bounded contexts
**Depends on**: Phase 4
**Requirements**: ARCH-08, ARCH-09
**Success Criteria** (what must be TRUE):
  1. LOGISTICS module owns StockTransfer documents, StockTransaction entries, and the transfer state machine (draft -> confirmed -> in_transit -> delivered)
  2. CRM module owns clients, addresses, contracts, and pricing
  3. Both modules follow the established convention (public.py facade, frozen DTOs, module-scoped UoW)
  4. Characterization tests from Phase 1 still pass
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

### Phase 6: Orders Decomposition & Application Orchestrators
**Goal**: Orders module is slim (lifecycle only), cross-domain logic lives in application-layer orchestrators, and architecture boundaries are enforced
**Depends on**: Phase 5
**Requirements**: ARCH-01, ARCH-04, ARCH-05, ARCH-06, TEST-05
**Success Criteria** (what must be TRUE):
  1. Orders service handles only order lifecycle (create, assign, cancel, status) -- no stock or financial logic
  2. FulfillmentService (application layer) orchestrates delivery confirmation across ORDERS, INVENTORY, LOGISTICS, and BILLING in a single transaction
  3. Each module UoW contains only its own repositories; composite UoWs exist only in application orchestrators
  4. pytest-archon boundary tests pass, enforcing that no module imports another module's internals (only public.py)
  5. All characterization tests from Phase 1 still pass
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD
- [ ] 06-03: TBD

### Phase 7: Auth & Security Wiring
**Goal**: Three API audiences (courier, client, staff) have properly scoped authentication and authorization
**Depends on**: Phase 6
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04
**Success Criteria** (what must be TRUE):
  1. JWT tokens include an `aud` claim that distinguishes courier, client, and staff audiences
  2. Courier endpoints require `ORDERS_DELIVER` scope (not the broader `ORDERS_EDIT`)
  3. Client endpoints require `ORDERS_CREATE` scope (not the broader `ORDERS_EDIT`)
  4. All client and courier endpoints have IDOR protection (users can only access their own resources)
**Plans**: TBD

Plans:
- [ ] 07-01: TBD
- [ ] 07-02: TBD

### Phase 8: Courier API
**Goal**: Couriers can manage their daily delivery workflow entirely through the API
**Depends on**: Phase 7
**Requirements**: COUR-01, COUR-02, COUR-03, COUR-04, COUR-05, COUR-06, COUR-07, COUR-08, COUR-09, COUR-10, COUR-11, COUR-12
**Success Criteria** (what must be TRUE):
  1. Courier can view their daily task list, see order details, and progress through delivery statuses (accept -> in_transit -> arrived -> delivered)
  2. Courier can confirm delivery with actual items delivered, tara returned, and payment collected -- including partial delivery and rejection scenarios
  3. Courier can view their van inventory (stock), cash/payment summary, and own profile
  4. Courier can create and fulfill an order on-site at a client location
  5. Courier can browse the product catalog and add delivery notes
**Plans**: TBD

Plans:
- [ ] 08-01: TBD
- [ ] 08-02: TBD
- [ ] 08-03: TBD

### Phase 9: Client API
**Goal**: Clients can place orders, track deliveries, and manage their account through the API
**Depends on**: Phase 7
**Requirements**: CLNT-01, CLNT-02, CLNT-03, CLNT-04, CLNT-05, CLNT-06, CLNT-07, CLNT-08, CLNT-09, CLNT-10, CLNT-11, CLNT-12, CLNT-13
**Success Criteria** (what must be TRUE):
  1. Client can place an order (select products, choose address, pick payment method) with tara availability check
  2. Client can view order history with filters, see active order status with courier contact, and cancel or reschedule before dispatch
  3. Client can view tara balance per address and financial balance (debt/credit for B2B, payment history for B2C)
  4. Client can manage delivery addresses (add, edit, remove) and view own profile
  5. Client can browse product catalog and reorder from history
**Plans**: TBD

Plans:
- [ ] 09-01: TBD
- [ ] 09-02: TBD
- [ ] 09-03: TBD

### Phase 10: Staff API
**Goal**: Staff can manage the entire business operation -- orders, clients, couriers, warehouse, and reporting -- through the API
**Depends on**: Phase 7, Phase 8 (staff needs to manage what couriers use)
**Requirements**: STAF-01, STAF-02, STAF-03, STAF-04, STAF-05, STAF-06, STAF-07, STAF-08, STAF-09, STAF-10, STAF-11, STAF-12, STAF-13, STAF-14, STAF-15, STAF-16
**Success Criteria** (what must be TRUE):
  1. Operator can search/filter orders, create orders on behalf of clients, assign couriers, and override order status
  2. Operator can manage clients (onboard, CRUD, view client card with balance + tara + orders) and manage couriers (CRUD, view courier card with van stock + tasks)
  3. Operator can manage warehouses (create, view stock), manage stock transfers, and perform courier loading/return operations
  4. Operator can close courier shifts (reconcile cash, verify van stock), process warehouse pickup sales, and adjust client tara balances
  5. Operator can view dashboard summaries, client debt report, and tara reconciliation report
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 10-01: TBD
- [ ] 10-02: TBD
- [ ] 10-03: TBD
- [ ] 10-04: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10
Note: Phases 8 and 9 can execute in parallel (both depend on Phase 7, not on each other).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Characterization Tests | 0/2 | Not started | - |
| 2. Module Convention & Database Foundation | 0/2 | Not started | - |
| 3. STAFF & CATALOG Extraction | 0/2 | Not started | - |
| 4. Ledger Separation | 0/2 | Not started | - |
| 5. LOGISTICS & CRM Extraction | 0/2 | Not started | - |
| 6. Orders Decomposition & Application Orchestrators | 0/3 | Not started | - |
| 7. Auth & Security Wiring | 0/2 | Not started | - |
| 8. Courier API | 0/3 | Not started | - |
| 9. Client API | 0/3 | Not started | - |
| 10. Staff API | 0/4 | Not started | - |
