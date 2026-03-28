# Domain Pitfalls

**Domain:** Water delivery DDD modular monolith refactoring (B2B/B2C)
**Researched:** 2026-03-27

---

## Critical Pitfalls

Mistakes that cause rewrites, data corruption, or multi-week setbacks.

---

### Pitfall 1: Splitting Bounded Contexts While UoW Spans Them All

**What goes wrong:** The current `BaseOrderUnitOfWork` composes repositories from 3 different future bounded contexts (ORDERS, INVENTORY, BILLING) into a single SQLAlchemy session. `ClientUnitOfWork` is worse -- it spans 5 future contexts (CRM, STAFF, BILLING, INVENTORY, ORDERS). If you split modules into bounded contexts but leave these composite UoWs intact, the "boundaries" are an illusion. Any service can reach into any domain's repositories through the shared session. The refactoring produces folder reorganization, not actual domain separation.

**Why it happens:** The existing code needs atomicity across domains (e.g., order delivery creates stock transfers AND financial transactions in one commit). The temptation is to preserve this by keeping composite UoWs. Teams rationalize it as "we're a monolith, so shared transactions are fine." But this defeats the purpose of bounded contexts -- you cannot reason about one domain without understanding all domains it transacts with.

**Consequences:**
- No module can be tested in isolation (every test needs the full session with all repos).
- Changing a schema in INVENTORY breaks ORDERS tests because they share the UoW.
- Future extraction to microservices becomes impossible -- every operation is a distributed transaction.
- The 1,150-line `orders/services.py` cannot shrink because it orchestrates ledger writes directly.

**Warning signs:**
- A UoW class imports from 3+ module directories.
- A service method creates records in tables owned by another bounded context.
- You cannot run a module's tests without seeding data for unrelated modules.

**Prevention:**
1. Each bounded context owns exactly ONE UoW with ONLY its own repositories.
2. Cross-context operations use an Application Service (orchestration layer) that calls each context's service sequentially, with each context committing independently.
3. For operations requiring atomicity across contexts (delivery = stock transfer + financial entry), use the Outbox Pattern: ORDERS commits its state change and publishes a domain event; INVENTORY and BILLING react in their own transactions.
4. Accept eventual consistency between ledgers within the same database -- PostgreSQL triggers already enforce per-ledger consistency.

**Phase relevance:** Must be addressed in the foundational refactoring phase. If composite UoWs survive into API buildout, every new endpoint deepens the coupling.

---

### Pitfall 2: Separating Stock Ledger and Financial Ledger with Shared Transaction Scope

**What goes wrong:** The current system creates `StockTransaction` entries and `Transaction` (financial) entries in the same database commit during order fulfillment. The PG triggers (`update_inventory_balances` and `update_account_balances`) fire within this single transaction. Separating these into INVENTORY and BILLING bounded contexts means they need independent transaction scopes. But if you naively split them while keeping a single commit, you haven't actually separated anything. If you split them into separate commits, a failure in the financial leg leaves the stock ledger advanced but the financial ledger behind.

**Why it happens:** Double-entry bookkeeping demands that every physical movement (stock) has a corresponding financial movement (revenue, debt). Developers assume this means "same transaction." In reality, it means "eventually consistent with reconciliation."

**Consequences:**
- If forced into a single transaction: the two "bounded contexts" are coupled at the database level, negating separation. You cannot change the financial schema without risking stock ledger trigger behavior.
- If split carelessly: partial failures create orphaned stock movements with no financial record, making reconciliation impossible.
- If triggers interact: `update_inventory_balances` and `update_account_balances` both run in the same transaction currently. Splitting them means understanding which trigger fires when, and whether they can deadlock across separate sessions.

**Warning signs:**
- A single service method contains both `uow.transactions.add()` (stock) and `uow.financial_transactions.add()` at the same indent level.
- Tests require seeding both inventory AND financial accounts to verify a single business operation.
- Schema migrations for INVENTORY tables require testing against financial triggers.

