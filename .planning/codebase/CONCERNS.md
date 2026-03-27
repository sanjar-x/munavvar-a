# Codebase Concerns

**Analysis Date:** 2026-03-27

## Tech Debt

**Massive Code Duplication in Order Services:**
- Issue: `create_order()` and `create_warehouse_sale()` in `src/modules/orders/services.py` share ~80% identical logic (price lookup, tara validation, shortage calculation, capitalization). The same shortage/capitalization block is copy-pasted across both methods (lines 98-184 and 268-345). The `_handle_order_fulfillment()` and `_handle_warehouse_pickup()` methods also duplicate transfer + transaction creation patterns.
- Files: `src/modules/orders/services.py` (1150 lines)
- Impact: Bugs fixed in one path may not be fixed in the other. Adding new transfer types requires duplicating logic again. The file is the largest in the codebase and growing.
- Fix approach: Extract shared tara validation + capitalization into a private `_validate_and_capitalize_tara()` method. Extract transfer+transaction creation into a `_create_transfer_with_ledger_entries()` helper. Target: reduce services.py to ~700 lines.

**ValueError Used Instead of Domain Exceptions:**
- Issue: At least 14 `raise ValueError(...)` calls are scattered across service layer code instead of using the custom `AppException` hierarchy. These bypass the structured error handler and can surface as unformatted 500 errors to the frontend.
- Files: `src/modules/orders/services.py` (lines 258, 436, 454, 504, 642, 687, 696, 810, 818, 966, 1026), `src/modules/inventory/shift_service.py` (lines 38, 50, 71), `src/modules/inventory/services.py` (line 168), `src/api/v1/backoffice/orders.py` (line 172)
- Impact: Frontend receives raw `{"detail": "Internal Server Error"}` instead of structured `{"error": {"code": ..., "message": ...}}`. Inconsistent error handling between endpoints.
- Fix approach: Replace each `ValueError` with the appropriate domain exception (`NotFoundError`, `BadRequestError`, `ConflictError`). The `unhandled_exception_handler` in `src/api/exceptions/handlers.py` catches these as 500s.

**Duplicate Transfer/Transaction Creation Pattern:**
- Issue: The pattern of creating a `StockTransfer` + looping through items to create `StockTransferItem` + `StockTransaction` entries is repeated at least 8 times across the codebase.
- Files: `src/modules/orders/services.py` (fulfillment, warehouse pickup, walk-in cleanup), `src/modules/inventory/services.py` (StockTransferService.create_transfer), `src/modules/inventory/shift_service.py` (close_shift), `src/application/client/service.py` (onboard_client_with_balance)
- Impact: High risk of inconsistency. If the transfer creation pattern needs to change (e.g., adding audit fields), every copy must be updated.
- Fix approach: Create a shared `TransferBuilder` or service method in the inventory module that encapsulates transfer + items + ledger creation.

**Empty Cache Infrastructure:**
- Issue: Redis configuration exists in `src/core/config.py` (REDISHOST, REDISPORT, REDISUSER, REDISPASSWORD), but the `src/infrastructure/cache/` directory is empty. No caching is implemented anywhere.
- Files: `src/core/config.py` (lines 55-58), `src/infrastructure/cache/` (empty)
- Impact: Every request hits the database. The `get_current_user` dependency (`src/modules/auth/dependencies.py` line 58) queries the DB on every authenticated request ("SLOW PATH"). No caching of catalog products, user lookups, or balance queries.
- Fix approach: Implement a Redis client in `src/infrastructure/cache/`. Start with caching user lookups in the auth dependency (keyed by user_id from JWT, invalidated on user update).

**Stale Migration File in Project Root:**
- Issue: A file named `a1b2c3d4e5f6_add_triggers_and_capitalization.py` sits in the project root, not in `alembic/versions/`. It appears to be an orphaned/old migration that was superseded by the consolidated migrations.
- Files: `C:/Users/Sanjar/Desktop/munavvar-a/a1b2c3d4e5f6_add_triggers_and_capitalization.py`
- Impact: Confusing for developers. Could be accidentally applied.
- Fix approach: Delete the file. The triggers are already in `alembic/versions/c650cec7ccb0_triggers.py`.

## Security Considerations

