# Architecture Patterns

**Domain:** Water delivery DDD modular monolith (B2B/B2C)
**Researched:** 2026-03-28
**Confidence:** HIGH (evidence from codebase analysis + established DDD patterns)

## Current State Analysis

The existing codebase is a **partially-DDD modular monolith** with 6 domain modules (`auth`, `users`, `catalog`, `orders`, `inventory`, `finances`) and 4 application-layer orchestrators (`client`, `courier`, `order`, `inventories`). The architecture has strong foundations (UoW pattern, repository abstraction, PG trigger-enforced ledgers) but suffers from three structural problems that this research addresses:

1. **Bounded context leakage** -- The Orders module directly imports and manipulates Inventory and Finance repositories, creating a 900+ line service that owns three domains at once.
2. **UoW sprawl** -- `BaseOrderUnitOfWork` composes 8 repositories from 3 different modules. `ClientUnitOfWork` composes 11 repositories from 5 modules. These are "god transactions" that violate bounded context ownership.
3. **Missing module boundary enforcement** -- Modules import each other's repositories, models, and enums freely. There is no public API contract between modules.

## Recommended Architecture

### Target: 6 Bounded Contexts with Public Service APIs

```
src/
  core/                          # Cross-cutting (config, security, exceptions, logging)
  common/                        # Shared abstractions (BaseRepository, BaseService, IUnitOfWork)
  infrastructure/                # Database engine, session, base model, triggers
  modules/
    staff/                       # BC: STAFF (was: users + auth)
      models.py                  # User, Identity
      services.py                # UserService, AuthService
      public.py                  # StaffReader (public read API for other modules)
      ...
    catalog/                     # BC: CATALOG (unchanged, already clean)
      models.py                  # Product
      services.py                # CatalogService
      public.py                  # CatalogReader
      ...
    crm/                         # BC: CRM (was: part of users + application/client)
      models.py                  # Client, Address, Contract, DeliverySchedule
      services.py                # ClientService, OnboardingService
      public.py                  # CRMReader
      ...
    inventory/                   # BC: INVENTORY (Stock Ledger only)
      models.py                  # Inventory, Balance, StockTransaction
      services.py                # InventoryService, StockLedgerService
      public.py                  # InventoryReader
      ...
    logistics/                   # BC: LOGISTICS (was: part of inventory)
      models.py                  # StockTransfer, StockTransferItem
      services.py                # TransferService, ShiftService
      public.py                  # LogisticsReader
      ...
    billing/                     # BC: BILLING (was: finances)
      models.py                  # Account, Transaction
      services.py                # BillingService, FinancialLedgerService
      public.py                  # BillingReader
      ...
    orders/                      # BC: ORDERS (slimmed down)
      models.py                  # Order, OrderItem
      services.py                # OrderService (lifecycle + cart only)
      public.py                  # OrderReader
      ...
  application/                   # Cross-domain orchestration (use cases)
    fulfillment/                 # Order delivery + warehouse pickup
      service.py                 # FulfillmentService
      uow.py                    # FulfillmentUnitOfWork
    onboarding/                  # Client registration + initial setup
      service.py                 # OnboardingService
      uow.py                    # OnboardingUnitOfWork
  api/
    v1/
      staff/                     # Staff/Operator API endpoints
      courier/                   # Courier API endpoints
      client/                    # Client API endpoints
      auth/                      # Auth endpoints
```

### Component Boundaries

| Component | Responsibility | Owns Tables | Communicates With |
|-----------|---------------|-------------|-------------------|
| **STAFF** | Employee lifecycle, roles, authentication, courier identity | `users`, `identities` | None (root entity, referenced by all) |
| **CATALOG** | Product definitions, pricing, returnable item mappings | `products` | None (reference data) |
| **CRM** | Client profiles, addresses, contracts, delivery schedules | Future: `clients`, `addresses`, `contracts`. Currently: uses `users` + `inventories` (CLIENT type) for client-specific data | STAFF (user creation), INVENTORY (client inventory setup) |
| **INVENTORY** | Stock Ledger: inventory locations, balances, stock transactions | `inventories`, `inventory_balances`, `stock_transactions` | STAFF (user_id on inventory) |
| **LOGISTICS** | Transfer documents, state machine, route sheets, courier loading | `stock_transfers`, `stock_transfer_items` | INVENTORY (reads balances, writes transactions), STAFF (created_by, accepted_by) |
| **BILLING** | Financial Ledger: accounts, financial transactions, debt tracking | `accounts`, `transactions` | STAFF (account ownership) |
| **ORDERS** | Order lifecycle, cart management, status machine | `orders`, `order_items` | CATALOG (price lookup), CRM (client validation) |
| **Fulfillment** (app layer) | Orchestrates delivery/pickup: stock movement + financial settlement | No own tables | ORDERS, LOGISTICS, INVENTORY, BILLING |
| **Onboarding** (app layer) | Client registration: user + account + inventory + optional first order | No own tables | STAFF, CRM, BILLING, INVENTORY, ORDERS |

