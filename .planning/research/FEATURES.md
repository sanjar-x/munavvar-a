# Feature Landscape: Role-Based APIs for Water Delivery

**Domain:** Bottled water delivery management -- Courier, Client, and Staff/Operator APIs
**Researched:** 2026-03-27
**Overall Confidence:** HIGH (domain is well-established, patterns consistent across Trakop, Water Delivery Solutions, Rekart, MilkRide, and general last-mile delivery platforms)

---

## Context: What Already Exists

The codebase already has a partial implementation across three API audiences (`/api/v1/courier/`, `/api/v1/client/`, `/api/v1/backoffice/`). The existing system covers:

- **Courier**: order creation (admin-scoped), order details, add/remove items, deliver order (with actual items), status update, task list
- **Client**: tara check, order creation, order details, add/remove items, order history
- **Backoffice**: full order CRUD with search/filters, warehouse sale flow, courier assignment, status management, client/courier management, warehouse management, stock transfers, shift close

**Key gap**: The existing courier and client APIs use backoffice-level scopes and patterns. They are not yet tailored for their actual audience (e.g., courier endpoints still use `ORDERS_EDIT` scope meant for admins, client endpoints allow item editing that should be restricted). The APIs need to be re-scoped and extended with audience-appropriate features.

---

## Table Stakes

Features users expect. Missing = product feels incomplete or unusable for the target role.

### Courier API -- Table Stakes

| # | Feature | Why Expected | Complexity | Notes |
|---|---------|--------------|------------|-------|
| C1 | **Daily task list / route sheet** | Courier opens app, sees today's assigned deliveries. Without this, they cannot work. | Low | Exists partially (`GET /tasks`). Needs: filter by date, sort by delivery sequence, include address + phone. |
| C2 | **Order detail view** | Courier needs to see what to deliver (items, quantities, client address, phone, payment method). | Low | Exists (`GET /{order_id}`). Needs: client phone number, delivery address rendered prominently. |
| C3 | **Accept/start delivery** | Courier signals "I'm heading out" -- triggers `IN_TRANSIT` status. | Low | Exists partially (`PATCH /status`). Needs proper courier-scoped endpoint with `ORDERS_DELIVER` scope. |
| C4 | **Arrive at client** | Courier signals "I'm at the door" -- triggers `ARRIVED` status. Optional but standard in delivery apps. | Low | Same pattern as C3. |
| C5 | **Deliver order with confirmation** | Record actual items delivered (may differ from order), collect tara (empty bottles) returned by client, record payment collected. This is THE critical transaction. | High | Exists (`POST /{order_id}/deliver`). Needs: explicit tara return count, payment amount/method confirmation. Currently fires all stock + financial transactions atomically. |
| C6 | **View own inventory (van stock)** | Courier must see what they have in their van -- full bottles, empty bottles, equipment. | Low | Not yet exposed in courier API. Data exists in `inventory_balances` for `COURIER` inventory type. |
| C7 | **Cash/payment summary** | At any point, courier needs to know: how much cash they've collected, how many card payments recorded. For end-of-shift reconciliation. | Medium | Not yet exposed. Financial transactions exist in ledger. Need aggregation endpoint. |
| C8 | **Own profile view** | View own name, phone, assigned warehouse. | Low | Exists (`GET /profile`). |
| C9 | **Product catalog view** | See available products and prices (for on-site order creation if needed). | Low | Exists (`GET /catalog`). |

### Client API -- Table Stakes

| # | Feature | Why Expected | Complexity | Notes |
|---|---------|--------------|------------|-------|
| L1 | **Place order** | Client selects products, chooses address, picks payment method, submits. | Low | Exists (`POST /orders`). Needs: scope fix (currently `ORDERS_EDIT`, should be `ORDERS_CREATE`). |
| L2 | **Tara availability check** | Before ordering, client sees if they have enough empty bottles to exchange. Essential in water delivery. | Low | Exists (`POST /check-tara`). |
| L3 | **Order history** | Client sees past orders with statuses, dates, amounts. | Low | Exists (`GET /history`). Needs: pagination, date filters. |
| L4 | **Active order status** | Client sees current order: status (new, assigned, in transit, arrived, delivered), courier name + phone (once assigned). | Low | Partially exists via `GET /{order_id}`. Needs: courier contact info in response when assigned. |
| L5 | **Cancel order** | Client can cancel an order before it's in transit. | Low | Not yet exposed. Scope exists (`ORDERS_CANCEL`), logic exists. Needs endpoint. |
| L6 | **Tara (bottle) balance view** | Client sees: "You have 5 empty 19L bottles at address X." Core to water delivery -- determines what they can order. | Low | Not yet exposed in client API. Data exists in `inventory_balances`. |
| L7 | **Delivery addresses (inventories)** | View own delivery addresses. Each address is an inventory point with its own tara balance. | Low | Not yet exposed. Data exists (`CLIENT` type inventories). |
| L8 | **Own profile view** | View name, phone, addresses. | Low | Exists (`GET /profile`). |
| L9 | **Product catalog** | Browse products with prices. | Low | Exists (`GET /catalog`). |
| L10 | **Financial balance view** | B2B clients need: current debt/credit balance. B2C clients: payment history at minimum. | Medium | Not yet exposed. Data exists in financial accounts. |

