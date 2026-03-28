# Research Summary: HOD DDD Restructuring

**Domain:** Water delivery DDD modular monolith restructuring
**Researched:** 2026-03-28
**Overall confidence:** HIGH

## Executive Summary

The existing HOD codebase is a working MVP with strong foundational patterns (UoW, repository abstraction, PG trigger-enforced dual ledgers) but has bounded context leakage that will compound as API buildout proceeds. The Orders module currently acts as a "god service" orchestrating stock movements, financial settlements, and order lifecycle in a single 1151-line service file with UoWs that compose 8-11 repositories spanning 3-5 modules.

The restructuring requires splitting the current 6 modules (`auth`, `users`, `catalog`, `orders`, `inventory`, `finances`) plus 4 application orchestrators into 7 bounded contexts (STAFF, CATALOG, CRM, INVENTORY, LOGISTICS, BILLING, ORDERS) with 2 explicit application-layer orchestrators (Fulfillment, Onboarding). The critical change is extracting fulfillment logic (stock transfer creation + financial settlement) out of the Orders service into a dedicated application-layer orchestrator that calls module-level services through public API facades.

The dual ledger separation (Stock Ledger in INVENTORY, Financial Ledger in BILLING) is the architectural centerpiece. Both ledgers are already enforced by PG triggers that make them append-only with materialized balance views. The separation is about module ownership boundaries, not database changes -- the triggers and tables remain, but the services that write to them become module-scoped.

The technology stack is settled (Python 3.14, FastAPI, SQLAlchemy 2.x async, PostgreSQL, Alembic) and does not need changes. This is purely an architectural restructuring of module boundaries, service responsibilities, and inter-module communication patterns.

## Key Findings

**Stack:** No changes needed. Python 3.14 + FastAPI + SQLAlchemy 2.x async + PostgreSQL is the right stack. The codebase already uses modern Python features (PEP 695 generics, UUIDv7, StrEnum).

**Architecture:** Restructure from 6 leaky modules to 7 bounded contexts with public API facades (`public.py` per module). Cross-domain orchestration moves to explicit application-layer services. Module UoWs shrink to own-table-only; application UoWs handle cross-domain transactions.

**Critical pitfall:** The biggest risk is breaking the dual-ledger atomicity invariant during restructuring. Stock movements and financial settlements MUST remain in the same DB transaction. This means application-layer orchestrators must compose a single UoW/session for cross-domain writes.

## Implications for Roadmap

Based on research, suggested phase structure:

1. **Foundation & Common Patterns** - Establish the module public API pattern, frozen DTO convention, and restructure STAFF + CATALOG (no dependencies on other modules)
   - Addresses: Consistent module structure convention, frozen DTO boundary
   - Avoids: Breaking existing functionality while changing core patterns

2. **Ledger Separation** - Split current `inventory` into INVENTORY (Stock Ledger) + LOGISTICS (transfers). Rename `finances` to BILLING.
   - Addresses: Clean Stock Ledger / Financial Ledger split
   - Avoids: The "god UoW" anti-pattern where inventory UoW includes financial repos

3. **Domain Module Completion** - Slim down ORDERS (extract fulfillment logic), establish CRM module
   - Addresses: Clean bounded context separation for all 7 modules
   - Avoids: Leaving fulfillment logic scattered across Orders

4. **Application Layer Orchestration** - Build FulfillmentService and OnboardingService as explicit cross-domain orchestrators
   - Addresses: Cross-domain use cases with proper transaction boundaries
   - Avoids: Re-creating god services at the module level

5. **API Layer Buildout** - Staff, Courier, and Client APIs on top of clean service boundaries
   - Addresses: 3 API audience separation, role-based auth wiring
   - Avoids: Building APIs on unstable service interfaces

**Phase ordering rationale:**
- STAFF and CATALOG must come first because every other module references users and products
- Ledger separation must precede Orders slimming because the fulfillment logic needs target modules to move into
- Application-layer orchestrators can only be built once module public APIs are defined
- API layer is last because it depends on stable service interfaces

**Research flags for phases:**
- Phase 2 (Ledger Separation): Needs careful attention to the LOGISTICS/INVENTORY boundary -- which service owns the "complete transfer and write stock transactions" flow
- Phase 3 (Orders slimming): The 1151-line orders/services.py needs surgical extraction -- high risk of regression
- Phase 5 (API Layer): Standard patterns, unlikely to need additional research

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Stack is fixed per project constraints, no decisions needed |
| Architecture | HIGH | Patterns are well-established (Grzybek, Jovanovic), adapted to specific codebase |
| Features | HIGH | Feature scope is defined in PROJECT.md, validated by existing codebase |
| Pitfalls | HIGH | Identified from actual code analysis, not theoretical concerns |

## Gaps to Address

- **CRM module scope**: Whether Client should remain a role on the User table or become a separate entity in a dedicated CRM module needs phase-specific design. Current analysis assumes User stays in STAFF with CRM-specific extensions.
- **Alembic migration strategy**: The fresh database rebuild makes migration simpler, but the multi-schema approach (separate PG schemas per bounded context) vs single schema with naming conventions needs a concrete decision during Phase 1.
- **CQRS queries**: The existing `queries.py` pattern in `users` module suggests partial CQRS. Whether to formalize this across all modules needs Phase 1 design work.
- **Route sheets**: The `route_sheet_id` on StockTransfer suggests a planned feature. Its bounded context placement (LOGISTICS) needs confirmation during Phase 2.