### Data Flow

#### Order Delivery Fulfillment (the most complex flow)

```
API Layer                    Application Layer              Module Layer
---------                    -----------------              ------------
PATCH /orders/{id}/status
  |
  v
OrderService                                               [ORDERS]
  .update_status()
  |  (status -> DELIVERED)
  |
  v
FulfillmentService                                         [APPLICATION]
  .handle_delivery(order)
  |
  +---> InventoryReader.get_courier_balances()              [INVENTORY]
  |       (validates stock availability)
  |
  +---> LogisticsService.create_delivery_transfer()         [LOGISTICS]
  |       (CLIENT_DELIVERY: Courier -> Client)
  |       internally calls InventoryService
  |       to write StockTransactions
  |
  +---> LogisticsService.create_return_transfer()           [LOGISTICS]
  |       (CLIENT_RETURN: Client -> Courier, tara)
  |       internally calls InventoryService
  |       to write StockTransactions
  |
  +---> BillingService.settle_order()                       [BILLING]
          (Revenue -> Client debt)
          (Client -> Courier/Card payment)
```

**Key insight:** The current `BaseOrderService._handle_order_fulfillment()` method (lines 630-795 in `orders/services.py`) directly manipulates 6 repositories across 3 domains. In the target architecture, this becomes `FulfillmentService` in the application layer, calling module-level services through their public APIs.

#### Stock Ledger Write Path (immutable, trigger-enforced)

```
LogisticsService.complete_transfer()
  |
  +---> StockTransferRepository.update_status(COMPLETED)    [LOGISTICS]
  |
  +---> InventoryService.record_movement()                  [INVENTORY]
          |
          +---> StockTransactionRepository.add()
                  |
                  v
              PG TRIGGER: update_inventory_balances()
                  |
                  +---> UPSERT inventory_balances
                        (from_id: -quantity, to_id: +quantity)
```

#### Financial Ledger Write Path (immutable, trigger-enforced)

```
BillingService.record_transaction()
  |
  +---> TransactionRepository.add()                         [BILLING]
          |
          v
      PG TRIGGER: update_account_balances()
          |
          +---> UPDATE accounts SET balance
                (from_id: -amount, to_id: +amount)
                (only when status = 'completed')
```

### Inter-Module Communication Pattern

**Use direct service calls (synchronous), not domain events.** Rationale:

1. The codebase is a monolith sharing one PostgreSQL database -- in-process calls are simpler and sufficient.
2. All critical flows (delivery fulfillment, warehouse pickup) require atomicity across stock + financial ledgers within a single DB transaction. Domain events with eventual consistency would break the dual-ledger invariant that "every stock movement has a corresponding financial settlement."
3. The team size and domain complexity do not warrant the operational overhead of an event bus.
4. If microservice extraction is ever needed (unlikely given the constraints), the `public.py` interfaces serve as natural service boundary seams.

**Module public API pattern** -- Each module exposes a `public.py` file:

```python
# src/modules/inventory/public.py
"""
Public read API for the Inventory bounded context.
Other modules import ONLY from this file.
"""
from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True)
class InventoryBalanceDTO:
    inventory_id: UUID
    product_id: UUID
    quantity: int

class InventoryReader:
    """Read-only queries other modules may call."""
    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    async def get_balances(self, inventory_id: UUID) -> list[InventoryBalanceDTO]:
        async with self.uow:
            balances = await self.uow.inventories.get_inventory_with_balances(inventory_id)
            return [InventoryBalanceDTO(...) for b in balances.balances]
```

**Rules for inter-module communication:**

1. Modules NEVER import another module's `models.py`, `repositories.py`, or `uow.py`.
2. Modules MAY import another module's `public.py` (frozen DTOs + reader services).
3. Cross-module writes go through the application layer orchestrator, never module-to-module.
4. Foreign keys at the DB level are allowed (they enforce referential integrity), but SQLAlchemy relationships across modules use `lazy="raise"` and TYPE_CHECKING imports only.

