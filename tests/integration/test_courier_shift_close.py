"""TEST-04: Courier shift close characterization test.

Covers end-of-day reconciliation:
  load courier -> close shift -> verify balances
and verifies HTTP response AND final balance state
(inventory_balances + accounts.balance + inventory
deactivation).
"""

import pytest
from sqlalchemy import select

from src.infrastructure.database.models import (
    Account,
    Balance,
    Inventory,
    User,
)
from src.modules.users.enums import Role
from tests.conftest import make_auth_headers
from tests.integration.conftest import (
    credit_account,
    load_stock,
)


class TestCourierShiftClose:
    @pytest.mark.skip(
        reason=(
            "Фича /backoffice/shifts/close не реализована: "
            "исходники src/api/v1/backoffice/shifts.py и "
            "src/modules/inventory/shift_service.py удалены, "
            "остались только .pyc. См. SENIOR_CODE_REVIEW FAIL-2."
        )
    )
    async def test_shift_close_returns_stock_and_collects_cash(
        self,
        client,
        db_session,
        courier_user,
        products,
        warehouse_inventory,
        courier_inventory,
        courier_account,
        system_entities,
    ):
        # -- Setup: storekeeper user (INVENTORY_WRITE) --
        storekeeper = User(
            username="Test Storekeeper",
            role=Role.STOREKEEPER,
            is_active=True,
        )
        db_session.add(storekeeper)
        await db_session.flush()

        headers = make_auth_headers(storekeeper.id, Role.STOREKEEPER)

        # -- Setup: load courier with 5 water + 3 tara -
        await load_stock(
            session=db_session,
            from_inv_id=(system_entities["virtual_vendor"].id),
            to_inv_id=courier_inventory.id,
            product_id=products["water"].id,
            quantity=5,
            created_by_id=(system_entities["system_user"].id),
        )
        await load_stock(
            session=db_session,
            from_inv_id=(system_entities["virtual_vendor"].id),
            to_inv_id=courier_inventory.id,
            product_id=products["tara"].id,
            quantity=3,
            created_by_id=(system_entities["system_user"].id),
        )

        # -- Setup: credit courier account with 100_000 -
        await credit_account(
            session=db_session,
            from_account_id=(system_entities["revenue_account"].id),
            to_account_id=courier_account.id,
            amount=100_000,
            created_by_id=(system_entities["system_user"].id),
        )

        # -- Record pre-state --------------------------
        wh_water_before = (
            await db_session.execute(
                select(Balance.quantity).where(
                    Balance.inventory_id == warehouse_inventory.id,
                    Balance.product_id == products["water"].id,
                )
            )
        ).scalar_one_or_none() or 0

        wh_tara_before = (
            await db_session.execute(
                select(Balance.quantity).where(
                    Balance.inventory_id == warehouse_inventory.id,
                    Balance.product_id == products["tara"].id,
                )
            )
        ).scalar_one_or_none() or 0

        cash_before = (
            await db_session.execute(
                select(Account.balance).where(
                    Account.id == system_entities["cash_account"].id
                )
            )
        ).scalar_one()

        # == Step 1: Close shift ========================
        resp = await client.post(
            "/api/v1/backoffice/shifts/close",
            json={
                "courier_id": str(courier_user.id),
                "returned_inventory": [
                    {
                        "product_id": str(products["water"].id),
                        "quantity": 5,
                    },
                    {
                        "product_id": str(products["tara"].id),
                        "quantity": 3,
                    },
                ],
                "cash_collected": 100_000,
            },
            headers=headers,
        )
        assert resp.status_code == 200, (
            f"status={resp.status_code} body={resp.text}"
        )

        # == Step 2: Assert balance state ===============

        # 2a. Courier water: 5 - 5 = 0
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id == courier_inventory.id,
                Balance.product_id == products["water"].id,
            )
        )
        assert result.scalar_one() == 0

        # 2b. Courier tara: 3 - 3 = 0
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id == courier_inventory.id,
                Balance.product_id == products["tara"].id,
            )
        )
        assert result.scalar_one() == 0

        # 2c. Warehouse water: pre + 5
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id == warehouse_inventory.id,
                Balance.product_id == products["water"].id,
            )
        )
        assert result.scalar_one() == (wh_water_before + 5)

        # 2d. Warehouse tara: pre + 3
        result = await db_session.execute(
            select(Balance.quantity).where(
                Balance.inventory_id == warehouse_inventory.id,
                Balance.product_id == products["tara"].id,
            )
        )
        assert result.scalar_one() == (wh_tara_before + 3)

        # 2e. Courier account: 100_000 - 100_000 = 0
        result = await db_session.execute(
            select(Account.balance).where(Account.id == courier_account.id)
        )
        assert result.scalar_one() == 0

        # 2f. Cash account: pre + 100_000
        result = await db_session.execute(
            select(Account.balance).where(
                Account.id == system_entities["cash_account"].id
            )
        )
        assert result.scalar_one() == cash_before + 100_000

        # 2g. Courier inventory deactivated
        result = await db_session.execute(
            select(Inventory.is_active).where(
                Inventory.id == courier_inventory.id
            )
        )
        assert result.scalar_one() is False
