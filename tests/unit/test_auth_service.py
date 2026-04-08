import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src.core.constants import WALKIN_USER_ID
from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.core.security.jwt import decode_access_token
from src.core.security.password import get_password_hash
from src.core.security.permissions import ROLE_SCOPES
from src.modules.auth.schemas import LocalLogin
from src.modules.auth.services import AuthService
from src.modules.users.enums import Role
from src.modules.users.services import UserService


class FakeUserService:
    def __init__(self, result: Any) -> None:
        self.result = result

    async def get_user_local_identity(self, identity_id: str) -> Any:
        return self.result


def make_user(role: Role, user_id: uuid.UUID | None = None):
    return SimpleNamespace(id=user_id or uuid.uuid4(), role=role)


def make_identity(password_hash: str):
    return SimpleNamespace(password_hash=password_hash)


@pytest.mark.asyncio
async def test_local_login_returns_staff_token_with_role_scopes():
    user = make_user(Role.ADMIN)
    identity = make_identity(await get_password_hash("secret-123"))
    service = AuthService(cast(UserService, FakeUserService((user, identity))))

    result = await service.local_login(
        LocalLogin(phone="+998901234567", password="secret-123")
    )

    payload = decode_access_token(result.access_token)

    assert result.token_type == "bearer"
    assert payload["sub"] == str(user.id)
    assert payload["scopes"] == ROLE_SCOPES[Role.ADMIN]


@pytest.mark.asyncio
async def test_local_login_rejects_client_accounts_even_with_valid_password():
    user = make_user(Role.CLIENT_B2C)
    identity = make_identity(await get_password_hash("secret-123"))
    service = AuthService(cast(UserService, FakeUserService((user, identity))))

    with pytest.raises(ForbiddenError) as exc:
        await service.local_login(
            LocalLogin(phone="+998901234567", password="secret-123")
        )

    assert exc.value.error_code == "STAFF_LOGIN_ONLY"


@pytest.mark.asyncio
async def test_courier_login_returns_courier_token_with_role_scopes():
    user = make_user(Role.COURIER)
    identity = make_identity(await get_password_hash("secret-123"))
    service = AuthService(cast(UserService, FakeUserService((user, identity))))

    result = await service.courier_login(
        LocalLogin(phone="+998901234567", password="secret-123")
    )

    payload = decode_access_token(result.access_token)

    assert result.token_type == "bearer"
    assert payload["sub"] == str(user.id)
    assert payload["scopes"] == ROLE_SCOPES[Role.COURIER]


@pytest.mark.asyncio
async def test_courier_login_rejects_non_courier_staff_accounts():
    user = make_user(Role.ADMIN)
    identity = make_identity(await get_password_hash("secret-123"))
    service = AuthService(cast(UserService, FakeUserService((user, identity))))

    with pytest.raises(ForbiddenError) as exc:
        await service.courier_login(
            LocalLogin(phone="+998901234567", password="secret-123")
        )

    assert exc.value.error_code == "COURIER_LOGIN_ONLY"


@pytest.mark.asyncio
async def test_local_login_masks_invalid_hash_as_invalid_credentials():
    user = make_user(Role.CLIENT_B2C, user_id=WALKIN_USER_ID)
    identity = make_identity("!disabled")
    service = AuthService(cast(UserService, FakeUserService((user, identity))))

    with pytest.raises(UnauthorizedError) as exc:
        await service.local_login(
            LocalLogin(phone="00000000002", password="anything")
        )

    assert exc.value.error_code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_client_login_rejects_staff_accounts():
    user = make_user(Role.COURIER)
    identity = make_identity(await get_password_hash("secret-123"))
    service = AuthService(cast(UserService, FakeUserService((user, identity))))

    with pytest.raises(ForbiddenError) as exc:
        await service.client_login(
            LocalLogin(phone="+998901234567", password="secret-123")
        )

    assert exc.value.error_code == "CLIENT_LOGIN_ONLY"


@pytest.mark.asyncio
async def test_client_login_rejects_walkin_account():
    user = make_user(Role.CLIENT_B2C, user_id=WALKIN_USER_ID)
    identity = make_identity(await get_password_hash("anything"))
    service = AuthService(cast(UserService, FakeUserService((user, identity))))

    with pytest.raises(ForbiddenError) as exc:
        await service.client_login(
            LocalLogin(phone="00000000002", password="anything")
        )

    assert exc.value.error_code == "WALKIN_LOGIN_FORBIDDEN"