### Dual Ledger Separation Strategy

The current codebase mixes stock ledger and financial ledger operations in `InventoryUnitOfWork` (which includes `AccountRepository` and `FinancialTransactionRepository`). This must be separated.

**Stock Ledger (INVENTORY module):**
- Tables: `inventories`, `inventory_balances`, `stock_transactions`
- Trigger: `update_inventory_balances()` -- append-only, INSERT fires balance UPSERT
- Invariant: `SUM(stock_transactions for inventory+product) == inventory_balances.quantity`
- Write API: `InventoryService.record_movement(from_id, to_id, product_id, quantity, transfer_id)`

**Financial Ledger (BILLING module):**
- Tables: `accounts`, `transactions`
- Trigger: `update_account_balances()` -- append-only, INSERT/status change fires balance UPDATE
- Invariant: `SUM(completed transactions for account) == accounts.balance`
- Write API: `BillingService.record_transaction(from_id, to_id, amount, order_id, status, reason)`

**Why separate:** Stock and financial ledgers have different:
- Domain language (quantity vs amount, inventory vs account, product-scoped vs money-scoped)
- Business rules (stock transactions are immediately final; financial transactions have PENDING/COMPLETED/REJECTED lifecycle)
- Audit requirements (stock is physical count; financial is monetary compliance)
- Access patterns (warehouse staff query stock; accountants query finances)

**Coordination point:** The application-layer `FulfillmentService` is the only place that writes to both ledgers in a single transaction. This is acceptable because they share one database. The key constraint: both writes must happen in the same DB transaction (same SQLAlchemy session) to maintain the invariant "delivered goods always have a corresponding financial entry."

### UoW Refactoring Strategy

**Current problem:** `BaseOrderUnitOfWork` composes repositories from `orders`, `inventory`, and `finances` modules. This makes Orders own everything.

**Target pattern:**

| UoW | Belongs To | Repositories |
|-----|-----------|--------------|
| `StaffUnitOfWork` | STAFF module | `users`, `identities` |
| `CatalogUnitOfWork` | CATALOG module | `products` |
| `InventoryUnitOfWork` | INVENTORY module | `inventories`, `balances`, `stock_transactions` |
| `LogisticsUnitOfWork` | LOGISTICS module | `transfers`, `transfer_items` + (writes via InventoryService) |
| `BillingUnitOfWork` | BILLING module | `accounts`, `transactions` |
| `OrderUnitOfWork` | ORDERS module | `orders`, `order_items` |
| `FulfillmentUnitOfWork` | APPLICATION layer | Composes repos from LOGISTICS, INVENTORY, BILLING, ORDERS |
| `OnboardingUnitOfWork` | APPLICATION layer | Composes repos from STAFF, BILLING, INVENTORY, ORDERS |

**Key rule:** Module-level UoWs own only their own tables. Application-level UoWs are the ONLY places that compose cross-module repositories. This is the "god transaction" pattern -- explicitly scoped to cross-domain use cases, not hidden inside a domain module.

### Role-Based API Layering

The API layer maps to 3 audiences, each with distinct scope requirements:

```
src/api/v1/
  auth/           # POST /login, POST /refresh (public)
  staff/          # Operator/admin endpoints (RBAC-gated)
    orders.py     # Full order CRUD, assignment, fulfillment
    clients.py    # Client management, onboarding
    couriers.py   # Courier management, shift operations
    warehouses.py # Warehouse management, transfers
    catalog.py    # Product CRUD
    finances.py   # Financial reports, transaction verification
    system.py     # Seeder, settings
  courier/        # Courier-specific endpoints
    tasks.py      # Today's route sheet, delivery confirmation
    shifts.py     # Shift start/end, load/unload
    payments.py   # Cash collection confirmation
  client/         # Client-facing endpoints
    orders.py     # Place order, view history
    profile.py    # View/edit profile
    balance.py    # Tara balance, financial balance
```

**Scope enforcement pattern** (already exists, needs consistent application):

```python
# Staff endpoint: requires ORDERS_EDIT scope
@router.patch("/{orderId}/status")
async def update_order_status(
    current_user: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])],
    ...
)

# Courier endpoint: requires ORDERS_DELIVER scope
@router.post("/{orderId}/deliver")
async def confirm_delivery(
    current_user: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_DELIVER])],
    ...
)

# Client endpoint: requires ORDERS_CREATE scope + IDOR check in service
@router.post("/")
async def create_order(
    current_user: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_CREATE])],
    ...
)
```

