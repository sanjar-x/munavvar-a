# src/api/v1/client/orders.py
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.orders.dependencies import get_base_order_service
from src.modules.orders.schemas import (
    OrderCreate,
    OrderResponse,
    TaraCheckRequest,
    TaraCheckResponse,
)
from src.modules.orders.services import BaseOrderService

orders_router = APIRouter()


@orders_router.post("/check-tara", response_model=TaraCheckResponse)
async def check_tara_availability(
    dto: TaraCheckRequest,
    client: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_READ])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Предварительная проверка доступности тары перед оформлением заказа."""
    return await base_order_service.check_tara_availability(dto=dto)


@orders_router.post("/", response_model=OrderResponse, status_code=201)
async def create_order(
    dto: OrderCreate,
    client: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_CREATE])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Создание"""
    return await base_order_service.create_order(client_id=client.id, dto=dto)


@orders_router.get("/{order_id}", response_model=OrderResponse)
async def get_order_details(
    order_id: uuid.UUID,
    client: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_READ])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Детальная информация по конкретному заказу."""
    return await base_order_service.get_order_with_details(order_id=order_id)


@orders_router.post("/{order_id}/items", response_model=OrderResponse)
async def add_product_to_order(
    order_id: uuid.UUID,
    product_id: Annotated[uuid.UUID, Body(embed=True)],
    quantity: Annotated[int, Body(embed=True, gt=0)],
    client: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_CREATE])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    return await base_order_service.add_product_to_order(
        order_id=order_id,
        product_id=product_id,
        quantity=quantity,
        requesting_user_id=client.id,
    )


@orders_router.delete(
    "/{order_id}/items/{product_id}", response_model=OrderResponse
)
async def remove_product_from_order(
    order_id: uuid.UUID,
    product_id: uuid.UUID,
    client: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_CREATE])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Полностью удалить позицию товара из заказа."""
    return await base_order_service.remove_product_from_order(
        order_id=order_id,
        product_id=product_id,
        requesting_user_id=client.id,
    )


@orders_router.get("/history", response_model=list[OrderResponse])
async def get_tasks(
    client: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_READ])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    return await base_order_service.get_client_history(client_id=client.id)
