from src.modules.inventory.enums import TransferType
from src.modules.users.enums import Role
from tests.conftest import make_auth_headers
from tests.integration.conftest import load_stock


class TestBackofficeTransferCreate:
    async def test_create_initial_balance_transfer_returns_items_with_product(
        self,
        client,
        admin_user,
        products,
        warehouse_inventory,
    ):
        headers = make_auth_headers(admin_user.id, Role.ADMIN)

        response = await client.post(
            "/api/v1/backoffice/transfers/",
            json={
                "type": TransferType.INITIAL_BALANCE,
                "to_id": str(warehouse_inventory.id),
                "items": [
                    {
                        "product_id": str(products["tara"].id),
                        "quantity": 2,
                    }
                ],
            },
            headers=headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["type"] == TransferType.INITIAL_BALANCE
        assert data["items"][0]["quantity"] == 2
        assert data["items"][0]["product"]["id"] == str(products["tara"].id)
        assert data["items"][0]["product"]["name"] == products["tara"].name

    async def test_create_courier_load_transfer_returns_items_with_product(
        self,
        client,
        db_session,
        admin_user,
        products,
        warehouse_inventory,
        courier_inventory,
        system_entities,
    ):
        headers = make_auth_headers(admin_user.id, Role.ADMIN)

        await load_stock(
            session=db_session,
            from_inv_id=system_entities["virtual_vendor"].id,
            to_inv_id=warehouse_inventory.id,
            product_id=products["water"].id,
            quantity=5,
            created_by_id=system_entities["system_user"].id,
        )

        response = await client.post(
            "/api/v1/backoffice/transfers/",
            json={
                "type": TransferType.COURIER_LOAD,
                "from_id": str(warehouse_inventory.id),
                "to_id": str(courier_inventory.id),
                "items": [
                    {
                        "product_id": str(products["water"].id),
                        "quantity": 1,
                    }
                ],
            },
            headers=headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["type"] == TransferType.COURIER_LOAD
        assert data["items"][0]["quantity"] == 1
        assert data["items"][0]["product"]["id"] == str(products["water"].id)
        assert data["items"][0]["product"]["name"] == products["water"].name