**IDOR protection:** Courier and Client endpoints must always filter by `current_user.id`. The service layer (not the API layer) enforces this, as it already does in `get_order_with_details()`.

## Patterns to Follow

### Pattern 1: Module Public API (Facade)

**What:** Each bounded context exposes a `public.py` with frozen DTOs and reader services. Other modules import only from `public.py`.

**When:** Any time one module needs data from another.

**Example:**

```python
# src/modules/catalog/public.py
from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True)
class ProductPriceDTO:
    id: UUID
    price: int
    returnable_item_id: UUID | None

class CatalogReader:
    async def get_prices(self, product_ids: list[UUID]) -> list[ProductPriceDTO]:
        ...
```

### Pattern 2: Application-Layer Orchestrator

**What:** Cross-domain business processes live in `src/application/`, not in any single module. They compose module services and share a single DB transaction.

**When:** A use case touches 2+ bounded contexts' write paths.

**Example:**

```python
# src/application/fulfillment/service.py
class FulfillmentService:
    def __init__(
        self,
        uow: FulfillmentUnitOfWork,
        logistics_service: TransferService,
        billing_service: BillingService,
        inventory_reader: InventoryReader,
    ):
        ...

    async def handle_delivery(self, order: Order, actual_items: list | None) -> None:
        async with self.uow:
            # 1. Validate stock (reads inventory)
            # 2. Create stock transfers (writes logistics + inventory)
            # 3. Financial settlement (writes billing)
            await self.uow.commit()  # Single atomic transaction
```

### Pattern 3: Frozen DTO Boundary

**What:** Services return frozen dataclasses or Pydantic models, never ORM objects. This prevents session leaks and accidental lazy loading.

**When:** Always -- at every service boundary.

**Example:**

```python
@dataclass(frozen=True)
class OrderDTO:
    id: UUID
    client_id: UUID
    status: OrderStatus
    total_amount: int
    items: tuple[OrderItemDTO, ...]
```

**Current gap:** The CONVENTIONS.md notes "Service methods return domain model objects, not schemas." This must change. The target is frozen DTOs from all service methods.

### Pattern 4: Module-Scoped UoW

**What:** Each module's UoW contains only its own repositories.

**When:** Always for module-level services.

```python
# src/modules/billing/uow.py
class BillingUnitOfWork(BaseSQLAlchemyUoW):
    accounts: AccountRepository
    transactions: TransactionRepository

    async def __aenter__(self) -> "BillingUnitOfWork":
        await super().__aenter__()
        self.accounts = AccountRepository(session=self.session)
        self.transactions = TransactionRepository(session=self.session)
        return self
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: God UoW

**What:** A single UoW that composes repositories from 3+ modules (current `BaseOrderUnitOfWork` with 8 repos from orders + inventory + finances).

**Why bad:** Destroys bounded context boundaries. Any service with this UoW can write to any table. Makes it impossible to reason about which module owns which data.

**Instead:** Module UoWs for within-module operations. Application-layer UoWs for explicitly cross-domain orchestration.

### Anti-Pattern 2: Cross-Module Repository Import

**What:** `src/modules/orders/uow.py` importing `from src.modules.finances.repositories import AccountRepository`.

**Why bad:** Creates a direct dependency from ORDERS to FINANCES internals. If FINANCES changes its repository interface, ORDERS breaks.

**Instead:** ORDERS calls `BillingReader` (from `billing/public.py`) for reads, and delegates writes to `FulfillmentService` in the application layer.

### Anti-Pattern 3: Business Logic in ORM Relationships

**What:** Using SQLAlchemy `relationship()` across module boundaries to navigate from Order to StockTransfer to Transaction.

**Why bad:** These relationships create hidden queries, N+1 risks, and couple modules at the ORM level.

**Instead:** Keep cross-module relationships as `TYPE_CHECKING`-only imports with `lazy="raise"`. Use explicit queries in the service layer.

### Anti-Pattern 4: Duplicated Ledger Write Logic

**What:** Both `_handle_order_fulfillment()` and `_handle_warehouse_pickup()` contain nearly identical code for creating transfers + transactions + financial entries (currently ~200 lines each of duplicated patterns).

**Why bad:** Business rules for "how to create a stock transfer" are scattered across methods in the Orders service instead of encapsulated in the Logistics module.

**Instead:** `LogisticsService.create_and_complete_transfer(type, from_id, to_id, items, ...)` encapsulates the full transfer creation pattern. `BillingService.settle_order(order_id, amount, payment_method, ...)` encapsulates financial settlement.

## Scalability Considerations

| Concern | Current (MVP) | At 10K orders/day | At 100K orders/day |
|---------|--------------|-------------------|---------------------|
| DB connections | Single async pool | Connection pooling tuning (pgbouncer) | Read replicas for reports |
| Ledger writes | PG triggers, single DB | Same -- triggers scale well | Consider partitioning `stock_transactions` by month |
| Cross-module queries | Direct joins OK | Add materialized views for reports | CQRS: separate read models |
| API response time | Eager loading | Add Redis cache for catalog/balances | Event-driven read model updates |
| Module coupling | Shared DB, direct calls | Same -- modular monolith is fine | Extract BILLING to microservice if compliance requires |

For the current scale (water delivery company, likely <1000 orders/day), the modular monolith with shared database is the correct choice. Do not over-engineer.

## Suggested Build Order (Dependencies Between Components)

The restructuring should follow this dependency order:

```
Phase 1: Foundation (no dependencies)
  |- STAFF module (users + auth, referenced by everything)
  |- CATALOG module (already clean, minimal changes)
  |- Common abstractions (frozen DTO base, public API pattern)

