# src/api/v1/backoffice/orders.py
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.orders.dependencies import get_base_order_service
from src.modules.orders.enums import OrderStatus, PaymentMethod
from src.modules.orders.schemas import OrderCreate, OrderResponse
from src.modules.orders.services import BaseOrderService

orders_router = APIRouter()


@orders_router.get("/", response_model=list[OrderResponse])
async def search_orders(
    admin: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_READ])],
    base_order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    statuses: Annotated[
        list[OrderStatus] | None, Query(description="Фильтр по статусам")
    ] = None,
    payment_methods: Annotated[
        list[PaymentMethod] | None,
        Query(description="Фильтр по способам оплаты"),
    ] = None,
    courier_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    client_inventory_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_amount: Annotated[
        int | None, Query(ge=0, description="Минимальная сумма заказа")
    ] = None,
    max_amount: Annotated[
        int | None, Query(ge=0, description="Максимальная сумма заказа")
    ] = None,
):
    """Глобальный поиск заказов по фильтрам."""
    return await base_order_service.search_orders(
        skip=skip,
        limit=limit,
        statuses=statuses,
        payment_methods=payment_methods,
        courier_id=courier_id,
        client_id=client_id,
        client_inventory_id=client_inventory_id,
        date_from=date_from,
        date_to=date_to,
        min_amount=min_amount,
        max_amount=max_amount,
    )


@orders_router.post("/", response_model=OrderResponse)
async def create_order(
    clientId: Annotated[uuid.UUID, Query(description="ID клиента")],
    dto: OrderCreate,
    admin: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])],
    order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
):
    """Создание заказа администратором от лица клиента."""
    return await order_service.create_order(client_id=clientId, dto=dto)


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
    """Добавить товар в заказ (или увеличить количество)."""
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


@orders_router.patch("/{order_id}/assign", response_model=OrderResponse)
async def assign_courier(
    order_id: uuid.UUID,
    courier_id: Annotated[uuid.UUID, Body(embed=True)],
    admin: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])],
    base_order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
):
    """Назначить или сменить курьера на заказе."""
    return await base_order_service.assign_courier(
        order_id=order_id, courier_id=courier_id
    )


@orders_router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: uuid.UUID,
    new_status: Annotated[OrderStatus, Body(embed=True)],
    admin: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])],
    base_order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
):
    """Принудительно изменить статус заказа (ручная корректировка)."""
    return await base_order_service.update_status(
        order_id=order_id, new_status=new_status
    )


@orders_router.get("/client/{client_id}/history", response_model=list[OrderResponse])
async def get_client_history(
    client_id: uuid.UUID,
    admin: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_READ])],
    base_order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """Просмотр истории заказов конкретного клиента."""
    return await base_order_service.get_client_history(
        client_id=client_id, skip=skip, limit=limit
    )


@orders_router.get("/courier/{courier_id}/tasks", response_model=list[OrderResponse])
async def get_courier_tasks(
    courier_id: uuid.UUID,
    admin: Annotated[User, Security(get_current_user, scopes=[Scope.ORDERS_READ])],
    base_order_service: Annotated[BaseOrderService, Depends(get_base_order_service)],
):
    """Просмотр активных задач (заказов) конкретного курьера."""
    return await base_order_service.get_courier_tasks(courier_id=courier_id)
