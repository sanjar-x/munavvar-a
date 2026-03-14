# src/api/v1/coureie/orders.py
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.orders.dependencies import get_base_order_service
from src.modules.orders.enums import OrderStatus
from src.modules.orders.schemas import OrderCreate, OrderDeliverRequest, OrderResponse
from src.modules.orders.services import BaseOrderService

orders_router = APIRouter()


@orders_router.post("/", response_model=OrderResponse)
async def create_order(
    client_id: Annotated[uuid.UUID, Query(description="ID клиента")],
    dto: OrderCreate,
    admin: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])],
    base_order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
):
    return await base_order_service.create_order(client_id=client_id, dto=dto)


@orders_router.get("/{order_id}", response_model=OrderResponse)
async def get_order_details(
    order_id: uuid.UUID,
    admin: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_READ])],
    base_order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
):
    """Детальная информация по конкретному заказу."""
    return await base_order_service.get_order_with_details(order_id=order_id)


@orders_router.post("/{order_id}/items", response_model=OrderResponse)
async def add_product_to_order(
    order_id: uuid.UUID,
    product_id: Annotated[uuid.UUID, Body(embed=True)],
    quantity: Annotated[int, Body(embed=True, gt=0)],
    admin: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])],
    base_order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
):
    return await base_order_service.add_product_to_order(
        order_id=order_id, product_id=product_id, quantity=quantity
    )


@orders_router.delete("/{order_id}/items/{product_id}", response_model=OrderResponse)
async def remove_product_from_order(
    order_id: uuid.UUID,
    product_id: uuid.UUID,
    admin: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])],
    base_order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
):
    """Полностью удалить позицию товара из заказа."""
    return await base_order_service.remove_product_from_order(
        order_id=order_id, product_id=product_id
    )


@orders_router.post("/{order_id}/deliver", response_model=OrderResponse)
async def deliver_order(
    order_id: uuid.UUID,
    dto: OrderDeliverRequest,
    courier: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])],
    base_order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
):
    """Завершение доставки курьером (поддерживает частичный возврат/отказ)."""
    return await base_order_service.update_status(
        order_id=order_id,
        new_status=OrderStatus.DELIVERED,
        actual_items=dto.actual_items,
    )


@orders_router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: uuid.UUID,
    new_status: Annotated[OrderStatus, Body(embed=True)],
    courier: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])],
    base_order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
):
    return await base_order_service.update_status(
        order_id=order_id, new_status=new_status
    )


@orders_router.get("/tasks", response_model=list[OrderResponse])
async def get_tasks(
    courier: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_READ])],
    base_order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
):
    """Просмотр активных задач (заказов) конкретного курьера."""
    return await base_order_service.get_courier_tasks(courier_id=courier.id)
