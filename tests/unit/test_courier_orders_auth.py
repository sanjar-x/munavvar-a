import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.server import create_app
from src.core.exceptions import NotFoundError
from src.core.security.jwt import create_access_token
from src.core.security.permissions import Scope
from src.modules.orders.dependencies import get_base_order_service
from src.modules.users.dependencies import get_user_service
from src.modules.users.enums import Role


class FakeUserService:
    async def get(self, id: uuid.UUID):
        return SimpleNamespace(
            id=id,
            role=Role.COURIER,
            is_active=True,
        )


class FakeOrderService:
    async def update_status(self, *args, **kwargs):
        raise NotFoundError(
            message="Stub order lookup failed",
            error_code="ORDER_STUB_NOT_FOUND",
        )


def make_auth_headers(user_id: uuid.UUID, scopes: list[str]) -> dict[str, str]:
    token = create_access_token(
        payload_data={
            "sub": str(user_id),
            "scopes": scopes,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def courier_test_client():
    app = create_app()
    app.dependency_overrides[get_user_service] = lambda: FakeUserService()
    app.dependency_overrides[get_base_order_service] = (
        lambda: FakeOrderService()
    )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "method", "payload"),
    [
        (
            "/api/v1/courier/orders/{order_id}/deliver",
            "post",
            {},
        ),
        (
            "/api/v1/courier/orders/{order_id}/status",
            "patch",
            {"new_status": "assigned"},
        ),
    ],
)
async def test_courier_mutation_routes_accept_orders_deliver_scope(
    courier_test_client: AsyncClient,
    path: str,
    method: str,
    payload: dict,
):
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    headers = make_auth_headers(user_id, [Scope.ORDERS_DELIVER])

    response = await getattr(courier_test_client, method)(
        path.format(order_id=order_id),
        json=payload,
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORDER_STUB_NOT_FOUND"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "method", "payload"),
    [
        (
            "/api/v1/courier/orders/{order_id}/deliver",
            "post",
            {},
        ),
        (
            "/api/v1/courier/orders/{order_id}/status",
            "patch",
            {"new_status": "assigned"},
        ),
    ],
)
async def test_courier_mutation_routes_reject_missing_orders_deliver_scope(
    courier_test_client: AsyncClient,
    path: str,
    method: str,
    payload: dict,
):
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    headers = make_auth_headers(user_id, [Scope.ORDERS_READ])

    response = await getattr(courier_test_client, method)(
        path.format(order_id=order_id),
        json=payload,
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
