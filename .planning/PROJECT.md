# HOD (Home & Office Delivery)

## What This Is

A B2B/B2C water delivery management platform that automates the full cycle: from client order intake through courier delivery, stock movement between warehouses, and financial reconciliation. Built as a DDD modular monolith with Python/FastAPI/PostgreSQL. Currently a working MVP requiring architectural cleanup and API buildout.

## Core Value

The dual ledger system (Stock Ledger + Financial Ledger) must always maintain integrity — every stock movement and financial transaction is traceable through double-entry bookkeeping. If everything else breaks, the ledgers must be correct.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. Inferred from existing codebase. -->

- ✓ JWT authentication with RBAC (8 roles, scope-based permissions) — existing
- ✓ Order creation, status management, fulfillment flow — existing
- ✓ Stock Ledger with PG trigger-enforced balances — existing (partial, needs separation)
- ✓ Financial Ledger with append-only enforcement — existing (partial, needs separation)
- ✓ StockTransfer document flow (draft → confirmed → in_transit → delivered) — existing
- ✓ Warehouse pickup and walk-in sale flows — existing
- ✓ Product catalog with pricing — existing
- ✓ Client and courier management — existing
- ✓ Database seeder for test data — existing
- ✓ Backoffice API endpoints (partial) — existing
- ✓ Frontend admin SPA (React 19, RTK Query, 13 pages) — existing

### Active

<!-- Current scope. Building toward these. -->

- [ ] Clean separation of 6 bounded contexts (INVENTORY, LOGISTICS, ORDERS, BILLING, STAFF, CRM)
- [ ] Proper Stock Ledger / Financial Ledger split with independent services
- [ ] Unified Repository → Service → frozen DTO pattern across all modules
- [ ] Consistent module structure convention for all domains
- [ ] Courier API: route sheets, delivery confirmation, payment collection, tara return
- [ ] Client API: order placement, delivery history, balance view, tara balance
- [ ] Staff/Operator API: order management, warehouse operations, billing, reports
- [ ] Role-based auth wiring for 3 API audiences (courier, client, staff)
- [ ] Alembic migrations rebuilt from scratch (fresh start, no legacy migration debt)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Mobile apps — web-first, mobile later
- Real-time notifications (WebSocket) — not needed for MVP delivery flows
- Multi-tenancy — single organization deployment
- External payment gateway integration — manual payment recording (cash, P2P) is sufficient
- Advanced reporting/analytics dashboards — basic reports in Staff API, analytics deferred
- Frontend rebuild — existing React SPA is functional, focus is backend

## Context

**Domain:** Bottled water delivery for coolers. B2B clients (offices, restaurants) and B2C (private individuals). Key physical assets: full water bottles, empty bottles (tara), equipment (coolers, pumps).

**Existing codebase:** Working MVP with 6 domain modules (`auth`, `users`, `catalog`, `orders`, `inventory`, `finances`), application-layer orchestration (`client`, `courier`, `order`, `inventories`), and FastAPI API layer. ~220 lines architecture, PostgreSQL triggers enforce ledger integrity.

**Pain points driving restructuring:**
1. Ledger logic mixed with order business logic — bounded contexts leak
2. Stock Ledger and Financial Ledger not cleanly separated as independent services
3. Service layer inconsistent — some return ORM objects, some return DTOs
4. File/module structure lacks unified convention across domains

**Approach:** Refactor first (clean foundations), then build API layer on solid ground. Database can be rebuilt fresh — no production data migration needed.

**Target domain model (6 Bounded Contexts):**
- **INVENTORY** — Warehouses, stock balances, Stock Ledger (double-entry)
- **LOGISTICS** — StockTransfer documents, StockTransaction entries, state machine
- **ORDERS** — Order lifecycle, assignment, fulfillment
- **BILLING** — Financial Ledger (double-entry), payments, debt tracking, reconciliation
- **STAFF** — Employees, roles, couriers (as stock + cash accountability points)
- **CRM** — Clients, addresses, contracts, pricing, delivery schedules

## Constraints

- **Tech stack**: Python 3.14+, SQLAlchemy 2.x (async), PostgreSQL, FastAPI, Alembic — non-negotiable
- **Architecture**: DDD modular monolith — modules communicate via services, not direct model access
- **Ledger integrity**: PG triggers enforce balance consistency — application code cannot bypass
- **lazy="raise"**: On bulk-risk SQLAlchemy relationships — no accidental N+1 queries
- **ondelete="RESTRICT"**: On critical foreign keys — no silent cascade deletes
- **Service returns**: Frozen DTOs only — never expose ORM objects to consumers

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Refactor before API | Clean foundations prevent accumulating tech debt in new API code | — Pending |
| Fresh database start | No production data to preserve, enables clean schema rebuild | — Pending |
| Dual Ledger separation | Stock and Financial are different domains with different rules | — Pending |
| 3 API audiences (Courier/Client/Staff) | Maps to real user roles and device contexts | — Pending |
| Frozen DTOs from services | Prevents ORM session leaks, enforces clean boundaries | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-28 after initialization*