**Prevention:**
1. Design the split as: INVENTORY commits stock movements first (triggers update `inventory_balances`). Then an Application Service or domain event triggers BILLING to record the financial counterpart.
2. Use an `outbox` table per context: INVENTORY writes a `stock_movement_completed` event row atomically with its stock transaction. A processor reads the outbox and calls BILLING.
3. Build a reconciliation query from day one: `SELECT stock movements without matching financial entries`. Run it in tests and as a health check.
4. Keep triggers scoped: `update_inventory_balances` should only reference `stock_transactions` and `inventory_balances`. `update_account_balances` should only reference `transactions` and `accounts`. They must never cross-reference tables from the other ledger.

**Phase relevance:** This is the single hardest architectural decision. Must be designed in the refactoring phase, but implementation can be incremental: first separate the models and services, then separate the transaction scopes, then add the outbox.

---

### Pitfall 3: Breaking a Running System During Refactoring (No Test Safety Net)

**What goes wrong:** The codebase has zero test coverage (empty `tests/conftest.py`). Refactoring bounded contexts, extracting services, splitting UoWs, and changing import paths will break things. Without tests, the only way to verify correctness is manual testing of every order flow, every transfer type, every financial settlement path. This is unsustainable. Teams either skip verification (ship bugs) or slow to a crawl (manual QA after every change).

**Why it happens:** The project is a working MVP and "testing can come later." But refactoring IS the moment where tests are most valuable -- they're the diff between "refactoring" and "rewriting and hoping it works."

**Consequences:**
- Silent regressions in financial calculations (rounding, tara exchange, settlement) that only surface when real money doesn't add up.
- Duplicated logic (the 8 copy-pasted transfer creation patterns) means a fix in the new structure may not cover all code paths.
- The team loses confidence in the refactoring and either abandons it or does a risky big-bang rewrite.

**Warning signs:**
- Merging refactoring PRs without a CI pipeline that runs tests.
- Finding bugs through manual testing after every structural change.
- Reverting refactoring commits because "something broke but we don't know what."

**Prevention:**
1. Before ANY refactoring, write characterization tests (also called "golden master" tests) for the critical flows: order delivery fulfillment, warehouse pickup, walk-in sale, tara exchange, shift close. These are end-to-end tests that hit the database.
2. Focus on the dual ledger invariants: "total debits = total credits" for financial ledger, "sum of stock transactions = inventory balance" for stock ledger. These can be asserted after every test.
3. Use the existing seeder as test fixture setup -- it already creates the full data graph.
4. Run tests in CI before merging any refactoring PR.

**Phase relevance:** Must be the FIRST phase -- before any structural changes. Even 10-15 integration tests covering the happy paths of the 4 main flows provide enormous safety.

---

### Pitfall 4: Treating RBAC as API-Layer-Only Concern While Domain Leaks Permissions

**What goes wrong:** The current system has 8 roles, 20+ scopes, and 3 API audiences (courier, client, staff). The scopes are embedded in JWT at login time and checked at the router level. But the service layer has NO permission awareness -- `BaseOrderService.create_order()` doesn't know if it was called by a client or an admin. This creates two problems:
1. Scope bugs go undetected: client endpoints use `ORDERS_EDIT` (admin-only) instead of `ORDERS_CREATE`, which means clients literally cannot create orders through their API. This bug EXISTS today.
2. IDOR vulnerabilities: the service has IDOR protection (`requesting_user_id` parameter) but the API layer doesn't pass it. Any client can view any order.

When building 3 separate API audiences, each audience will call the SAME service methods with different authorization semantics. If those semantics live only in router decorators, every new endpoint is a potential privilege escalation.

**Why it happens:** It feels clean to "keep auth out of business logic." But when business rules differ by role (clients can only see their own orders, couriers can only deliver assigned orders, admins see everything), the service layer MUST enforce ownership constraints. The API layer decides "can this role access this endpoint?" The service layer decides "can this user access this specific resource?"

**Consequences:**
- The existing client API is non-functional (wrong scopes).
- IDOR vulnerabilities across all client-facing endpoints.
- When building courier API, same mistakes will repeat: wrong scopes, missing ownership checks.
- Adding a new role (e.g., MANAGER) requires auditing every endpoint, not just updating `ROLE_SCOPES`.

