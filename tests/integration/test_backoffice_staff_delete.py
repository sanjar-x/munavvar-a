from sqlalchemy import select

from src.infrastructure.database.models import Identity, User
from src.modules.users.enums import AuthProvider, Role
from tests.conftest import make_auth_headers


class TestBackofficeStaffDelete:
    async def test_delete_staff_user(
        self,
        client,
        db_session,
        admin_user,
        courier_user,
    ):
        headers = make_auth_headers(admin_user.id, Role.ADMIN)

        response = await client.delete(
            f"/api/v1/backoffice/users/{courier_user.id}",
            headers=headers,
        )

        assert response.status_code == 204, response.text

        deleted_user = (
            await db_session.execute(
                select(User).where(User.id == courier_user.id)
            )
        ).scalar_one_or_none()
        deleted_identity = (
            await db_session.execute(
                select(Identity).where(
                    Identity.user_id == courier_user.id,
                    Identity.provider == AuthProvider.LOCAL,
                )
            )
        ).scalar_one_or_none()

        assert deleted_user is None
        assert deleted_identity is None
