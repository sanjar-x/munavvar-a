from fastapi import status

from src.infrastructure.database.models import Identity, User
from src.modules.users.enums import AuthProvider, Role
from tests.conftest import make_auth_headers


class TestBackofficeStaffList:
    async def test_get_staff_users_filters_by_roles(
        self,
        client,
        db_session,
        admin_user,
        courier_user,
        client_user,
    ):
        accountant_user = User(
            username="Test Accountant",
            role=Role.ACCOUNTANT,
            is_active=True,
        )
        db_session.add(accountant_user)
        await db_session.flush()

        db_session.add(
            Identity(
                user_id=accountant_user.id,
                provider=AuthProvider.LOCAL,
                provider_identity_id="+998906666666",
                password_hash="fakehash",
            )
        )
        await db_session.flush()

        headers = make_auth_headers(admin_user.id, Role.ADMIN)

        response = await client.get(
            "/api/v1/backoffice/users",
            params=[("roles", "courier"), ("roles", "accountant")],
            headers=headers,
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        data = response.json()

        assert data["total_count"] == 2

        roles = {user["role"] for user in data["users"]}
        phones = {user["phone"] for user in data["users"]}
        ids = {user["id"] for user in data["users"]}

        assert roles == {"courier", "accountant"}
        assert phones == {"+998902222222", "+998906666666"}
        assert str(client_user.id) not in ids
        assert str(admin_user.id) not in ids