**Warning signs:**
- Service methods that accept `user_id` but have no tests verifying that user_id is actually checked.
- Endpoints where the scope in the decorator doesn't match the scopes assigned to the intended role.
- A `ROLE_SCOPES` mapping that assigns a scope to a role, but no endpoint uses that scope for that role's API audience.

**Prevention:**
1. Service methods that return user-specific data MUST accept and enforce `requesting_user_id`. This is not optional -- make it a required parameter.
2. Create a scope-to-role verification test: for each API endpoint, assert that the required scopes are present in the intended role's `ROLE_SCOPES`.
3. Separate "resource authorization" (can this user access this order?) from "action authorization" (can this role perform this action?). The former is domain logic in services; the latter is API-layer concern.
4. For 3 API audiences: create separate router files per audience. Each audience's router explicitly passes the current user's identity to the service layer. Never share router code between audiences.

**Phase relevance:** Must be fixed before building the Courier and Client APIs. Fix scope assignments first (quick wins), then add ownership enforcement to service methods.

---

### Pitfall 5: Circular Dependencies When Splitting Orders from Inventory/Logistics

**What goes wrong:** Currently, `orders/services.py` imports from `inventory` (enums, exceptions, schemas) and `inventory/models.py` has a `ForeignKey("orders.id")` on `StockTransfer.order_id`. Meanwhile, `orders/models.py` has `ForeignKey("inventories.id")` for `client_inventory_id` and `warehouse_id`. This is a bidirectional dependency between ORDERS and INVENTORY at both the model level and the service level.

When you try to split these into clean bounded contexts (ORDERS, INVENTORY, LOGISTICS), you hit circular imports. ORDERS needs to know about inventory IDs, and INVENTORY needs to know about order IDs. The naive fix is to put everything in a shared module, which destroys the boundary.

**Why it happens:** In the physical domain, orders and inventory are deeply coupled -- fulfilling an order moves stock. The domain model reflects this coupling through FK relationships. But DDD bounded contexts are about drawing boundaries where the LANGUAGE changes, not where the data flows.

**Consequences:**
- Circular import errors crash the application at startup.
- "Fixing" circularity by creating a shared models module re-centralizes the code.
- Alternatively, removing FKs to break circularity sacrifices referential integrity.
- The 6-context split (INVENTORY, LOGISTICS, ORDERS, BILLING, STAFF, CRM) may be over-specified, creating unnecessary boundaries.

**Warning signs:**
- `ImportError: cannot import name X from partially initialized module` during testing.
- A module's `__init__.py` importing from another module's `__init__.py`.
- FK relationships pointing from one bounded context's table to another's.

**Prevention:**
1. At the database level, cross-context FKs are FINE in a modular monolith. The database is shared. The boundary is at the service/API level, not at the table level. Do not remove FKs.
2. At the code level, break circular imports by depending on IDs (UUIDs), not on model objects. ORDERS stores `inventory_id: UUID` and asks INVENTORY to look it up when needed. INVENTORY stores `order_id: UUID` and never imports the Order model.
3. Use a dependency direction: ORDERS depends on INVENTORY (calls its service), but INVENTORY never calls ORDERS. LOGISTICS depends on INVENTORY but not on ORDERS directly. BILLING depends on nothing -- it receives events.
4. Define which context OWNS each table. `stock_transfers` is owned by LOGISTICS (not INVENTORY and not ORDERS). `orders` is owned by ORDERS. Cross-references use UUID columns without importing the foreign model class.

**Phase relevance:** Must be resolved during the bounded context design phase, before moving any code. Draw the dependency graph first. If it has cycles, the context boundaries are wrong.

---

## Moderate Pitfalls

---

### Pitfall 6: Over-Engineering the DTO Layer Into a Data Transformation Hell

