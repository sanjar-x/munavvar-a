from src.infrastructure.database.models import Identity, User
from src.modules.users.enums import AuthProvider, Role
from tests.conftest import make_auth_headers


class TestOrderFsm:
    async def test_delivery_fsm_rejects_skipping_directly_to_delivered(
        self,
        client,
        admin_user,
        client_user,
        client_inventory,
        products,
    ):
        headers = make_auth_headers(admin_user.id, Role.ADMIN)

        response = await client.post(
            f"/api/v1/backoffice/orders/?clientId={client_user.id}",
            json={
                "items": [
                    {
                        "product_id": str(products["water"].id),
                        "quantity": 1,
                    }
                ],
                "payment_method": "cash",
                "client_inventory_id": str(client_inventory.id),
                "capitalize_missing_tara": True,
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        order_id = response.json()["id"]

        response = await client.patch(
            f"/api/v1/backoffice/orders/{order_id}/delivered",
            headers=headers,
        )

        assert response.status_code == 409, response.text
        body = response.json()["error"]
        assert body["code"] == "INVALID_ORDER_STATUS"
        assert body["details"]["current_status"] == "new"
        assert body["details"]["target_status"] == "delivered"

    async def test_delivery_fsm_rejects_reassign_after_in_transit(
        self,
        client,
        db_session,
        admin_user,
        courier_user,
        client_user,
        client_inventory,
        products,
    ):
        second_courier = User(
            username="Second Courier",
            role=Role.COURIER,
            is_active=True,
        )
        db_session.add(second_courier)
        await db_session.flush()
        db_session.add(
            Identity(
                user_id=second_courier.id,
                provider=AuthProvider.LOCAL,
                provider_identity_id="+998904444444",
                password_hash="fakehash",
            )
        )
        await db_session.flush()

        headers = make_auth_headers(admin_user.id, Role.ADMIN)

        response = await client.post(
            f"/api/v1/backoffice/orders/?clientId={client_user.id}",
            json={
                "items": [
                    {
                        "product_id": str(products["water"].id),
                        "quantity": 1,
                    }
                ],
                "payment_method": "cash",
                "client_inventory_id": str(client_inventory.id),
                "capitalize_missing_tara": True,
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        order_id = response.json()["id"]

        response = await client.patch(
            f"/api/v1/backoffice/orders/{order_id}/assign",
            json={"courierId": str(courier_user.id)},
            headers=headers,
        )
        assert response.status_code == 200, response.text

        response = await client.patch(
            f"/api/v1/backoffice/orders/{order_id}/in-transit",
            headers=headers,
        )
        assert response.status_code == 200, response.text

        response = await client.patch(
            f"/api/v1/backoffice/orders/{order_id}/assign",
            json={"courierId": str(second_courier.id)},
            headers=headers,
        )

        assert response.status_code == 409, response.text
        body = response.json()["error"]
        assert body["code"] == "COURIER_ASSIGNMENT_ERROR"
