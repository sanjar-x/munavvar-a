import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.server import create_app
from src.core.security.jwt import create_access_token
from src.core.security.permissions import Scope
from src.modules.auth.dependencies import get_auth_service
from src.modules.auth.schemas import TokenResponse
from src.modules.orders.dependencies import get_base_order_service
from src.modules.users.dependencies import get_user_service
from src.modules.users.enums import Role


def make_auth_headers(user_id: uuid.UUID, scopes: list[str]) -> dict[str, str]:
    token = create_access_token(
        payload_data={
            "sub": str(user_id),
            "scopes": scopes,
        }
    )
    return {"Authorization": f"Bearer {token}"}


class FakeUserService:
    def __init__(self, role: Role):
        self.role = role

    async def get(self, id: uuid.UUID):
        return SimpleNamespace(
            id=id,
            role=self.role,
            is_active=True,
        )


class FakeCourierOrderService:
    def __init__(self):
        self.last_courier_id: uuid.UUID | None = None

    async def get_courier_tasks(self, courier_id: uuid.UUID):
        self.last_courier_id = courier_id
        return []


class FakeAuthService:
    def __init__(self):
        self.last_phone: str | None = None
        self.last_password: str | None = None

    async def courier_login(self, data):
        self.last_phone = data.phone
        self.last_password = data.password
        return TokenResponse(access_token="stub-token", token_type="bearer")


@pytest.mark.asyncio
async def test_courier_login_route_uses_phone_and_password_payload():
    app = create_app()
    auth_service = FakeAuthService()
    app.dependency_overrides[get_auth_service] = lambda: auth_service

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/courier/login",
            json={
                "phone": "+998901234567",
                "password": "secret-123",
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "stub-token",
        "token_type": "bearer",
    }
    assert auth_service.last_phone == "+998901234567"
    assert auth_service.last_password == "secret-123"


@pytest.mark.asyncio
async def test_courier_orders_list_returns_tasks_for_current_courier():
    user_id = uuid.uuid4()
    app = create_app()
    order_service = FakeCourierOrderService()
    app.dependency_overrides[get_user_service] = lambda: FakeUserService(
        Role.COURIER
    )
    app.dependency_overrides[get_base_order_service] = lambda: order_service

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/courier/orders/",
            headers=make_auth_headers(user_id, [Scope.ORDERS_READ]),
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == []
    assert order_service.last_courier_id == user_id


@pytest.mark.asyncio
async def test_courier_orders_list_rejects_non_courier_role():
    user_id = uuid.uuid4()
    app = create_app()
    app.dependency_overrides[get_user_service] = lambda: FakeUserService(
        Role.ADMIN
    )
    app.dependency_overrides[get_base_order_service] = (
        lambda: FakeCourierOrderService()
    )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/courier/orders/",
            headers=make_auth_headers(user_id, [Scope.ORDERS_READ]),
        )

    app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "COURIER_ONLY"
