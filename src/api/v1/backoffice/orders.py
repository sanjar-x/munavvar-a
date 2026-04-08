# src/api/v1/backoffice/orders.py
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, Security

from src.core.constants import WALKIN_USER_ID
from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.dependencies import get_capitalize_tara_service
from src.modules.inventory.schemas import (
    CapitalizeTaraItem,
)
from src.modules.inventory.services import CapitalizeTaraService
from src.modules.orders.dependencies import get_base_order_service
from src.modules.orders.enums import OrderStatus, PaymentMethod, SaleType
from src.modules.orders.schemas import (
    OrderCreate,
    OrderDeliverRequest,
    OrderResponse,
    OrdersResponse,
    TaraCheckRequest,
    TaraCheckResponse,
    WarehouseSaleCapitalizeTaraRequest,
    WarehouseSaleCreate,
)
from src.modules.orders.services import BaseOrderService
from src.modules.users.enums import Role

orders_router = APIRouter()


async def _update_backoffice_order_status(
    *,
    order_id: uuid.UUID,
    new_status: OrderStatus,
    base_order_service: BaseOrderService,
    actual_items=None,
):
    return await base_order_service.update_status(
        order_id=order_id,
        new_status=new_status,
        actual_items=actual_items,
    )


@orders_router.get("/", response_model=OrdersResponse)
async def search_orders(
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_READ])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    statuses: Annotated[
        list[OrderStatus] | None, Query(description="Фильтр по статусам")
    ] = None,
    payment_methods: Annotated[
        list[PaymentMethod] | None,
        Query(alias="paymentMethods", description="Фильтр по способам оплаты"),
    ] = None,
    courier_id: Annotated[uuid.UUID | None, Query(alias="courierId")] = None,
    client_id: Annotated[uuid.UUID | None, Query(alias="clientId")] = None,
    client_inventory_id: Annotated[
        uuid.UUID | None, Query(alias="clientInventoryId")
    ] = None,
    date_from: Annotated[datetime | None, Query(alias="dateFrom")] = None,
    date_to: Annotated[datetime | None, Query(alias="dateTo")] = None,
    min_amount: Annotated[
        int | None,
        Query(alias="minAmount", ge=0, description="Минимальная сумма заказа"),
    ] = None,
    max_amount: Annotated[
        int | None,
        Query(
            alias="maxAmount", ge=0, description="Максимальная сумма заказа"
        ),
    ] = None,
    sale_type: Annotated[
        SaleType | None,
        Query(alias="saleType", description="Фильтр по типу продажи"),
    ] = None,
):
    """Глобальный поиск заказов по фильтрам."""
    orders, total = await base_order_service.search_orders(
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
        sale_type=sale_type,
    )
    return OrdersResponse(
        total_count=total,
        orders=[OrderResponse.model_validate(order) for order in orders],
    )


@orders_router.post("/check-tara", response_model=TaraCheckResponse)
async def check_tara_availability(
    dto: TaraCheckRequest,
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_READ])
    ],
    order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Предварительная проверка доступности тары перед оформлением заказа."""
    return await order_service.check_tara_availability(dto=dto)


@orders_router.post("/", status_code=201, response_model=OrderResponse)
async def create_order(
    client_id: Annotated[
        uuid.UUID, Query(alias="clientId", description="ID клиента")
    ],
    dto: OrderCreate,
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_CREATE])
    ],
    order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
    client_role: Annotated[
        Role,
        Query(
            alias="clientRole",
            description=(
                "Роль клиента (client_b2b/client_b2c). "
                "Для B2B с CONTRACT обязательно"
            ),
        ),
    ] = Role.CLIENT_B2C,
):
    """Создание заказа администратором от лица клиента."""
    return await order_service.create_order(
        client_id=client_id,
        dto=dto,
        client_role=client_role,
    )


@orders_router.post(
    "/warehouse-sale", status_code=201, response_model=OrderResponse
)
async def create_warehouse_sale(
    dto: WarehouseSaleCreate,
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_CREATE])
    ],
    order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
    client_id: Annotated[
        uuid.UUID | None,
        Query(
            alias="clientId",
            description="ID клиента (если не передан — анонимная продажа)",
        ),
    ] = None,
):
    """Создание заказа на самовывоз со склада."""
    return await order_service.create_warehouse_sale(
        dto=dto, client_id=client_id, created_by_id=admin.id
    )


@orders_router.post("/warehouse-sale/capitalize-tara", status_code=201)
async def capitalize_tara_for_sale(
    dto: WarehouseSaleCapitalizeTaraRequest,
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])
    ],
    capitalize_service: Annotated[
        CapitalizeTaraService, Depends(get_capitalize_tara_service)
    ],
    client_id: Annotated[
        uuid.UUID | None,
        Query(
            alias="clientId",
            description="ID клиента (если не передан — walk-in)",
        ),
    ] = None,
):
    """Оприходование тары, принесённой покупателем
    на склад перед самовывозом."""
    effective_client_id = client_id or WALKIN_USER_ID

    return await capitalize_service.capitalize_tara_for_client(
        client_id=effective_client_id,
        items=[
            CapitalizeTaraItem(
                product_id=item.product_id, quantity=item.quantity
            )
            for item in dto.items
        ],
        created_by_id=admin.id,
    )


@orders_router.patch(
    "/{orderId}/complete-pickup", response_model=OrderResponse
)
async def complete_pickup(
    order_id: Annotated[uuid.UUID, Path(alias="orderId")],
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])
    ],
    order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Подтверждение выдачи товара со склада (NEW → PICKUP_COMPLETED)."""
    return await order_service.complete_pickup(
        order_id=order_id, completed_by_id=admin.id
    )


