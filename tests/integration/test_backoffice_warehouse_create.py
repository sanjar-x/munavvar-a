from src.modules.users.enums import Role
from tests.conftest import make_auth_headers


class TestBackofficeWarehouseCreate:
    async def test_create_warehouse_returns_responsible_user(
        self,
        client,
        admin_user,
    ):
        headers = make_auth_headers(admin_user.id, Role.ADMIN)

        response = await client.post(
            "/api/v1/backoffice/warehouses/",
            json={
                "user_id": str(admin_user.id),
                "name": "Test Warehouse Create",
            },
            headers=headers,
        )

        assert response.status_code == 201, response.text
        data = response.json()

        assert data["name"] == "Test Warehouse Create"
        assert data["type"] == "WAREHOUSE"
        assert data["is_active"] is True
        assert data["user"]["id"] == str(admin_user.id)
        assert data["user"]["phone"] == "+998901111111"
