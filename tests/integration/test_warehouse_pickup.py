"""TEST-02: Warehouse pickup characterization test.

Covers the warehouse pickup flow:
  create warehouse sale -> complete pickup
and verifies both HTTP responses AND final balance state
(inventory_balances + accounts.balance).
"""
from sqlalchemy import select

from src.infrastructure.database.models import Account, Balance
from src.modules.users.enums import Role
from tests.conftest import make_auth_headers
from tests.integration.conftest import load_stock


class TestWarehousePickup:
    async def test_warehouse_pickup_cash_payment(
        self,
        client,
        db_session,
        admin_user,
        client_user,
        products,
        warehouse_inventory,
        client_inventory,
        client_account,
        system_entities,
    ):
        # -- Setup: load warehouse with 10 water ------
        await load_stock(
            session=db_session,
            from_inv_id=(
                system_entities["virtual_vendor"].id
            ),
            to_inv_id=warehouse_inventory.id,
            product_id=products["water"].id,
            quantity=10,
            created_by_id=(
                system_entities["system_user"].id
            ),
        )

        headers = make_auth_headers(
            admin_user.id, Role.ADMIN
        )

        # -- Record pre-state for system accounts -----
        rev_before = (
            await db_session.execute(
                select(Account.balance).where(
                    Account.id
                    == system_entities[
                        "revenue_account"
                    ].id
                )
            )
        ).scalar_one()

        cash_before = (
            await db_session.execute(
                select(Account.balance).where(
                    Account.id
                    == system_entities[
                        "cash_account"
                    ].id
                )
            )
        ).scalar_one()

        # == Step 1: Create warehouse sale =============
        resp = await client.post(
            "/api/v1/backoffice/orders/warehouse-sale"
            f"?clientId={client_user.id}",
            json={
                "warehouse_id": str(
                    warehouse_inventory.id
                ),
                "items": [
                    {
                        "product_id": str(
                            products["water"].id
                        ),
                        "quantity": 2,
                    }
                ],
                "capitalize_missing_tara": True,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        order_data = resp.json()
        order_id = order_data["id"]
        assert (
            order_data["sale_type"]
            == "warehouse_pickup"
        )

        # == Step 2: Complete pickup ===================
        resp = await client.patch(
            "/api/v1/backoffice/orders/"
            f"{order_id}/complete-pickup",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "pickup_completed"

        # == Step 3: Assert balance state ==============
        # Known amounts: water.price=20_000, qty=2,
        # total=40_000

        # 3a. Warehouse water: 10 - 2 = 8
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id
                == warehouse_inventory.id,
                Balance.product_id
                == products["water"].id,
            )
        )
        assert result.scalar_one() == 8

        # 3b. Client water: 0 + 2 = 2
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id
                == client_inventory.id,
                Balance.product_id
                == products["water"].id,
            )
        )
        assert result.scalar_one() == 2

        # 3c. Warehouse tara: 0 + 2 returned = 2
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id
                == warehouse_inventory.id,
                Balance.product_id
                == products["tara"].id,
            )
        )
        assert result.scalar_one() == 2

        # 3d. Client tara: +2 capitalized - 2 returned
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id
                == client_inventory.id,
                Balance.product_id
                == products["tara"].id,
            )
        )
        assert result.scalar_one() == 0

        # 3e. Revenue account delta: -40_000
        rev_after = (
            await db_session.execute(
                select(Account.balance).where(
                    Account.id
                    == system_entities[
                        "revenue_account"
                    ].id
                )
            )
        ).scalar_one()
        assert rev_after - rev_before == -40_000

        # 3f. Cash account delta: +40_000
        cash_after = (
            await db_session.execute(
                select(Account.balance).where(
                    Account.id
                    == system_entities[
                        "cash_account"
                    ].id
                )
            )
        ).scalar_one()
        assert cash_after - cash_before == 40_000

        # 3g. Client account: net 0 (debt + payment)
        result = await db_session.execute(
            select(Account.balance).where(
                Account.id == client_account.id
            )
        )
        assert result.scalar_one() == 0
