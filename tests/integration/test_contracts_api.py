# tests/integration/test_contracts_api.py
"""Integration tests for the Contracts module.

Coverage:
  1. Admin lifecycle: create draft → activate → suspend → reinstate →
     terminate via HTTP.
  2. B2B client IDOR guard: client can only fetch their own contract.
  3. Admin price-item upsert (PUT /prices/{product_id}).
  4. Full B2B order flow with CONTRACT payment method:
     - price override from contract price items is applied
     - per-product quantity_used incremented on order creation
     - quantity_used decremented when order is CANCELLED
  5. Bank payment via POST /cashbox/accept-payment (payment_method=bank).
"""

from datetime import UTC

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    Account,
    Contract,
    ContractPriceItem,
    Identity,
    Inventory,
    User,
)
from src.modules.contracts.enums import ContractStatus
from src.modules.finances.enums import AccountType
from src.modules.inventory.enums import InventoryType
from src.modules.users.enums import AuthProvider, Role
from tests.conftest import make_auth_headers
from tests.integration.conftest import credit_account

# ──────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def admin_user(db_session: AsyncSession):
    user = User(
        username="Contracts Admin",
        role=Role.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    identity = Identity(
        user_id=user.id,
        provider=AuthProvider.LOCAL,
        provider_identity_id="+998900000001",
        password_hash="fakehash",
    )
    db_session.add(identity)
    await db_session.flush()
    return user


@pytest.fixture
async def b2b_user(db_session: AsyncSession):
    user = User(
        username="LLC Aqua Corp",
        role=Role.CLIENT_B2B,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    identity = Identity(
        user_id=user.id,
        provider=AuthProvider.LOCAL,
        provider_identity_id="+998900000002",
        password_hash="fakehash",
    )
    db_session.add(identity)
    await db_session.flush()
    return user


@pytest.fixture
async def other_b2b_user(db_session: AsyncSession):
    """Second B2B client — used for IDOR tests."""
    user = User(
        username="LLC Rival Corp",
        role=Role.CLIENT_B2B,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def b2b_account(db_session: AsyncSession, b2b_user, system_entities):
    acc = Account(
        user_id=b2b_user.id,
        type=AccountType.CLIENT,
        name="B2B Client Account",
        balance=0,
        is_active=True,
    )
    db_session.add(acc)
    await db_session.flush()
    return acc


@pytest.fixture
async def b2b_inventory(db_session: AsyncSession, b2b_user):
    inv = Inventory(
        user_id=b2b_user.id,
        type=InventoryType.CLIENT,
        name="B2B Office Address",
        is_active=True,
    )
    db_session.add(inv)
    await db_session.flush()
    return inv


@pytest.fixture
async def draft_contract(db_session: AsyncSession, b2b_user):
    """A DRAFT contract (not yet activated)."""
    contract = Contract(
        client_id=b2b_user.id,
        number="HOD-TEST-001",
        status=ContractStatus.DRAFT,
        start_date="2025-01-01",
        payment_due_days=30,
        legal_name="LLC Aqua Corp",
        inn="123456789",
        is_active=True,
    )
    db_session.add(contract)
    await db_session.flush()
    return contract


@pytest.fixture
async def active_contract(
    db_session: AsyncSession, b2b_user, draft_contract, admin_user
):
    """An ACTIVE contract (signed and activated)."""
    from datetime import datetime

    draft_contract.status = ContractStatus.ACTIVE
    draft_contract.signed_at = datetime.now(tz=UTC)
    draft_contract.signed_by_id = admin_user.id
    db_session.add(draft_contract)
    await db_session.flush()
    return draft_contract


# ──────────────────────────────────────────────────────────────────
# 1. Contract lifecycle (CRUD via HTTP)
# ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_admin_create_contract(
    client: AsyncClient,
    admin_user,
    b2b_user,
    system_entities,
):
    """POST /contracts/ creates a DRAFT contract."""
    headers = make_auth_headers(admin_user.id, Role.ADMIN)
    resp = await client.post(
        "/api/v1/backoffice/contracts/",
        params={"clientId": str(b2b_user.id)},
        headers=headers,
        json={
            "number": "HOD-2025-HTTP-001",
            "start_date": "2025-01-01",
            "payment_due_days": 30,
            "legal_name": "LLC Aqua Corp",
            "inn": "123456789",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == ContractStatus.DRAFT
    assert data["client_id"] == str(b2b_user.id)
    assert data["number"] == "HOD-2025-HTTP-001"


@pytest.mark.anyio
async def test_admin_activate_contract(
    client: AsyncClient,
    admin_user,
    draft_contract,
    system_entities,
):
    """POST /contracts/{id}/activate transitions DRAFT → ACTIVE."""
    headers = make_auth_headers(admin_user.id, Role.ADMIN)
    resp = await client.post(
        f"/api/v1/backoffice/contracts/{draft_contract.id}/activate",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == ContractStatus.ACTIVE
    assert data["signed_by_id"] == str(admin_user.id)
    assert data["signed_at"] is not None


@pytest.mark.anyio
async def test_admin_suspend_and_reinstate_contract(
    client: AsyncClient,
    admin_user,
    active_contract,
    system_entities,
):
    """
    POST /contracts/{id}/suspend → SUSPENDED
    POST /contracts/{id}/reinstate → ACTIVE
    """
    headers = make_auth_headers(admin_user.id, Role.ADMIN)

    # Suspend
    resp = await client.post(
        f"/api/v1/backoffice/contracts/{active_contract.id}/suspend",
        headers=headers,
        json={"reason": "Задержка оплаты"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == ContractStatus.SUSPENDED

    # Reinstate
    resp = await client.post(
        f"/api/v1/backoffice/contracts/{active_contract.id}/reinstate",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == ContractStatus.ACTIVE


@pytest.mark.anyio
async def test_admin_terminate_contract(
    client: AsyncClient,
    admin_user,
    active_contract,
    system_entities,
):
    """POST /contracts/{id}/terminate → TERMINATED."""
    headers = make_auth_headers(admin_user.id, Role.ADMIN)
    resp = await client.post(
        f"/api/v1/backoffice/contracts/{active_contract.id}/terminate",
        headers=headers,
        json={"reason": "Расторжение по инициативе стороны"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == ContractStatus.TERMINATED
    assert data["termination_reason"] == ("Расторжение по инициативе стороны")


# ──────────────────────────────────────────────────────────────────
# 2. IDOR guard: B2B client can only see their own contract
# ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_b2b_client_get_own_contract(
    client: AsyncClient,
    b2b_user,
    active_contract,
    system_entities,
):
    """GET /my-contract returns the current user's active contract."""
    headers = make_auth_headers(b2b_user.id, Role.CLIENT_B2B)
    resp = await client.get(
        "/api/v1/client/my-contract",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(active_contract.id)
    assert data["status"] == ContractStatus.ACTIVE


@pytest.mark.anyio
async def test_b2b_client_cannot_access_others_contract(
    client: AsyncClient,
    other_b2b_user,
    active_contract,
    system_entities,
):
    """
    A different B2B client must get 404 because they have no
    active contract of their own (not the other user's contract).
    """
    headers = make_auth_headers(other_b2b_user.id, Role.CLIENT_B2B)
    resp = await client.get(
        "/api/v1/client/my-contract",
        headers=headers,
    )
    # other_b2b_user has no active contract → 400 (CONTRACT_REQUIRED)
    assert resp.status_code == 400, resp.text


# ──────────────────────────────────────────────────────────────────
# 3. Price-item upsert
# ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_admin_set_price_item(
    client: AsyncClient,
    admin_user,
    active_contract,
    products,
    system_entities,
):
    """
    PUT /contracts/{id}/prices/{product_id} creates or updates a
    contract-specific price override.
    """
    headers = make_auth_headers(admin_user.id, Role.ADMIN)
    water = products["water"]
    contract_price = 15_000  # cheaper than catalog (20_000)

    resp = await client.put(
        f"/api/v1/backoffice/contracts/{active_contract.id}/prices/{water.id}",
        headers=headers,
        json={"price": contract_price, "quantity": 200},
    )
    assert resp.status_code in (200, 201), resp.text
    data = resp.json()
    assert data["price"] == contract_price
    assert data["product_id"] == str(water.id)
    assert data["quantity"] == 200

    # Upsert: update the price and quantity
    resp2 = await client.put(
        f"/api/v1/backoffice/contracts/{active_contract.id}/prices/{water.id}",
        headers=headers,
        json={"price": 12_000, "quantity": 300},
    )
    assert resp2.status_code in (200, 201), resp2.text
    assert resp2.json()["price"] == 12_000
    assert resp2.json()["quantity"] == 300


# ──────────────────────────────────────────────────────────────────
# 4. Full B2B order flow with CONTRACT payment
# ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_b2b_order_with_contract_price_override(
    client: AsyncClient,
    admin_user,
    b2b_user,
    b2b_account,
    b2b_inventory,
    active_contract,
    products,
    system_entities,
    db_session: AsyncSession,
):
    """
    Full B2B order with CONTRACT payment:
    - contract price (15 000) overrides catalog price (20 000)
    - total_amount = 15 000 × 2 = 30 000
    - quantity_used on price item is incremented by 2
    """
    from sqlalchemy import select

    water = products["water"]

    # 1. Set a contract price override (water: 15 000, quota: 100)
    headers = make_auth_headers(admin_user.id, Role.ADMIN)
    pi_resp = await client.put(
        f"/api/v1/backoffice/contracts/{active_contract.id}/prices/{water.id}",
        headers=headers,
        json={"price": 15_000, "quantity": 100},
    )
    assert pi_resp.status_code in (200, 201), pi_resp.text

    # 2. Create the B2B order via CLIENT API
    b2b_headers = make_auth_headers(b2b_user.id, Role.CLIENT_B2B)
    order_resp = await client.post(
        "/api/v1/client/orders/",
        headers=b2b_headers,
        json={
            "items": [{"product_id": str(water.id), "quantity": 2}],
            "client_inventory_id": str(b2b_inventory.id),
            "payment_method": "contract",
            "capitalize_missing_tara": True,
        },
    )
    assert order_resp.status_code == 201, order_resp.text
    order = order_resp.json()
    assert order["payment_method"] == "contract"
    assert order["contract_id"] == str(active_contract.id)
    # Price override: 15 000 × 2
    assert order["total_amount"] == 30_000

    # 3. Verify quantity_used was incremented
    result = await db_session.execute(
        select(ContractPriceItem.quantity_used).where(
            ContractPriceItem.contract_id == active_contract.id,
            ContractPriceItem.product_id == water.id,
        )
    )
    quantity_used = result.scalar_one()
    assert quantity_used == 2


@pytest.mark.anyio
async def test_b2b_order_cancel_releases_quantities(
    client: AsyncClient,
    admin_user,
    b2b_user,
    b2b_account,
    b2b_inventory,
    active_contract,
    products,
    system_entities,
    db_session: AsyncSession,
):
    """
    When a CONTRACT order is cancelled, the per-product
    quantity_used is decremented back to 0.
    """
    from sqlalchemy import select

    water = products["water"]

    # Set price item with quota
    adm_headers = make_auth_headers(admin_user.id, Role.ADMIN)
    pi_resp = await client.put(
        f"/api/v1/backoffice/contracts/{active_contract.id}/prices/{water.id}",
        headers=adm_headers,
        json={"price": 15_000, "quantity": 50},
    )
    assert pi_resp.status_code in (200, 201), pi_resp.text

    # Create the order
    b2b_headers = make_auth_headers(b2b_user.id, Role.CLIENT_B2B)
    order_resp = await client.post(
        "/api/v1/client/orders/",
        headers=b2b_headers,
        json={
            "items": [{"product_id": str(water.id), "quantity": 1}],
            "client_inventory_id": str(b2b_inventory.id),
            "payment_method": "contract",
            "capitalize_missing_tara": True,
        },
    )
    assert order_resp.status_code == 201, order_resp.text
    order_id = order_resp.json()["id"]

    # Cancel the order via backoffice
    admin_headers = make_auth_headers(admin_user.id, Role.ADMIN)
    cancel_resp = await client.patch(
        f"/api/v1/backoffice/orders/{order_id}/cancelled",
        headers=admin_headers,
    )
    assert cancel_resp.status_code == 200, cancel_resp.text
    assert cancel_resp.json()["status"] == "cancelled"

    # Verify quantity_used is back to 0
    result = await db_session.execute(
        select(ContractPriceItem.quantity_used).where(
            ContractPriceItem.contract_id == active_contract.id,
            ContractPriceItem.product_id == water.id,
        )
    )
    quantity_used = result.scalar_one()
    assert quantity_used == 0


@pytest.mark.anyio
async def test_b2c_client_cannot_use_contract_payment(
    client: AsyncClient,
    db_session: AsyncSession,
    system_entities,
    products,
):
    """
    A B2C client attempting CONTRACT payment gets a 400 Bad Request.
    """
    # Create a B2C user + inventory (no contract)
    b2c_user = User(
        username="B2C User",
        role=Role.CLIENT_B2C,
        is_active=True,
    )
    db_session.add(b2c_user)
    await db_session.flush()

    inv = Inventory(
        user_id=b2c_user.id,
        type=InventoryType.CLIENT,
        name="B2C Address",
        is_active=True,
    )
    db_session.add(inv)
    await db_session.flush()

    headers = make_auth_headers(b2c_user.id, Role.CLIENT_B2C)
    resp = await client.post(
        "/api/v1/client/orders/",
        headers=headers,
        json={
            "items": [
                {
                    "product_id": str(products["water"].id),
                    "quantity": 1,
                }
            ],
            "client_inventory_id": str(inv.id),
            "payment_method": "contract",
            "capitalize_missing_tara": True,
        },
    )
    assert resp.status_code == 400, resp.text
    assert "contract" in resp.json()["error"]["message"].lower()


# ──────────────────────────────────────────────────────────────────
# 5. Bank payment via /cashbox/accept-payment
# ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_accept_bank_payment(
    client: AsyncClient,
    admin_user,
    b2b_user,
    b2b_account,
    system_entities,
    db_session: AsyncSession,
):
    """
    POST /cashbox/accept-payment with payment_method=bank creates a
    COMPLETED transaction from CLIENT → BANK system account,
    and client balance decreases.
    """
    from sqlalchemy import select

    # Pre-fund the client account with 100 000 debt
    await credit_account(
        session=db_session,
        from_account_id=b2b_account.id,
        to_account_id=system_entities["revenue_account"].id,
        amount=100_000,
        created_by_id=system_entities["system_user"].id,
    )
    await db_session.flush()

    # Accept payment via bank transfer
    cashier_headers = make_auth_headers(admin_user.id, Role.ADMIN)
    resp = await client.post(
        "/api/v1/backoffice/finances/cashbox/accept-payment",
        headers=cashier_headers,
        json={
            "client_id": str(b2b_user.id),
            "amount": 50_000,
            "payment_method": "bank",
            "reason": "Оплата по договору HOD-TEST-001",
        },
    )
    assert resp.status_code == 201, resp.text
    txn = resp.json()
    assert txn["status"] == "completed"
    assert txn["amount"] == 50_000

    # Client balance should have decreased by 50 000
    result = await db_session.execute(
        select(Account.balance).where(Account.id == b2b_account.id)
    )
    balance = result.scalar_one()
    # balance was 100 000 (debt), now 50 000 after payment
    # Trigger updates balance: credit_account increased it,
    # bank payment decreases it
    assert balance == 50_000