### Staff/Operator API (Backoffice) -- Table Stakes

| # | Feature | Why Expected | Complexity | Notes |
|---|---------|--------------|------------|-------|
| S1 | **Order search + filters** | Operator searches orders by status, date, courier, client, amount range. | Low | Exists fully with comprehensive filter set. |
| S2 | **Create order on behalf of client** | Phone orders -- operator creates order for a client. | Low | Exists (`POST /orders`). |
| S3 | **Assign courier to order** | Dispatcher assigns or reassigns courier. | Low | Exists (`PATCH /{orderId}/assign`). |
| S4 | **Update order status** | Manual override of order status. | Low | Exists (`PATCH /{orderId}/status`). |
| S5 | **Client management** | CRUD clients, view client card (profile + balance + tara + orders). | Low | Exists fully (onboard, create, list, get, update, block). |
| S6 | **Courier management** | CRUD couriers, view courier card (profile + van stock + tasks). | Low | Exists (create, list, get, update, block). |
| S7 | **Warehouse management** | Create warehouses, view stock levels. | Low | Exists (create, list, detail with balances). |
| S8 | **Stock transfers** | Create and manage inventory movements (supply, inter-warehouse, courier load/return). | Low | Exists (create, list). |
| S9 | **Shift close / cash collection** | End-of-day: reconcile courier's cash, collect money, verify van stock. | Medium | Exists (`POST /shifts/close`). |
| S10 | **Warehouse pickup sale** | Walk-in customer buys at warehouse counter. | Low | Exists (create warehouse sale, capitalize tara, complete pickup). |
| S11 | **Courier loading** | Load courier's van with products from warehouse before shift. | Medium | Handled via stock transfers (`COURIER_LOAD`). Needs: dedicated endpoint or clearer workflow. |
| S12 | **Courier return processing** | After shift: unload remaining stock from van back to warehouse. | Medium | Handled via stock transfers (`COURIER_RETURN`). Same note as S11. |
| S13 | **Client tara capitalization** | Manually set or adjust a client's tara balance (for onboarding or corrections). | Low | Exists (`POST /{client_id}/inventory/capitalize`). |

---

## Differentiators

Features that set the product apart from basic order-entry systems. Not expected, but valued by operations teams and end users.

### Courier API -- Differentiators

| # | Feature | Value Proposition | Complexity | Notes |
|---|---------|-------------------|------------|-------|
| C10 | **Partial delivery / rejection handling** | Courier records "delivered 3 of 5 bottles, client rejected 2." System auto-adjusts stock + financials. Prevents manual correction by admin later. | High | Partially exists via `actual_items` in `OrderDeliverRequest`. Needs: explicit UI contract for partial/rejected items. |
| C11 | **On-site order creation** | Courier at client location, client wants to order more. Courier creates order and fulfills immediately. Reduces round-trips and captures impulse sales. | Medium | Not yet implemented. Requires: courier scope + immediate fulfillment flow. |
| C12 | **Delivery notes / comments** | Courier adds notes: "client not home, left with receptionist", "gate code is 4567." Useful for recurring deliveries. | Low | Not yet implemented. Add `notes` field to delivery confirmation. |
| C13 | **Offline-capable delivery confirmation** | In basements/elevators with no signal, courier can confirm delivery offline, sync later. Critical for water delivery (many basement deliveries). | High | Not in scope per PROJECT.md (web-first). Flag for future mobile app phase. |

### Client API -- Differentiators

