import uuid

from sqlalchemy import select

from src.core.security.jwt import decode_access_token
from src.core.security.password import verify_password
from src.core.security.permissions import ROLE_SCOPES
from src.infrastructure.database.models import Account, Identity, User
from src.modules.finances.enums import AccountType
from src.modules.users.enums import AuthProvider, Role
from tests.conftest import make_auth_headers


class TestBackofficeUserRoles:
    async def test_create_staff_user_and_login(
        self,
        client,
        db_session,
        admin_user,
    ):
        headers = make_auth_headers(admin_user.id, Role.ADMIN)

        response = await client.post(
            "/api/v1/backoffice/users/",
            json={
                "username": "Test Cashier",
                "phone": "+998904444444",
                "password": "secret-123",
                "role": "cashier",
            },
            headers=headers,
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["username"] == "Test Cashier"
        assert data["role"] == "cashier"
        assert data["phone"] == "+998904444444"

        user = (
            await db_session.execute(
                select(User).where(User.id == uuid.UUID(data["id"]))
            )
        ).scalar_one()
        identity = (
            await db_session.execute(
                select(Identity).where(
                    Identity.user_id == user.id,
                    Identity.provider == AuthProvider.LOCAL,
                )
            )
        ).scalar_one()

        assert user.role == Role.CASHIER
        assert verify_password("secret-123", identity.password_hash)

        login_response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "+998904444444",
                "password": "secret-123",
            },
        )

        assert login_response.status_code == 200, login_response.text
        payload = decode_access_token(login_response.json()["access_token"])
        assert payload["scopes"] == ROLE_SCOPES[Role.CASHIER]

    async def test_promote_passwordless_client_to_courier_requires_password(
        self,
        client,
        db_session,
        admin_user,
    ):
        candidate = User(
            username="Promotion Candidate",
            role=Role.CLIENT_B2C,
            is_active=True,
        )
        db_session.add(candidate)
        await db_session.flush()

        db_session.add(
            Identity(
                user_id=candidate.id,
                provider=AuthProvider.LOCAL,
                provider_identity_id="+998905555555",
                password_hash=None,
            )
        )
        await db_session.flush()

        headers = make_auth_headers(admin_user.id, Role.ADMIN)

        response = await client.patch(
            f"/api/v1/backoffice/users/{candidate.id}",
            json={"role": "courier"},
            headers=headers,
        )

        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "STAFF_PASSWORD_REQUIRED"

        response = await client.patch(
            f"/api/v1/backoffice/users/{candidate.id}",
            json={
                "role": "courier",
                "password": "courier-pass",
            },
            headers=headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["role"] == "courier"
        assert data["phone"] == "+998905555555"

        identity = (
            await db_session.execute(
                select(Identity).where(
                    Identity.user_id == candidate.id,
                    Identity.provider == AuthProvider.LOCAL,
                )
            )
        ).scalar_one()
        account = (
            await db_session.execute(
                select(Account).where(
                    Account.user_id == candidate.id,
                    Account.type == AccountType.COURIER,
                )
            )
        ).scalar_one()

        assert verify_password("courier-pass", identity.password_hash)
        assert account.name == "Касса курьера: Promotion Candidate"

        login_response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "+998905555555",
                "password": "courier-pass",
            },
        )

        assert login_response.status_code == 200, login_response.text
        payload = decode_access_token(login_response.json()["access_token"])
        assert payload["scopes"] == ROLE_SCOPES[Role.COURIER]