Phase 2: Ledger Separation (depends on Phase 1)
  |- INVENTORY module (Stock Ledger, split from current inventory)
  |- BILLING module (Financial Ledger, rename from finances)
  |- LOGISTICS module (transfers, split from current inventory)

Phase 3: Domain Modules (depends on Phase 1 + 2)
  |- CRM module (client management, split from users + application/client)
  |- ORDERS module (slim down, remove ledger writes)

Phase 4: Application Layer (depends on all modules)
  |- FulfillmentService (delivery + pickup orchestration)
  |- OnboardingService (client registration orchestration)

Phase 5: API Layer (depends on all above)
  |- Staff API (backoffice)
  |- Courier API
  |- Client API
```

**Rationale:**
- STAFF and CATALOG have no module-level dependencies -- they can be restructured first as stable foundations.
- INVENTORY/BILLING/LOGISTICS must be separated before ORDERS can be slimmed down, because the fulfillment logic currently in ORDERS needs to move to the application layer, which depends on the new module boundaries.
- CRM depends on STAFF (user creation) and INVENTORY (client inventory setup).
- Application-layer orchestrators can only be built once all modules have their public APIs defined.
- API layer is last because it depends on all services being available.

## Sources

- Codebase analysis: `src/modules/orders/services.py` (1151 lines), `src/modules/inventory/services.py`, `src/modules/finances/models.py`, all UoW files
- [Modular Monolith with DDD (Kamil Grzybek)](https://github.com/kgrzybek/modular-monolith-with-ddd) -- canonical reference implementation
- [Modular Monolith Integration Styles (Kamil Grzybek)](https://www.kamilgrzybek.com/blog/posts/modular-monolith-integration-styles) -- inter-module communication patterns
- [Modular Monolith Communication Patterns (Milan Jovanovic)](https://www.milanjovanovic.tech/blog/modular-monolith-communication-patterns) -- synchronous vs async tradeoffs
- [Data Isolation in Modular Monoliths (Mehmet Ozkaya)](https://mehmetozkaya.medium.com/data-management-in-modular-monoliths-4-data-isolation-strategies-1042667a099c) -- shared DB with schema separation
- [Modular Monolith Data Isolation (Milan Jovanovic)](https://www.milanjovanovic.tech/blog/modular-monolith-data-isolation) -- 4 isolation strategies
- [Domain-driven design with Python and FastAPI (ActiDoo)](https://www.actidoo.com/en/blog/python-fastapi-domain-driven-design) -- Python/FastAPI DDD layering
- [Double-Entry Bookkeeping for Programmers](https://www.balanced.software/double-entry-bookkeeping-for-programmers/) -- dual ledger implementation patterns
- [How to Build a Double-Entry Ledger (Fatih Altuntas)](https://medium.com/@altuntasfatih42/how-to-build-a-double-entry-ledger-f69edcea825d) -- ledger architecture
- [Building a Real-Time Ledger System (Finlego)](https://finlego.com/blog/designing-a-real-time-ledger-system-with-double-entry-logic) -- trigger-based balance materialization

---

*Architecture analysis: 2026-03-28*