**Client Login Endpoint Has No Password Verification:**
- Risk: The `client_login()` method in `src/modules/auth/services.py` (lines 58-89) issues a JWT token with just a phone number -- no password check, no OTP, no verification whatsoever. Anyone who knows a client's phone number can obtain their access token.
- Files: `src/modules/auth/services.py` (lines 58-89), `src/api/v1/client/login.py` (lines 14-29)
- Current mitigation: None. The endpoint is live and publicly accessible.
- Recommendations: Implement OTP (SMS/Telegram) verification for client login. At minimum, add a password check identical to `local_login()`. This is a critical security vulnerability.

**No Rate Limiting on Authentication Endpoints:**
- Risk: The login endpoints (`/api/v1/auth/login`, `/api/v1/client/login`) have no rate limiting. An attacker can brute-force credentials or enumerate phone numbers without restriction.
- Files: `src/api/v1/auth/login.py`, `src/api/v1/client/login.py`
- Current mitigation: None. No rate limiting middleware exists anywhere in the codebase.
- Recommendations: Add rate limiting middleware (e.g., `slowapi` or custom Redis-based limiter). Apply aggressive limits to auth endpoints (5 attempts per minute per IP). Apply moderate limits to all API routes.

**JWT Token Expiry Set to 7 Days, No Refresh Token, No Blacklist:**
- Risk: Access tokens are valid for 7 days (`ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7` in `src/core/config.py` line 31). There is no refresh token mechanism. The JWT includes a `jti` field intended for blacklisting (comment on line 35 of `src/core/security/jwt.py`), but no blacklist implementation exists. There is no logout endpoint.
- Files: `src/core/config.py` (line 31), `src/core/security/jwt.py` (line 35), `src/modules/auth/services.py`
- Current mitigation: Tokens are signed with HS256. User deactivation is checked on each request via `get_current_user`.
- Recommendations: Reduce access token TTL to 15-30 minutes. Implement refresh token rotation. Implement JWT blacklist in Redis (using jti). Add a logout endpoint.

**Client API Endpoints Use ORDERS_EDIT Scope Instead of ORDERS_CREATE:**
- Risk: The client-facing order creation, add-item, and remove-item endpoints in `src/api/v1/client/orders.py` require `Scope.ORDERS_EDIT` (lines 40, 70, 88). But `ORDERS_EDIT` is only assigned to ADMIN role in `src/core/security/permissions.py` (line 83). Client roles (CLIENT_B2C, CLIENT_B2B) only have `ORDERS_CREATE`. This means clients cannot create orders through their own API.
- Files: `src/api/v1/client/orders.py` (lines 40, 70, 88), `src/core/security/permissions.py` (lines 126-138)
- Current mitigation: None -- this is a functional bug.
- Recommendations: Change client order endpoints to use `Scope.ORDERS_CREATE` for order creation and define a new scope or use `ORDERS_CREATE` for cart modification.

**No IDOR Protection on Client Order Detail Endpoint:**
- Risk: The `get_order_details` endpoint in `src/api/v1/client/orders.py` (line 50) does not pass `requesting_user_id` to `get_order_with_details()`. This means any authenticated client can view any order's details by guessing the UUID.
- Files: `src/api/v1/client/orders.py` (line 61), `src/modules/orders/services.py` (lines 404-426)
- Current mitigation: The IDOR check exists in the service (lines 417-424) but is not activated because `requesting_user_id` is not passed.
- Recommendations: Pass `requesting_user_id=client.id` in the client endpoint. The courier endpoint has the same issue at `src/api/v1/courier/orders.py` line 47.

**SQL Injection Risk in Inventory Search:**
- Risk: The `search_inventories` method in `src/modules/inventory/repositories.py` (line 130) uses `self.model.name.ilike(f"%{search_query}%")` with direct string interpolation into a LIKE pattern. While SQLAlchemy parameterizes the outer query, special LIKE characters (%, _) in user input are not escaped, allowing pattern injection.
- Files: `src/modules/inventory/repositories.py` (line 130)
- Current mitigation: SQLAlchemy parameterization prevents SQL injection proper, but LIKE pattern injection can return unexpected results.
- Recommendations: Escape `%` and `_` characters in `search_query` before interpolation, or use a dedicated search utility.

