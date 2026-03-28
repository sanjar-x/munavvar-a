"""TEST-03: Walk-in sale characterization test.

Covers the anonymous walk-in sale flow:
  create warehouse sale (no clientId) -> complete pickup
and verifies HTTP responses, balance state, AND the
LOSS_WRITE_OFF cleanup that clears the walk-in
user's inventory after pickup.
"""
from sqlalchemy import select

from src.infrastructure.database.models import Account, Balance
from src.modules.users.enums import Role
from tests.conftest import make_auth_headers
from tests.integration.conftest import load_stock


class TestWalkinSale:
    async def test_walkin_sale_with_loss_writeoff(
        self,
        client,
        db_session,
        admin_user,
        products,
        warehouse_inventory,
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

        walkin_inv = system_entities["walkin_inventory"]
        walkin_acct = system_entities["walkin_account"]
        virtual_loss = system_entities["virtual_loss"]

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

        walkin_bal_before = (
            await db_session.execute(
                select(Account.balance).where(
                    Account.id == walkin_acct.id
                )
            )
        ).scalar_one()

        # == Step 1: Create anonymous warehouse sale ===
        # No clientId param -> defaults to WALKIN_USER_ID
        resp = await client.post(
            "/api/v1/backoffice/orders"
            "/warehouse-sale",
            json={
                "warehouse_id": str(
                    warehouse_inventory.id
                ),
                "items": [
                    {
                        "product_id": str(
                            products["water"].id
                        ),
                        "quantity": 1,
                    }
                ],
                "capitalize_missing_tara": True,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        order_data = resp.json()
        order_id = order_data["id"]

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
        # Known amounts: water.price=20_000, qty=1,
        # total=20_000

        # 3a. Warehouse water: 10 - 1 = 9
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id
                == warehouse_inventory.id,
                Balance.product_id
                == products["water"].id,
            )
        )
        assert result.scalar_one() == 9

        # 3b. Walk-in water: +1 sale - 1 writeoff = 0
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id == walkin_inv.id,
                Balance.product_id
                == products["water"].id,
            )
        )
        assert result.scalar_one() == 0

        # 3c. Walk-in tara: +1 capitalized - 1 returned
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id == walkin_inv.id,
                Balance.product_id
                == products["tara"].id,
            )
        )
        assert result.scalar_one() == 0

        # 3d. Warehouse tara: +1 returned
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id
                == warehouse_inventory.id,
                Balance.product_id
                == products["tara"].id,
            )
        )
        assert result.scalar_one() == 1

        # 3e. Virtual loss water: increased by 1
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id
                == virtual_loss.id,
                Balance.product_id
                == products["water"].id,
            )
        )
        assert result.scalar_one() == 1

        # 3f. Revenue account delta: -20_000
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
        assert rev_after - rev_before == -20_000

        # 3g. Cash account delta: +20_000
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
        assert cash_after - cash_before == 20_000

        # 3h. Walk-in account: net 0 (debt + payment)
        walkin_bal_after = (
            await db_session.execute(
                select(Account.balance).where(
                    Account.id == walkin_acct.id
                )
            )
        ).scalar_one()
        assert (
            walkin_bal_after - walkin_bal_before == 0
        )