@orders_router.get("/{orderId}", response_model=OrderResponse)
async def get_order_details(
    order_id: Annotated[uuid.UUID, Path(alias="orderId")],
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_READ])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Детальная информация по конкретному заказу."""
    return await base_order_service.get_order_with_details(order_id=order_id)


@orders_router.post("/{orderId}/items", response_model=OrderResponse)
async def add_product_to_order(
    order_id: Annotated[uuid.UUID, Path(alias="orderId")],
    product_id: Annotated[uuid.UUID, Body(alias="productId", embed=True)],
    quantity: Annotated[int, Body(embed=True, gt=0)],
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Добавить товар в заказ (или увеличить количество)."""
    return await base_order_service.add_product_to_order(
        order_id=order_id, product_id=product_id, quantity=quantity
    )


@orders_router.delete(
    "/{orderId}/items/{productId}", response_model=OrderResponse
)
async def remove_product_from_order(
    order_id: Annotated[uuid.UUID, Path(alias="orderId")],
    product_id: Annotated[uuid.UUID, Path(alias="productId")],
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Полностью удалить позицию товара из заказа."""
    return await base_order_service.remove_product_from_order(
        order_id=order_id, product_id=product_id
    )


@orders_router.patch("/{orderId}/assign", response_model=OrderResponse)
async def assign_courier(
    order_id: Annotated[uuid.UUID, Path(alias="orderId")],
    courier_id: Annotated[uuid.UUID, Body(alias="courierId", embed=True)],
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Назначить или сменить курьера на заказе."""
    return await base_order_service.assign_courier(
        order_id=order_id, courier_id=courier_id
    )


@orders_router.patch("/{orderId}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: Annotated[uuid.UUID, Path(alias="orderId")],
    new_status: Annotated[OrderStatus, Body(alias="newStatus", embed=True)],
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Изменить статус заказа в рамках допустимых FSM-переходов."""
    return await _update_backoffice_order_status(
        order_id=order_id,
        new_status=new_status,
        base_order_service=base_order_service,
    )


@orders_router.patch("/{orderId}/in-transit", response_model=OrderResponse)
async def mark_order_in_transit(
    order_id: Annotated[uuid.UUID, Path(alias="orderId")],
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Перевести заказ в статус IN_TRANSIT."""
    return await _update_backoffice_order_status(
        order_id=order_id,
        new_status=OrderStatus.IN_TRANSIT,
        base_order_service=base_order_service,
    )


@orders_router.patch("/{orderId}/arrived", response_model=OrderResponse)
async def mark_order_arrived(
    order_id: Annotated[uuid.UUID, Path(alias="orderId")],
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Перевести заказ в статус ARRIVED."""
    return await _update_backoffice_order_status(
        order_id=order_id,
        new_status=OrderStatus.ARRIVED,
        base_order_service=base_order_service,
    )


@orders_router.patch("/{orderId}/delivered", response_model=OrderResponse)
async def mark_order_delivered(
    order_id: Annotated[uuid.UUID, Path(alias="orderId")],
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_EDIT])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
    dto: OrderDeliverRequest | None = None,
):
    """Перевести заказ в статус DELIVERED."""
    return await _update_backoffice_order_status(
        order_id=order_id,
        new_status=OrderStatus.DELIVERED,
        actual_items=dto.actual_items if dto else None,
        base_order_service=base_order_service,
    )


@orders_router.get(
    "/client/{clientId}/history", response_model=list[OrderResponse]
)
async def get_client_history(
    client_id: Annotated[uuid.UUID, Path(alias="clientId")],
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_READ])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Просмотр истории заказов конкретного клиента."""
    return await base_order_service.get_client_history(
        client_id=client_id, skip=skip, limit=limit
    )


@orders_router.get(
    "/courier/{courierId}/tasks", response_model=list[OrderResponse]
)
async def get_courier_tasks(
    courier_id: Annotated[uuid.UUID, Path(alias="courierId")],
    admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.ORDERS_READ])
    ],
    base_order_service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
):
    """Просмотр активных задач (заказов) конкретного курьера."""
    return await base_order_service.get_courier_tasks(courier_id=courier_id)


@orders_router.post(
    "/jobs/expire-stale",
    summary="Отменить зависшие заказы",
    description=(
        "Массово отменяет заказы: NEW старше порога "
        "(по умолчанию 48ч), ASSIGNED старше 72ч. "
        "Возвращает кредит по контрактным заказам. "
        "Идемпотентен."
    ),
)
async def run_expire_stale_orders_job(
    admin: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.ORDERS_EDIT]),
    ],
    service: Annotated[
        BaseOrderService, Depends(get_base_order_service)
    ],
    max_age_hours: Annotated[
        int, Query(ge=1, le=720, alias="maxAgeHours")
    ] = 48,
    assigned_max_age_hours: Annotated[
        int,
        Query(ge=1, le=720, alias="assignedMaxAgeHours"),
    ] = 72,
):
    """Автоматическая экспирация заказов.

    Вызывается по расписанию (Railway cron) или вручную
    администратором. SKIP LOCKED — безопасен при
    параллельном запуске.
    """
    cancelled = await service.expire_stale_orders(
        max_age_hours=max_age_hours,
        assigned_max_age_hours=assigned_max_age_hours,
        admin_id=admin.id,
    )
    return {"cancelled": cancelled}