**Syntax Error in Exception Handling:**
- Risk: In `src/modules/auth/dependencies.py` line 69, the except clause reads `except ValueError, TypeError:` which is Python 2 syntax. In Python 3 this catches `ValueError` and assigns it to the name `TypeError`, shadowing the built-in `TypeError`. Actual `TypeError` exceptions will not be caught.
- Files: `src/modules/auth/dependencies.py` (line 69)
- Current mitigation: The code likely works for the common case (invalid UUID string raises ValueError), but TypeError from other causes will propagate as 500.
- Recommendations: Change to `except (ValueError, TypeError):` with parentheses.

## Performance Bottlenecks

**DB Query on Every Authenticated Request:**
- Problem: The `get_current_user` dependency (`src/modules/auth/dependencies.py` line 58) executes a database query for every authenticated API call. With the "fast path" / "slow path" split in the comments, the slow path is always used when endpoints depend on `get_current_user`.
- Files: `src/modules/auth/dependencies.py` (lines 58-88)
- Cause: No caching layer. The empty `src/infrastructure/cache/` directory confirms Redis is configured but unused.
- Improvement path: Cache user objects in Redis with a short TTL (60s). Invalidate on user update/deactivation. Use the JWT `jti` for cache key or `sub` (user_id).

**Heavy Eager Loading on Order Search:**
- Problem: The `search_orders` repository method loads 5 levels of relationships for every order in the result set: client (+ identities), courier (+ identities), client_inventory, items (+ products), and stock_transfers (+ items). This is always loaded even when listing orders in a table view.
- Files: `src/modules/orders/repositories.py` (lines 190-198)
- Cause: A single "fully loaded" query pattern is used for both list and detail views.
- Improvement path: Create a lightweight `search_orders_summary` method that only loads client name and basic order data for list views. Reserve the full eager loading for `get_with_details` (single order detail).

**No Pagination Metadata on Order Search:**
- Problem: The `search_orders` endpoint returns `list[OrderResponse]` without total count, making it impossible for the frontend to implement proper pagination (page count, "Load More", etc.).
- Files: `src/api/v1/backoffice/orders.py` (line 33), `src/modules/orders/services.py` (lines 1119-1150)
- Cause: The service returns only the list, no count query is executed.
- Improvement path: Add a parallel `count` query (like in `src/modules/users/queries.py`) and return `{"total_count": N, "orders": [...]}`.

**Sequential Item Processing in Transfer Creation:**
- Problem: When creating transfers with multiple items, each `transfer_items.add()` and `transactions.add()` call is a separate `INSERT ... RETURNING` flush. For an order with 5 items, this is 10+ sequential round trips within a transaction.
- Files: `src/modules/orders/services.py` (lines 754-792), `src/modules/inventory/services.py` (lines 354-370)
- Cause: Individual `add()` calls instead of using `add_many()` (which does bulk insert).
- Improvement path: Collect all transfer items and transactions into lists, then use `add_many()` for batch insertion.

## Fragile Areas

**Order Status Transitions Have No State Machine:**
- Files: `src/modules/orders/services.py` (method `update_status`, lines 583-628)
- Why fragile: The `update_status` method allows arbitrary status transitions. The only guard is: (1) pickup orders cannot use delivery statuses, and (2) the `assign_courier` method blocks DELIVERED/CANCELLED orders. There is no validation that prevents, e.g., transitioning from DELIVERED back to NEW, or from CANCELLED to IN_TRANSIT. The `InvalidOrderStatusError` exception class exists in `src/modules/orders/exceptions.py` but is never used.
- Safe modification: Add a `VALID_TRANSITIONS` dict mapping `{current_status: set(allowed_next_statuses)}` and validate transitions in `update_status` before proceeding.
- Test coverage: No tests exist for status transitions (the `tests/` directory contains only an empty `conftest.py`).

**Shift Close Assumes Single System Warehouse:**
- Files: `src/modules/inventory/shift_service.py` (lines 80-84)
- Why fragile: `close_shift` calls `get_system_inventory(InventoryType.WAREHOUSE)` which uses `scalar_one()` -- it will crash if there are zero or multiple warehouses. The system now supports multiple warehouses (WarehouseService exists), but close_shift always routes returns to a single system warehouse.
- Safe modification: Require the `CloseShiftRequest` to include a target `warehouse_id`. Fall back to default warehouse only if not specified.
- Test coverage: No tests.

