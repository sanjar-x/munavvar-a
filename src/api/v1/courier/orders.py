import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_courier
from src.modules.orders.dependencies import get_base_order_service
from src.modules.orders.enums import OrderStatus
from src.modules.orders.schemas import OrderDeliverRequest, OrderResponse
from src.modules.orders.services import BaseOrderService

orders_router = APIRouter()


@orders_router.get("/", response_model=list[OrderResponse])
@orders_router.get(
    "/tasks",
    response_model=list[OrderResponse],
    include_in_schema=False,
)
async def get_tasks(
    courier: Annotated[
        User, Security(get_current_courier, scopes=[Scope.ORDERS_READ])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Список активных заказов текущего курьера."""
    return await base_order_service.get_courier_tasks(courier_id=courier.id)


@orders_router.get("/{order_id}", response_model=OrderResponse)
async def get_order_details(
    order_id: uuid.UUID,
    courier: Annotated[
        User, Security(get_current_courier, scopes=[Scope.ORDERS_READ])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Детальная информация по заказу текущего курьера."""
    return await base_order_service.get_order_with_details(
        order_id=order_id,
        requesting_user_id=courier.id,
    )


@orders_router.post("/{order_id}/deliver", response_model=OrderResponse)
async def deliver_order(
    order_id: uuid.UUID,
    dto: OrderDeliverRequest,
    courier: Annotated[
        User, Security(get_current_courier, scopes=[Scope.ORDERS_DELIVER])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Завершение доставки курьером."""
    return await base_order_service.update_status(
        order_id=order_id,
        new_status=OrderStatus.DELIVERED,
        actual_items=dto.actual_items,
        requesting_user_id=courier.id,
    )


@orders_router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: uuid.UUID,
    new_status: Annotated[OrderStatus, Body(embed=True)],
    courier: Annotated[
        User, Security(get_current_courier, scopes=[Scope.ORDERS_DELIVER])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Смена статуса заказа текущим курьером."""
    return await base_order_service.update_status(
        order_id=order_id,
        new_status=new_status,
        requesting_user_id=courier.id,
    )
