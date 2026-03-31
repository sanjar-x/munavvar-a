# Courier Auth + Assigned Orders API v2

**Date:** 2026-03-31
**Status:** Proposed

## Summary

Безопасный courier-facing API для мобильного приложения курьеров.

Цель:
- использовать уже существующий staff JWT login;
- дать курьеру доступ только к своим назначенным заказам;
- ограничить изменения заказа только разрешёнными courier-переходами;
- исключить IDOR, произвольные status changes и повторный fulfillment.

---

## 1. Scope

### In scope
- login курьера через существующий staff auth;
- список активных заказов текущего курьера;
- детали конкретного назначенного заказа;
- безопасные courier actions: start, arrive, deliver;
- partial delivery через `actual_items`;
- защита от повторных складских/финансовых side effects.

### Out of scope
- новый auth backend;
- refresh tokens / session revocation;
- история заказов курьера;
- отмена заказа курьером;
- route sheets / live tracking / geolocation.

---

## 2. Current repo baseline

### Existing auth
В проекте уже есть staff login:
- `POST /api/v1/auth/login`
- `Role.COURIER` уже входит в `STAFF_ROLES`
- access token уже содержит `scopes`

Relevant files:
- `src/api/v1/auth/login.py`
- `src/modules/auth/services.py`
- `src/modules/auth/dependencies.py`
- `src/core/security/permissions.py`

### Existing courier order surface
Courier routes уже существуют в:
- `src/api/v1/courier/orders.py`

Current risks in current implementation:
- `GET /courier/orders/{order_id}` не передаёт `requesting_user_id` в `get_order_with_details()`;
- `PATCH /courier/orders/{order_id}/status` даёт слишком широкий доступ к `OrderStatus`;
- `POST /courier/orders/{order_id}/deliver` не передаёт acting courier id;
- `/tasks` объявлен после `/{order_id}`, что рискованно для route matching.

### Existing order ownership signal
Защита от IDOR уже частично есть в сервисе:
- `BaseOrderService.get_order_with_details(order_id, requesting_user_id=...)`
- `OrderAccessDeniedError`

Relevant files:
- `src/modules/orders/services.py`
- `src/modules/orders/exceptions.py`

---

## 3. Auth design

### 3.1 Login
Использовать существующий endpoint:

`POST /api/v1/auth/login`

Request format:
- `username` = phone
- `password`

Response:

```json
{
  "access_token": "jwt",
  "token_type": "bearer"
}
```

### 3.2 Required scopes
Courier API требует:
- `orders:read`
- `orders:deliver`
- `profile:read`

### 3.3 Authorization rules
Для всех courier order endpoints:
1. пользователь должен быть активным;
2. пользователь должен быть `Role.COURIER`;
3. order-level доступ разрешён только если:
   - `order.courier_id == current_user.id`

Если ownership check не проходит:
- `403 ORDER_ACCESS_DENIED`

---

## 4. API surface

## 4.1 Get assigned tasks
### `GET /api/v1/courier/orders/tasks`

### Purpose
Вернуть активные заказы текущего курьера.

### Auth
- scope: `orders:read`

### Included statuses
- `ASSIGNED`
- `IN_TRANSIT`
- `ARRIVED`

### Excluded statuses
- `NEW`
- `DELIVERED`
- `CANCELLED`

### Sorting
- `created_at ASC`

### Response

```json
[
  {
    "id": "uuid",
    "status": "assigned",
    "client": {
      "id": "uuid",
      "username": "Client Name",
      "phone": "+998..."
    },
    "client_inventory": {
      "id": "uuid",
      "name": "Address / Location"
    },
    "items_summary": [
      {
        "product_id": "uuid",
        "product_name": "Munavvar 19L",
        "quantity": 2
      }
    ],
    "total_amount": 120000,
    "payment_method": "cash",
    "created_at": "2026-03-31T10:00:00Z",
    "updated_at": "2026-03-31T10:15:00Z"
  }
]
```

