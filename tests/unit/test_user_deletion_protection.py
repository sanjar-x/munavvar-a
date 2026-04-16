"""Системные пользователи (SYSTEM, Walk-in) защищены от удаления."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.constants import (
    PROTECTED_USER_IDS,
    SYSTEM_USER_ID,
    WALKIN_USER_ID,
)
from src.modules.users.exceptions import (
    SystemUserDeletionForbiddenError,
)
from src.modules.users.services import UserService


def _make_service() -> UserService:
    uow = AsyncMock()
    return UserService(uow=uow)


@pytest.mark.parametrize(
    "user_id",
    [
        pytest.param(SYSTEM_USER_ID, id="system"),
        pytest.param(WALKIN_USER_ID, id="walkin"),
    ],
)
async def test_archive_rejects_protected_user(
    user_id: uuid.UUID,
):
    service = _make_service()
    with pytest.raises(SystemUserDeletionForbiddenError) as exc:
        await service.archive(user_id)
    assert exc.value.error_code == "SYSTEM_USER_DELETION_FORBIDDEN"
    assert exc.value.details["user_id"] == str(user_id)


@pytest.mark.parametrize(
    "user_id",
    [
        pytest.param(SYSTEM_USER_ID, id="system"),
        pytest.param(WALKIN_USER_ID, id="walkin"),
    ],
)
async def test_delete_rejects_protected_user(
    user_id: uuid.UUID,
):
    service = _make_service()
    with pytest.raises(SystemUserDeletionForbiddenError) as exc:
        await service.delete(user_id)
    assert exc.value.error_code == "SYSTEM_USER_DELETION_FORBIDDEN"


@pytest.mark.parametrize(
    "user_id",
    [
        pytest.param(SYSTEM_USER_ID, id="system"),
        pytest.param(WALKIN_USER_ID, id="walkin"),
    ],
)
async def test_delete_staff_rejects_protected_user(
    user_id: uuid.UUID,
):
    service = _make_service()
    with pytest.raises(SystemUserDeletionForbiddenError) as exc:
        await service.delete_staff(user_id)
    assert exc.value.error_code == "SYSTEM_USER_DELETION_FORBIDDEN"


@pytest.mark.parametrize(
    "user_id",
    [
        pytest.param(SYSTEM_USER_ID, id="system"),
        pytest.param(WALKIN_USER_ID, id="walkin"),
    ],
)
async def test_update_deactivation_rejects_protected_user(
    user_id: uuid.UUID,
):
    service = _make_service()
    schema = MagicMock()
    schema.model_dump.return_value = {"is_active": False}
    with pytest.raises(SystemUserDeletionForbiddenError) as exc:
        await service.update(user_id, schema)
    assert exc.value.error_code == "SYSTEM_USER_DELETION_FORBIDDEN"


async def test_archive_allows_regular_user():
    service = _make_service()
    service.uow.__aenter__ = AsyncMock(return_value=service.uow)
    service.uow.__aexit__ = AsyncMock(return_value=False)
    service.uow.users.archive = AsyncMock(return_value=True)
    service.uow.commit = AsyncMock()

    regular_id = uuid.uuid4()
    assert regular_id not in PROTECTED_USER_IDS

    result = await service.archive(regular_id)
    assert result is True


async def test_constants_contain_walkin_and_system():
    assert SYSTEM_USER_ID in PROTECTED_USER_IDS
    assert WALKIN_USER_ID in PROTECTED_USER_IDS
