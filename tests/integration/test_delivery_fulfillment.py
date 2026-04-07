"""TEST-01: Order delivery fulfillment characterization test.

Covers the full delivery cycle:
  create order -> assign courier -> deliver
and verifies both HTTP responses AND final balance state
(inventory_balances + accounts.balance).
"""

from sqlalchemy import select

from src.infrastructure.database.models import Account, Balance
from src.modules.users.enums import Role
from tests.conftest import make_auth_headers
from tests.integration.conftest import load_stock


class TestDeliveryFulfillment:
    async def test_cash_delivery_fulfillment(
        self,
        client,
        db_session,
        admin_user,
        courier_user,
        client_user,
        products,
        warehouse_inventory,
        courier_inventory,
        client_inventory,
        courier_account,
        client_account,
        system_entities,
    ):
        # -- Setup: load courier with 10 water --------
        await load_stock(
            session=db_session,
            from_inv_id=(system_entities["virtual_vendor"].id),
            to_inv_id=courier_inventory.id,
            product_id=products["water"].id,
            quantity=10,
            created_by_id=(system_entities["system_user"].id),
        )

        headers = make_auth_headers(admin_user.id, Role.ADMIN)

        # -- Record pre-state for system accounts -----
        rev_before = (
            await db_session.execute(
                select(Account.balance).where(
                    Account.id == system_entities["revenue_account"].id
                )
            )
        ).scalar_one()

        # == Step 1: Create order ======================
        resp = await client.post(
            f"/api/v1/backoffice/orders/?clientId={client_user.id}",
            json={
                "items": [
                    {
                        "product_id": str(products["water"].id),
                        "quantity": 2,
                    }
                ],
                "payment_method": "cash",
                "client_inventory_id": str(client_inventory.id),
                "capitalize_missing_tara": True,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        order_data = resp.json()
        order_id = order_data["id"]

        # == Step 2: Assign courier ====================
        resp = await client.patch(
            f"/api/v1/backoffice/orders/{order_id}/assign",
            json={
                "courierId": str(courier_user.id),
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "assigned"

        # == Step 3: Move order through delivery statuses ===
        resp = await client.patch(
            f"/api/v1/backoffice/orders/{order_id}/in-transit",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "in_transit"

        resp = await client.patch(
            f"/api/v1/backoffice/orders/{order_id}/arrived",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "arrived"

        resp = await client.patch(
            f"/api/v1/backoffice/orders/{order_id}/delivered",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "delivered"

        # == Step 3.1: Backoffice list must serialize transfer items fully ===
        resp = await client.get(
            "/api/v1/backoffice/orders/",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        listed_order = next(
            item for item in resp.json() if item["id"] == order_id
        )
        assert listed_order["stock_transfers"]
        first_transfer_item = listed_order["stock_transfers"][0]["items"][0]
        assert first_transfer_item["product"]["id"]
        assert first_transfer_item["product"]["name"]

        # == Step 4: Assert balance state ==============
        # Known amounts: water.price=20_000, qty=2,
        # total=40_000

        # 4a. Courier water: started 10, delivered 2
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id == courier_inventory.id,
                Balance.product_id == products["water"].id,
            )
        )
        assert result.scalar_one() == 8

        # 4b. Client water: 0 + 2 = 2
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id == client_inventory.id,
                Balance.product_id == products["water"].id,
            )
        )
        assert result.scalar_one() == 2

        # 4c. Courier tara: 0 + 2 returned = 2
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id == courier_inventory.id,
                Balance.product_id == products["tara"].id,
            )
        )
        assert result.scalar_one() == 2

        # 4d. Client tara: capitalized 2 + delivered 2 - returned 2 = 2
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id == client_inventory.id,
                Balance.product_id == products["tara"].id,
            )
        )
        assert result.scalar_one() == 2

        # 4e. Courier account: +40_000 (cash collected)
        result = await db_session.execute(
            select(Account.balance).where(Account.id == courier_account.id)
        )
        assert result.scalar_one() == 40_000

        # 4f. Client account: +40_000 debt, -40_000 paid
        result = await db_session.execute(
            select(Account.balance).where(Account.id == client_account.id)
        )
        assert result.scalar_one() == 0

        # 4g. Revenue account: delta = -40_000
        rev_after = (
            await db_session.execute(
                select(Account.balance).where(
                    Account.id == system_entities["revenue_account"].id
                )
            )
        ).scalar_one()
        assert rev_after - rev_before == -40_000