### Notes
Для этого endpoint должен использоваться отдельный lightweight response DTO, а не полный `OrderResponse`.

---

## 4.2 Get assigned order details
### `GET /api/v1/courier/orders/{order_id}`

### Purpose
Вернуть детали только назначенного этому курьеру заказа.

### Auth
- scope: `orders:read`

### Response

```json
{
  "id": "uuid",
  "status": "assigned",
  "client": {
    "id": "uuid",
    "username": "Client Name",
    "phone": "+998..."
  },
  "client_inventory": {
    "id": "uuid",
    "name": "Address / Location"
  },
  "courier_id": "uuid",
  "payment_method": "cash",
  "total_amount": 120000,
  "items": [
    {
      "id": "uuid",
      "product_id": "uuid",
      "product": {
        "id": "uuid",
        "name": "Munavvar 19L"
      },
      "quantity": 2,
      "unit_price": 60000,
      "total": 120000
    }
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

### Authorization behavior
- if order not found → `404 ORDER_NOT_FOUND`
- if order exists but assigned to another courier → `403 ORDER_ACCESS_DENIED`

---

## 4.3 Start delivery
### `POST /api/v1/courier/orders/{order_id}/start`

### Purpose
Transition:
- `ASSIGNED -> IN_TRANSIT`

### Auth
- scope: `orders:deliver`

### Request body
No body.

### Response
Updated courier order summary.

### Rules
Allowed only if:
- order belongs to current courier
- current status is `ASSIGNED`

Otherwise:
- `403 ORDER_ACCESS_DENIED`
- `409 INVALID_ORDER_STATUS`

---

## 4.4 Mark arrived
### `POST /api/v1/courier/orders/{order_id}/arrive`

### Purpose
Transition:
- `IN_TRANSIT -> ARRIVED`

### Auth
- scope: `orders:deliver`

### Request body
No body.

### Response
Updated courier order summary.

### Rules
Allowed only if:
- order belongs to current courier
- current status is `IN_TRANSIT`

---

## 4.5 Deliver order
### `POST /api/v1/courier/orders/{order_id}/deliver`

### Purpose
Transition:
- `ARRIVED -> DELIVERED`

### Auth
- scope: `orders:deliver`

### Request

```json
{
  "actual_items": [
    {
      "product_id": "uuid",
      "quantity": 2
    }
  ]
}
```

### Behavior
- if `actual_items` is omitted → full delivery;
- if `actual_items` is provided → partial delivery is allowed only within ordered quantities;
- fulfillment side effects run exactly once.

### Rules
Allowed only if:
- order belongs to current courier
- current status is `ARRIVED`
- order is not already terminal

### Errors
- `403 ORDER_ACCESS_DENIED`
- `409 INVALID_ORDER_STATUS`
- `409 DELIVERY_QUANTITY_EXCEEDED`
- optional dedicated error: `ORDER_ALREADY_DELIVERED`

---

## 4.6 Deprecated / forbidden surface
### `PATCH /api/v1/courier/orders/{order_id}/status`

This endpoint should be removed or deprecated for courier clients.

Reason:
- exposes generic `OrderStatus` mutation surface;
- bypasses domain-safe action semantics;
- makes ownership and transition validation easier to miss;
- conflicts with permission model where `orders:cancel` is separate from `orders:deliver`.

---

## 5. Business rules

### 5.1 Ownership
Courier may:
- read only own assigned orders;
- mutate only own assigned orders.

### 5.2 Allowed courier transitions
Only these transitions are allowed:
- `ASSIGNED -> IN_TRANSIT`
- `IN_TRANSIT -> ARRIVED`
- `ARRIVED -> DELIVERED`

### 5.3 Forbidden transitions
Forbidden:
- `ASSIGNED -> DELIVERED`
- `ASSIGNED -> CANCELLED`
- `ARRIVED -> ASSIGNED`
- `DELIVERED -> anything`
- `CANCELLED -> anything`

### 5.4 Courier cannot cancel orders in v1
Cancellation remains outside courier v1 scope.

### 5.5 Single-shot fulfillment
Transfers, inventory changes, and financial settlement must happen only once for a given order.

---

## 6. Error model

### 401 Unauthorized
- `INVALID_TOKEN_PAYLOAD`
- `USER_NOT_FOUND`

### 403 Forbidden
- `INSUFFICIENT_PERMISSIONS`
- `ORDER_ACCESS_DENIED`
- `USER_BANNED`

### 404 Not Found
- `ORDER_NOT_FOUND`

### 409 Conflict
- `INVALID_ORDER_STATUS`
- `DELIVERY_QUANTITY_EXCEEDED`
- optional: `ORDER_ALREADY_DELIVERED`

### 422 Validation Error
- invalid UUID
- invalid body shape
- invalid enum value

---

## 7. Data model impact

### Required DB changes
None required for v1.

Current model already has:
- `orders.courier_id`
- `orders.status`

This is sufficient if service-level authorization and transition rules are implemented.

### Optional future additions
Not required for v1, but useful later:
- `started_at`
- `arrived_at`
- `delivered_at`
- courier action audit trail

---

## 8. Required code changes by file

## 8.1 `src/api/v1/courier/orders.py`
Required changes:
1. Move static routes before dynamic route:
   - `/tasks`
   - then `/{order_id}`
2. Remove or deprecate `PATCH /{order_id}/status`
3. Add explicit action endpoints:
   - `POST /{order_id}/start`
   - `POST /{order_id}/arrive`
4. Pass `courier.id` into service layer for all detail/mutation operations

## 8.2 `src/modules/orders/services.py`
Required changes:
1. Add courier-aware access assertion
2. Add courier-safe transition validation
3. Add terminal guard to block repeat delivery effects
4. Replace generic mutation path with explicit methods:
   - `get_courier_order(order_id, courier_id)`
   - `start_delivery(order_id, courier_id)`
   - `mark_arrived(order_id, courier_id)`
   - `deliver_order(order_id, courier_id, actual_items=None)`

## 8.3 `src/modules/orders/schemas.py`
Add dedicated courier response schemas:
- `CourierTaskItemSummary`
- `CourierTaskResponse`
- `CourierOrderDetailResponse`
- optional action response DTO

## 8.4 `src/modules/orders/exceptions.py`
Optional additions:
- dedicated `OrderAlreadyDeliveredError`
or reuse:
- `InvalidOrderStatusError` with stricter messages/details

## 8.5 Tests
Expand/add tests for:
- courier A cannot read courier B order
- courier A cannot mutate courier B order
- `/tasks` resolves correctly
- `ASSIGNED -> IN_TRANSIT` works
- `IN_TRANSIT -> ARRIVED` works
- `ARRIVED -> DELIVERED` works
- repeated deliver returns `409`
- courier cannot set `CANCELLED`
- unassigned order is inaccessible

---

## 9. Rollout plan

### Phase 1
- route order fix
- remove generic status patch from courier flow
- add actor-aware service methods

### Phase 2
- introduce courier DTOs
- add unit + integration tests

### Phase 3
- mobile integration
- smoke testing with real courier users

---

## 10. Go / No-go

### Current state
No-go.

### Go criteria
Implementation is approved only after:
1. ownership enforcement;
2. explicit courier transitions;
3. terminal/idempotency protection;
4. route order fix;
5. test coverage for authz + transitions.

---

## 11. Recommended final API

Preferred v1 courier surface:
- `POST /api/v1/auth/login`
- `GET /api/v1/courier/orders/tasks`
- `GET /api/v1/courier/orders/{id}`
- `POST /api/v1/courier/orders/{id}/start`
- `POST /api/v1/courier/orders/{id}/arrive`
- `POST /api/v1/courier/orders/{id}/deliver`

This is preferred over a generic status patch endpoint because it is safer, easier to test, and better aligned with the business workflow.