**Courier API Endpoints Use Wrong Scope:**
- Files: `src/api/v1/courier/orders.py` (lines 27, 56, 74, 92)
- Why fragile: The courier order creation, add-item, and remove-item endpoints require `Scope.ORDERS_EDIT` which is an admin-only scope. Courier role has `Scope.ORDERS_DELIVER` in `src/core/security/permissions.py`. This means couriers currently cannot use their own API endpoints for order modification.
- Safe modification: Review each courier endpoint and assign appropriate scopes (ORDERS_DELIVER for status changes, ORDERS_READ for viewing).
- Test coverage: No tests.

**Walk-in User Cleanup Depends on Hardcoded UUID:**
- Files: `src/modules/orders/services.py` (line 914), `src/core/constants.py` (WALKIN_USER_ID)
- Why fragile: The walk-in inventory cleanup (writing off products to VIRTUAL_LOSS after anonymous warehouse sale) triggers only when `order.client_id == WALKIN_USER_ID`. If this constant changes or the walk-in user is not seeded correctly, anonymous purchases will accumulate phantom inventory.
- Safe modification: Add a DB check constraint or a flag on the User model to identify system/walk-in users rather than relying on a hardcoded UUID comparison.
- Test coverage: No tests.

## Missing Critical Features

**No Order Cancellation Implementation:**
- Problem: `ORDERS_CANCEL` scope is defined and assigned to ADMIN, CLIENT_B2C, and CLIENT_B2B roles in `src/core/security/permissions.py`, and `OrderStatus.CANCELLED` exists in `src/modules/orders/enums.py`. However, there is no cancel endpoint or cancel service method. The only way to cancel is through the generic `update_status()` which lacks any cancellation-specific logic (no inventory reversal, no financial reversal).
- Blocks: Clients and admins cannot cancel orders. If an order is cancelled after delivery, the inventory and financial ledger entries are not reversed, causing balance discrepancies.

**No Logout / Token Revocation:**
- Problem: No logout endpoint exists. JWTs cannot be revoked. Once issued, a token is valid for 7 days regardless of user actions (password change, deactivation by admin, etc.).
- Blocks: Admin cannot immediately revoke access for a compromised account. Users cannot log out.

**No CONTRACT Payment Method Handling:**
- Problem: `PaymentMethod.CONTRACT` exists in `src/modules/orders/enums.py` (line 22) but neither `_process_financial_settlement()` nor `_process_pickup_settlement()` handle it. If an order with CONTRACT payment is delivered, only the Revenue -> Client debt is created, but no settlement transaction follows (the `if/elif` chain in lines 984-1011 falls through).
- Blocks: B2B customers using contract-based billing will have permanently unsettled debts in the financial ledger.

## Test Coverage Gaps

**Effectively Zero Test Coverage:**
- What's not tested: The entire application. The `tests/` directory contains only an empty `tests/conftest.py`. No unit tests, no integration tests, no API tests exist.
- Files: `tests/conftest.py` (empty)
- Risk: Every code change is deployed without automated verification. The complex business logic (order fulfillment, tara exchange, financial settlement, inventory balance triggers) has no safety net. The duplicate code patterns make manual testing unreliable -- it is easy to fix one path and miss the other.
- Priority: **Critical**. Start with integration tests for the order fulfillment flow (`update_status` -> DELIVERED), as this touches the most modules and has the highest financial impact. Then add tests for the transfer service (`StockTransferService.create_transfer`) which validates routing rules.

## Dependencies at Risk

**No Dependency Pinning Visibility:**
- Risk: While `uv.lock` exists for Python dependency locking, the `pyproject.toml` should be reviewed for overly broad version ranges on critical packages (SQLAlchemy, FastAPI, Pydantic). A major version bump in any of these could break the application silently.
- Impact: Deployment could pull incompatible versions.
- Migration plan: Pin major versions in `pyproject.toml`. Maintain `uv.lock` as the source of truth for exact versions.

---

*Concerns audit: 2026-03-27*