**What goes wrong:** The project mandates "frozen DTOs from services -- never expose ORM objects." This is correct in principle. But teams often implement this as: ORM model -> domain entity -> service DTO -> response schema. Every layer converts. For a system with `Order` + `OrderItem` + `StockTransfer` + `StockTransferItem` + `StockTransaction` + `Transaction`, a single order detail query now requires 6 model-to-DTO conversions, each with their own mapping code. The mapping code becomes the largest part of the codebase.

**Why it happens:** DDD literature recommends separating domain models from persistence models. In typed languages with rich type systems, this pays off. In Python with Pydantic v2 and SQLAlchemy 2.x, the ORM model IS effectively the domain model (business logic lives in services, not models). Adding a separate domain entity layer creates boilerplate without benefit.

**Prevention:**
1. Use a two-layer conversion: ORM model -> frozen Pydantic DTO (returned by services). The DTO IS the response schema for internal consumers.
2. The API layer may need a different response schema (hiding internal fields, adding computed fields). That's a thin transformation, not a separate domain layer.
3. Use `model_validate(orm_obj, from_attributes=True)` (Pydantic v2) instead of manual attribute mapping.
4. Do NOT create separate "domain entity" classes in Python unless they carry behavior that doesn't belong in the service layer.

**Warning signs:**
- More than 2 conversion steps between database and API response.
- Mapping files that are longer than the service files they support.
- Developers spending more time on DTO mapping than on business logic.

**Phase relevance:** Define the DTO pattern convention ONCE in the refactoring phase and apply it uniformly. Do not let each module invent its own conversion approach.

---

### Pitfall 7: Migrating Triggers Without a Verification Strategy

**What goes wrong:** The PG triggers (`update_inventory_balances`, `update_account_balances`) are the system's correctness backbone. During refactoring, if the trigger SQL is modified (e.g., to support new table names in the LOGISTICS context), there's no automated way to verify the triggers still produce correct balances. The triggers are defined in Alembic migration SQL strings, not tested independently.

**Why it happens:** Triggers are invisible to application-level tests. They fire implicitly on INSERT/UPDATE. Developers test the application code but not the trigger behavior. A typo in trigger SQL silently corrupts balances.