| # | Feature | Value Proposition | Complexity | Notes |
|---|---------|-------------------|------------|-------|
| L11 | **Recurring order / subscription** | Client sets "deliver 10 bottles every Monday." Auto-creates orders. Reduces friction for regular B2B clients. | High | Not yet implemented. Explicitly OUT OF SCOPE for now per PROJECT.md focus, but critical for B2B retention long-term. |
| L12 | **Delivery rescheduling** | Client moves delivery to different date before courier is dispatched. Reduces cancellation rate. | Medium | Not yet implemented. Requires: date field on order, status guard (only while `NEW`). |
| L13 | **Multiple address management** | Client adds/edits delivery addresses themselves, each with its own tara balance. Self-service reduces admin load. | Low | Backend exists (client inventories). Needs: client-facing CRUD endpoints. |
| L14 | **Reorder from history** | Client taps "repeat this order." Copies items + address from a past order into a new draft. Reduces ordering friction. | Low | Not yet implemented. Pure frontend convenience backed by existing `POST /orders`. |
| L15 | **B2B invoice access** | B2B client views invoices, delivery acts, and financial statements. Scope `BILLS_READ` already defined. | Medium | Not yet implemented. Requires: invoice generation service, PDF export. |

### Staff/Operator API -- Differentiators

| # | Feature | Value Proposition | Complexity | Notes |
|---|---------|-------------------|------------|-------|
| S14 | **Dashboard summaries** | Today's stats: orders count by status, revenue, deliveries completed, pending, courier utilization. Gives dispatcher instant situational awareness. | Medium | Not yet implemented. Requires: aggregation queries. |
| S15 | **Batch courier assignment** | Assign multiple orders to a courier in one action. Dispatcher drags orders onto courier's route. | Medium | Not yet implemented. Requires: bulk endpoint. |
| S16 | **Client debt report** | Which clients owe money? Sorted by amount/age. Critical for B2B cash flow. | Medium | Not yet implemented. Financial data exists. Needs: aggregation endpoint with filters. |
| S17 | **Tara reconciliation report** | Which clients hold the most tara? Who hasn't returned bottles in N weeks? Prevents asset loss. | Medium | Not yet implemented. Inventory data exists. Needs: aggregation + time-based analysis. |
| S18 | **Courier performance view** | Deliveries per day, average time, success rate, cash collected. For operations management. | Medium | Not yet implemented. Requires: aggregation over order + financial data. |
| S19 | **Bulk order creation** | Create orders for multiple clients at once (e.g., "all Tuesday regulars need delivery"). Reduces dispatcher time. | Medium | Not yet implemented. Useful with subscription data. |

---

## Anti-Features

Features to explicitly NOT build in this milestone. Including rationale to prevent scope creep.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Real-time GPS tracking** | PROJECT.md explicitly excludes WebSocket/real-time. Adds massive complexity (persistent connections, battery drain, location privacy). Courier status updates (`IN_TRANSIT`, `ARRIVED`) are sufficient for water delivery SLAs. | Use status-based tracking. Client sees "Courier is on the way." No need for live dot on map. |
| **Push notifications** | Requires mobile app infrastructure (FCM/APNS), notification service, device token management. Web-first approach means no native push. | Rely on status polling from client app. Consider SMS via external service as a future add-on (not in this milestone). |
| **Route optimization / navigation** | Requires third-party API (Google Maps Directions API, OSRM), adds cost + complexity. Water delivery routes are often fixed weekly patterns, not dynamic. | Courier follows their known route. Dispatcher can sequence orders manually. Optimization deferred. |
| **Payment gateway integration** | PROJECT.md explicitly excludes this. Cash and P2P card transfers are the payment reality. No need for Stripe/etc. | Record payment method and amount. Reconcile at shift end. Manual process is fine. |
| **Subscription/recurring order engine** | High complexity (scheduler, conflict resolution, holiday handling, capacity planning). Not needed for MVP role-based APIs. | Manual order creation by dispatcher or client. Subscriptions are a future phase. |
| **Photo proof of delivery** | Requires file storage (S3), upload endpoint, image processing. Water delivery typically uses tara count as proof. | Delivery confirmation with actual item counts serves as proof. Add photo later if needed. |
| **Multi-language support (i18n)** | Single-market deployment (Uzbekistan). All users speak the same language. | Hardcode language. Internationalize only if expanding to new markets. |
| **Courier earnings/payout calculation** | Courier compensation is out of scope for delivery management. Handled by HR/payroll. | Track deliveries per courier. Export data for external payroll if needed. |
| **Customer ratings/reviews** | Adds complexity (review moderation, rating aggregation). Water delivery is a utility, not a marketplace. Regular clients have direct relationships with drivers. | Address complaints through admin/operator channels directly. |
| **Chat / messaging between courier and client** | Requires real-time infrastructure. Phone calls work fine for "can't find the building" situations. | Include client phone number in courier's order view. Courier calls directly. |

---

## Feature Dependencies

Dependencies determine build order within the milestone.

```
Auth scoping fix (scope cleanup) ──┐
                                    ├──> Courier API features
Courier inventory view (C6) ───────┘

Auth scoping fix ──────────────────┐
                                    ├──> Client API features
Client inventory view (L6, L7) ────┘

Courier API (C1-C9) ──────────────> Courier shift close (S9, S11, S12)
                                     (shift close validates courier stock)

Client API (L1-L6) ───────────────> Client onboarding flow (S5)
                                     (onboarding sets up what client uses)

Order delivery (C5) ──────────────> Cash summary (C7)
                                     (need deliveries to have cash to summarize)

Financial balance service ─────────> Client balance view (L10)
                                     > Client debt report (S16)

Inventory balance service ─────────> Tara balance view (L6)
                                     > Tara reconciliation report (S17)
                                     > Courier van stock view (C6)
```

### Dependency summary:
1. **Auth scope cleanup** must come first -- everything depends on correct role-to-scope mapping
2. **Inventory and financial balance read services** are foundational -- multiple features query these
3. **Courier API** and **Client API** can be built in parallel after scope cleanup
4. **Staff reporting features** (S14-S18) depend on operational data flowing through courier/client APIs

---

## MVP Recommendation

For this milestone (role-based APIs), prioritize in this order:

### Phase 1: Foundation (do first)
1. Fix auth scoping -- courier endpoints use `ORDERS_DELIVER` not `ORDERS_EDIT`, client endpoints use `ORDERS_CREATE` not `ORDERS_EDIT`
2. Inventory balance read endpoints for courier and client
3. Financial balance read endpoint for client

### Phase 2: Courier API (core workflow)
1. **C1** Daily task list (filtered, sorted, with address+phone)
2. **C3/C4** Accept delivery / arrive status transitions
3. **C5** Deliver order with tara return + payment confirmation
4. **C6** Van stock view
5. **C7** Cash/payment summary

### Phase 3: Client API (self-service)
1. **L1** Place order (scope fix + validation tightening)
2. **L2** Tara check (exists, verify correctness)
3. **L5** Cancel order
4. **L6** Tara balance view
5. **L7** Delivery addresses view
6. **L10** Financial balance view
7. **L3** Order history with pagination

### Phase 4: Staff API (operational completeness)
1. **S11/S12** Dedicated courier load/return endpoints
2. **S14** Dashboard summaries
3. **S16** Client debt report
4. **S17** Tara reconciliation report

### Defer to future milestones:
- **L11** Subscriptions -- high complexity, needs its own milestone
- **L15** B2B invoicing -- needs document generation infrastructure
- **C13** Offline support -- needs mobile app
- **S15** Batch assignment -- nice-to-have optimization
- **S18** Courier performance -- reporting phase
- **S19** Bulk order creation -- reporting/optimization phase

---

## Sources

- [Trakop - Bottled Water Delivery Software](https://www.trakop.com/water-delivery-software/)
- [Trakop - Empty Bottle Tracking](https://www.trakop.com/blog/track-and-manage-empty-bottles-with-bottled-water-delivery-software/)
- [Trakop - Admin Panel Dashboard](https://www.trakop.com/blog/admin-panel-the-smart-dispatch-dashboard-for-delivery-business/)
- [Water Delivery Solutions - Features](https://www.waterdeliverysolutions.com/features/)
- [Water Delivery Solutions - B2B Features](https://www.waterdeliverysolutions.com/blog/b2b-specific-features-of-water-delivery-software-for-inventory-management/)
- [Rekart - Empty Bottle Tracking](https://rekart.io/insights/empty-bottle-tracking-delivery-software)
- [ClickPost - Courier Software Features 2026](https://www.clickpost.ai/blog/courier-software)
- [DispatchTrack - Last Mile Delivery Mobile App](https://www.dispatchtrack.com/blog/last-mile-delivery-mobile-app/)
- [Dispatch Science - Back Office Features](https://www.dispatchscience.com/software-features/back-office/)
- [Track-POD - Proof of Delivery Apps](https://www.track-pod.com/blog/proof-of-delivery-apps/)
- [Airship - Cash Management for Courier Operations](https://airship.me/blog/mastering-cash-management-for-courier-operations-2/)
- [Digiteum - B2B Self-Service Portal](https://www.digiteum.com/b2b-self-service-web-portal/)
- [Octalsoftware - Water Delivery App Development Guide](https://www.octalsoftware.com/blog/water-delivery-app-development)