**Consequences:**
- Inventory balances drift from reality. Discovered days later during reconciliation (if reconciliation exists -- it currently doesn't).
- Financial balances are wrong. If the append-only constraint is accidentally removed during migration, UPDATE/DELETE on transactions becomes possible, destroying the audit trail.

**Prevention:**
1. Write trigger-specific integration tests: insert a stock transaction, then query `inventory_balances` to verify the trigger updated correctly. Do the same for financial transactions.
2. Test the append-only constraint: attempt to UPDATE a `stock_transaction` and assert it fails. Attempt to DELETE a `transaction` and assert it fails.
3. Store trigger SQL in `.sql` files (already done in `src/infrastructure/database/scripts/`), version them, and include a hash check in migrations.
4. When rebuilding migrations from scratch (which the project plans to do), run the trigger tests against both old and new migration outputs and compare.

**Warning signs:**
- `inventory_balances.quantity` does not match `SUM(stock_transactions.quantity)` for a given inventory+product pair.
- `accounts.balance` does not match `SUM(transactions.amount)` for a given account.
- A migration that touches trigger definitions has no corresponding test changes.

**Phase relevance:** Write trigger verification tests in the testing phase. Run them as part of CI. They are the cheapest, highest-value tests in this system.

---

### Pitfall 8: Building Three API Audiences with Shared Response Schemas

**What goes wrong:** The staff (backoffice), courier, and client APIs return different information about the same entities. A staff member sees all order fields including financial details. A client sees their own order without courier assignment details. A courier sees delivery instructions without pricing. If all three audiences share a single `OrderResponse` schema, you either: (a) expose sensitive fields to the wrong audience, or (b) litter the schema with `Optional` fields that are only populated for certain roles.

**Why it happens:** DRY instinct. "Order is Order." But the order as seen by a client IS a different concept than the order as seen by a courier. These are different read models for different bounded contexts of the API.

**Consequences:**
- Information leakage: client sees courier's phone number, courier sees client's financial balance.
- Schema bloat: `OrderResponse` has 30 optional fields where each audience uses 15.
- Frontend confusion: client app receives fields it doesn't need and ignores, increasing payload size.
- API versioning nightmares: changing a field for staff breaks the client app.

**Prevention:**
1. Create audience-specific response schemas: `StaffOrderResponse`, `CourierOrderResponse`, `ClientOrderResponse`. They can share base fields via inheritance, but each adds/removes fields appropriate to its audience.
2. Create audience-specific query methods in the service layer: `get_order_for_client()` vs `get_order_for_courier()`. These load different relationships (client doesn't need courier identity, courier doesn't need financial summary).
3. This maps directly to CQRS: write operations go through the domain service, read operations go through audience-specific query services.

**Warning signs:**
- A single `OrderResponse` used across `/api/v1/backoffice/`, `/api/v1/courier/`, and `/api/v1/client/`.
- `Optional[...]` fields that are only `None` for certain audiences.
- Frontend code ignoring half the fields in an API response.

**Phase relevance:** Define audience-specific schemas when building each API audience. Do NOT retrofit later -- it requires changing every endpoint.

---

### Pitfall 9: The "God Service" Survives Refactoring

**What goes wrong:** `orders/services.py` is 1,150 lines and handles order creation, status management, fulfillment, warehouse pickup, walk-in sales, financial settlement, tara exchange, and courier assignment. Refactoring bounded contexts without decomposing this file just moves the God Service into a different folder. The module is "ORDERS" but the service does LOGISTICS + BILLING + INVENTORY work.

**Why it happens:** The order is the central business entity. Everything happens "because of an order." It's natural to put all order-related logic in the order service. But "related to" is not the same as "owned by." Financial settlement is BILLING logic triggered by an order event, not order logic.

**Consequences:**
- The orders module depends on every other module (catalog, inventory, finances, users).
- Any change to inventory logic requires modifying orders/services.py.
- Testing order creation requires setting up the full financial and inventory infrastructure.
- New developers cannot understand the order flow without understanding the entire system.

**Prevention:**
1. Decompose by asking "which context OWNS this behavior?"
   - Order lifecycle (create, assign, cancel): ORDERS
   - Stock movement on fulfillment: LOGISTICS (triggered by order status change)
   - Financial settlement: BILLING (triggered by delivery confirmation)
   - Tara exchange validation: INVENTORY (called by ORDERS before creation)
2. The order service should emit events: `OrderDelivered`, `OrderCancelled`. Other contexts subscribe.
3. Even without an event bus, use Application Services: `FulfillOrderUseCase` calls `OrderService.mark_delivered()`, then `LogisticsService.create_delivery_transfer()`, then `BillingService.settle_payment()`.
4. Target: `orders/services.py` should be under 300 lines, handling only order CRUD and status transitions.

**Warning signs:**
- `orders/services.py` imports from 3+ other modules.
- A single method in orders/services.py is over 100 lines (currently `_handle_order_fulfillment` at ~80 lines, `create_order` at ~180 lines).
- The orders module's UoW has more non-orders repositories than orders repositories.

**Phase relevance:** This is the core of the refactoring. Plan the decomposition in the design phase, execute in the refactoring phase. Do NOT attempt to do this and the testing phase simultaneously.

---

### Pitfall 10: Hardcoded System Entities Create Deployment Fragility

**What goes wrong:** The system relies on hardcoded UUIDs for special entities: `WALKIN_USER_ID`, system financial accounts (Revenue, Cash, Card, Discount), and virtual inventories (VIRTUAL_VENDOR, VIRTUAL_LOSS). The seeder creates these with specific IDs. If the seeder runs in a different order, or a migration resets the data, or a developer runs on a fresh database without seeding, the system fails silently -- walk-in sales accumulate phantom inventory, financial transactions have no destination account.

**Why it happens:** System entities were created organically during MVP development. Hardcoded UUIDs were the fastest way to reference them. But they create an invisible contract between the application code and the database state.

**Prevention:**
1. Replace UUID comparisons with a `SystemEntity` enum or flag column: `User.is_system_user`, `Account.account_type = SystemAccountType.REVENUE`.
2. Validate system entity existence at application startup (in the lifespan function). Fail FAST with a clear error if Revenue account or VIRTUAL_VENDOR inventory is missing.
3. Use database-level defaults or migration-level inserts (not application-level seeder) for system entities that the application depends on.
4. Add a health check endpoint that verifies all system entities exist.

**Warning signs:**
- `constants.py` contains UUIDs that are referenced in business logic.
- The application silently succeeds but produces wrong data when system entities are missing.
- `shift_close` crashes with `scalar_one()` because it assumes exactly one system warehouse.

**Phase relevance:** Fix during the refactoring phase as part of the "clean foundations" work. Quick win with high safety improvement.

---

## Minor Pitfalls

---

### Pitfall 11: Eager Loading Strategy Doesn't Match Bounded Context Boundaries

**What goes wrong:** The current `search_orders` query eagerly loads 5 levels of relationships (client + identities, courier + identities, client_inventory, items + products, stock_transfers + items). After refactoring, some of these relationships will cross bounded context boundaries. Loading a `User` (STAFF context) from within an order query (ORDERS context) violates the boundary.

**Prevention:**
1. Within a bounded context, eager loading is fine (Order -> OrderItem -> snapshot price).
2. Across contexts, use ID references and separate queries: load the order, then call `StaffService.get_user_summary(courier_id)` for display name.
3. Create lightweight "summary" DTOs for cross-context references: `CourierSummary(id, name)` instead of the full `User` model with identities.

**Phase relevance:** Address when implementing audience-specific query methods.

---

### Pitfall 12: State Machine Missing on Order Status Transitions

**What goes wrong:** `update_status` allows arbitrary transitions (DELIVERED back to NEW, CANCELLED to IN_TRANSIT). The `InvalidOrderStatusError` exception exists but is never used. During refactoring, if new status values are added for the courier flow (e.g., `PICKED_UP`, `EN_ROUTE`), the lack of a state machine means any combination is possible.

**Prevention:**
1. Define `VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]]` as a class attribute or module constant.
2. Validate in `update_status` before any side effects.
3. Each transition should have a named handler: `_on_delivered()`, `_on_cancelled()`. This makes it explicit which side effects (transfers, financials) are triggered by which transition.
4. Test every valid and invalid transition.

**Phase relevance:** Add the state machine during the refactoring phase, before building the courier API (which will add new transitions).

---

### Pitfall 13: Python 2 Syntax Bug in Auth Creates Silent Security Hole

**What goes wrong:** `src/modules/auth/dependencies.py` line 69 uses `except ValueError, TypeError:` which is Python 2 syntax. In Python 3, this catches `ValueError` and assigns it to the name `TypeError`, shadowing the builtin. Actual `TypeError` exceptions propagate as 500 errors.

**Prevention:** Fix to `except (ValueError, TypeError):` immediately. This is a one-line fix with security implications.

**Phase relevance:** Fix immediately, before any refactoring begins. It's a bug, not a design decision.

---

### Pitfall 14: CONTRACT Payment Method Is a Time Bomb

**What goes wrong:** `PaymentMethod.CONTRACT` exists in the enum but has no handling in `_process_financial_settlement()` or `_process_pickup_settlement()`. B2B customers using contract-based billing will have permanently unsettled debts in the financial ledger. The system records revenue but never settles, making the financial ledger permanently out of balance for contract orders.

**Prevention:**
1. Either implement CONTRACT handling (deferred payment creates a receivable, settled on monthly invoice).
2. Or remove CONTRACT from the enum and block order creation with that payment method until it's implemented.
3. Add a check constraint or service-level validation: if payment method is not in `[CASH, CARD, TRANSFER]` (the handled set), reject the order.

**Phase relevance:** Address during BILLING bounded context design. At minimum, add the validation guard in the refactoring phase.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Testing foundation | Writing tests for current structure that break during refactoring | Write tests against public service interfaces and database outcomes, not internal implementation. Test invariants ("ledger balances") not steps ("method X was called"). |
| Bounded context design | Over-splitting into 6 contexts when 4 would suffice | Validate each boundary by asking: "Does the language change?" STAFF and CRM might be one context. INVENTORY and LOGISTICS might be one context with two sub-modules. Start with fewer contexts and split when pain emerges. |
| UoW decomposition | Breaking atomicity guarantees that the business requires | Identify which operations TRULY need atomicity (delivery must create transfer + update order status) vs. which are eventually consistent (financial settlement can follow stock movement). Use the outbox pattern for the latter. |
| Dual ledger separation | Trigger interaction during migration | Test triggers in isolation. Write the reconciliation query before the separation, not after. Run it continuously during development. |
| API audience buildout | Scope/permission mismatches (already exists for client and courier APIs) | Create a "scope coverage matrix" test: for each audience, for each endpoint, assert the required scope exists in that audience's role. Run in CI. |
| Order service decomposition | Regression in the 8 duplicated transfer creation patterns | Extract `TransferBuilder` BEFORE decomposing the order service. Each current call site should use the builder. Then decomposition moves the builder calls to different contexts. |
| Fresh migration rebuild | Losing trigger definitions or subtle constraint differences | Diff the generated SQL against the current `pg_dump` output. Every constraint, trigger, and index must be present. |
| DTO standardization | Inconsistent conversion patterns across modules | Define ONE utility function (e.g., `to_dto(model, schema_class)`) and enforce it via code review or linting. |

---

## Sources

- [Refactoring Overgrown Bounded Contexts in Modular Monoliths -- Milan Jovanovic](https://www.milanjovanovic.tech/blog/refactoring-overgrown-bounded-contexts-in-modular-monoliths) -- bounded context growth patterns, extraction strategies
- [Evolving Modular Monoliths: Passing Data Between Bounded Contexts -- The Reformed Programmer](https://www.thereformedprogrammer.net/evolving-modular-monoliths-3-passing-data-between-bounded-contexts/) -- cross-context data patterns, shared database considerations
- [Refactoring Legacy Systems with Domain-Driven Design -- Deep Engineering](https://deepengineering.substack.com/p/refactoring-legacy-systems-with-domain) -- test safety nets before refactoring, organizational alignment
- [Sharing Databases Within Bounded Contexts -- Nick Tune](https://medium.com/nick-tune-tech-strategy-blog/sharing-databases-within-bounded-contexts-5f7ca6216097) -- when shared databases are acceptable, boundary enforcement
- [The Unit of Work and Transactions in DDD -- Sapiensworks](https://blog.sapiensworks.com/post/2015/09/02/DDD-and-UoW) -- one transaction per aggregate, eventual consistency across contexts
- [Modular Monolith with DDD -- Kamil Grzybek (GitHub)](https://github.com/kgrzybek/modular-monolith-with-ddd) -- reference architecture for modular monolith with bounded contexts
- [pgledger: Ledger Implementation in PostgreSQL -- Paul Gross](https://www.pgrs.net/2025/03/24/pgledger-ledger-implementation-in-postgresql/) -- append-only ledger patterns, trigger-based balance enforcement
- [Double-Entry Bookkeeping for Programmers -- balanced.software](https://www.balanced.software/double-entry-bookkeeping-for-programmers/) -- ledger separation, rounding pitfalls
- [My Experience of Using Modular Monolith and DDD -- The Reformed Programmer](https://www.thereformedprogrammer.net/my-experience-of-using-modular-monolith-and-ddd-architectures/) -- practical lessons from monolith-to-DDD migration
- [Data Points: Sharing Data Across DDD Bounded Contexts -- Microsoft](https://learn.microsoft.com/en-us/archive/msdn-magazine/2014/october/data-points-a-pattern-for-sharing-data-across-domain-driven-design-bounded-contexts) -- patterns for cross-context data sharing
- [Role-Based Access Control for APIs -- Endgrate](https://endgrate.com/blog/role-based-access-control-for-apis-implementation-guide) -- RBAC pitfalls, scope management

---

*Pitfalls analysis: 2026-03-27*
