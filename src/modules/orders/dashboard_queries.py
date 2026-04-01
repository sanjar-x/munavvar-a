# src/modules/orders/dashboard_queries.py
"""Read-only SQL-запросы для Dashboard API — домен Orders."""

from datetime import date, timedelta

from sqlalchemy import Date, Integer, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    SYSTEM_USER_ID,
    WALKIN_USER_ID,
)
from src.modules.inventory.enums import InventoryType
from src.modules.inventory.models import Inventory
from src.modules.orders.dashboard_schemas import (
    HeatmapCell,
    OrderFunnelResponse,
    OrderHeatmapResponse,
    OrdersSummary,
    OrderStatusCount,
    OrderTrendPoint,
    OrderTrendResponse,
    PaymentBreakdownResponse,
    PaymentMethodStats,
    StatusFunnelItem,
    TopClientItem,
    TopClientsResponse,
)
from src.modules.orders.enums import OrderStatus, SaleType
from src.modules.orders.models import Order
from src.modules.users.models import User

_ACTIVE_STATUSES = [
    OrderStatus.NEW,
    OrderStatus.ASSIGNED,
    OrderStatus.IN_TRANSIT,
    OrderStatus.ARRIVED,
]

_COMPLETED_STATUSES = [
    OrderStatus.DELIVERED,
    OrderStatus.PICKUP_COMPLETED,
]

_EXCLUDED_IDS = [SYSTEM_USER_ID, WALKIN_USER_ID]

_FSM_ORDER = [
    OrderStatus.NEW,
    OrderStatus.ASSIGNED,
    OrderStatus.IN_TRANSIT,
    OrderStatus.ARRIVED,
    OrderStatus.DELIVERED,
    OrderStatus.PICKUP_COMPLETED,
    OrderStatus.CANCELLED,
]


class OrderDashboardQueries:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_orders_summary(self) -> OrdersSummary:
        # --- Активные заказы (все даты, незавершённые) ---
        active_stmt = (
            select(
                Order.status,
                func.count().label("cnt"),
            )
            .where(
                Order.status.in_(_ACTIVE_STATUSES),
                Order.is_active.is_(True),
            )
            .group_by(Order.status)
        )
        active_rows = (await self.session.execute(active_stmt)).all()
        active_by_status = [
            OrderStatusCount(status=r.status, count=r.cnt) for r in active_rows
        ]

        # Незназначенные delivery-заказы
        unassigned_stmt = select(func.count()).where(
            Order.status == OrderStatus.NEW,
            Order.sale_type == SaleType.DELIVERY,
            Order.courier_id.is_(None),
            Order.is_active.is_(True),
        )
        unassigned = await self.session.scalar(unassigned_stmt) or 0

        # --- Статистика за сегодня ---
        # Sargable range вместо func.date() — позволяет
        # использовать индекс на created_at.
        _today = func.current_date()
        _tomorrow = _today + text("INTERVAL '1 day'")

        today_stmt = (
            select(
                func.count().label("total"),
                func.count()
                .filter(Order.status.in_(_COMPLETED_STATUSES))
                .label("delivered"),
                func.count()
                .filter(Order.status == OrderStatus.CANCELLED)
                .label("cancelled"),
                func.coalesce(
                    func.sum(Order.total_amount).filter(
                        Order.status.in_(_COMPLETED_STATUSES)
                    ),
                    0,
                ).label("revenue"),
                func.count()
                .filter(Order.sale_type == SaleType.DELIVERY)
                .label("delivery_cnt"),
                func.count()
                .filter(Order.sale_type == SaleType.WAREHOUSE_PICKUP)
                .label("pickup_cnt"),
            )
            .select_from(Order)
            .where(
                Order.created_at >= _today,
                Order.created_at < _tomorrow,
                Order.is_active.is_(True),
            )
        )
        today = (await self.session.execute(today_stmt)).one()

        # --- Активные курьеры ---
        couriers_stmt = select(
            func.count(func.distinct(Inventory.user_id))
        ).where(
            Inventory.type == InventoryType.COURIER,
            Inventory.is_active.is_(True),
        )
        active_couriers = await self.session.scalar(couriers_stmt) or 0

        return OrdersSummary(
            active_by_status=active_by_status,
            unassigned_orders=unassigned,
            total_today=today.total,
            delivered_today=today.delivered,
            cancelled_today=today.cancelled,
            revenue_today=today.revenue,
            by_sale_type={
                SaleType.DELIVERY: today.delivery_cnt,
                SaleType.WAREHOUSE_PICKUP: (today.pickup_cnt),
            },
            active_couriers=active_couriers,
        )

    # --- EP-5: Разбивка способов оплаты (BR-5) ---

    async def get_payment_breakdown(
        self,
        date_from: date,
        date_to: date,
    ) -> PaymentBreakdownResponse:
        stmt = (
            select(
                Order.payment_method.label("method"),
                func.count().label("cnt"),
                func.coalesce(func.sum(Order.total_amount), 0).label("amount"),
            )
            .where(
                Order.status.in_(_COMPLETED_STATUSES),
                Order.created_at >= date_from,
                Order.created_at < date_to + timedelta(days=1),
                Order.is_active.is_(True),
            )
            .group_by(Order.payment_method)
        )
        rows = (await self.session.execute(stmt)).all()

        methods = [
            PaymentMethodStats(
                method=r.method,
                orders_count=r.cnt,
                total_amount=r.amount,
            )
            for r in rows
        ]
        total_orders = sum(m.orders_count for m in methods)
        total_amount = sum(m.total_amount for m in methods)

        return PaymentBreakdownResponse(
            methods=methods,
            total_orders=total_orders,
            total_amount=total_amount,
        )

    # --- EP-2: Тренд заказов (BR-2) ---

    async def get_order_trends(
        self,
        date_from: date,
        date_to: date,
        granularity: str = "day",
        sale_type: str | None = None,
        client_type: str | None = None,
    ) -> OrderTrendResponse:
        end = date_to + timedelta(days=1)
        period_col = func.date_trunc(granularity, Order.created_at).cast(Date)

        stmt = (
            select(
                period_col.label("period"),
                func.count().label("cnt"),
                func.coalesce(func.sum(Order.total_amount), 0).label("rev"),
            )
            .select_from(Order)
            .where(
                Order.status.in_(_COMPLETED_STATUSES),
                Order.created_at >= date_from,
                Order.created_at < end,
                Order.is_active.is_(True),
            )
            .group_by(period_col)
            .order_by(period_col)
        )

        if sale_type:
            stmt = stmt.where(Order.sale_type == sale_type)
        if client_type:
            stmt = stmt.join(User, Order.client_id == User.id).where(
                User.role == client_type
            )

        rows = (await self.session.execute(stmt)).all()

        points = [
            OrderTrendPoint(
                period=str(r.period),
                orders_count=r.cnt,
                revenue=r.rev,
                avg_order_value=(r.rev // r.cnt if r.cnt else 0),
            )
            for r in rows
        ]

        return OrderTrendResponse(
            points=points,
            total_orders=sum(p.orders_count for p in points),
            total_revenue=sum(p.revenue for p in points),
        )

    # --- EP-3: Воронка статусов (BR-3) ---

    async def get_order_funnel(
        self,
        date_from: date,
        date_to: date,
    ) -> OrderFunnelResponse:
        end = date_to + timedelta(days=1)
        stmt = (
            select(
                Order.status.label("status"),
                func.count().label("cnt"),
            )
            .where(
                Order.created_at >= date_from,
                Order.created_at < end,
                Order.is_active.is_(True),
            )
            .group_by(Order.status)
        )
        rows = (await self.session.execute(stmt)).all()

        counts = {r.status: r.cnt for r in rows}
        total = sum(counts.values())

        statuses = [
            StatusFunnelItem(
                status=s.value,
                count=counts.get(s.value, 0),
                percentage=(
                    round(
                        counts.get(s.value, 0) / total,
                        4,
                    )
                    if total > 0
                    else 0.0
                ),
            )
            for s in _FSM_ORDER
        ]

        return OrderFunnelResponse(total=total, statuses=statuses)

    # --- EP-4: Тепловая карта (BR-4) ---

    async def get_order_heatmap(
        self,
        date_from: date,
        date_to: date,
    ) -> OrderHeatmapResponse:
        end = date_to + timedelta(days=1)
        # ISODOW: 1=Пн..7=Вс; AT TIME ZONE для
        # корректных часов по Ташкенту.
        tz_col = func.timezone("Asia/Tashkent", Order.created_at)

        stmt = (
            select(
                func.extract("isodow", tz_col).cast(Integer).label("dow"),
                func.extract("hour", tz_col).cast(Integer).label("hour"),
                func.count().label("cnt"),
            )
            .where(
                Order.created_at >= date_from,
                Order.created_at < end,
                Order.is_active.is_(True),
            )
            .group_by(
                func.extract("isodow", tz_col),
                func.extract("hour", tz_col),
            )
            .order_by(
                func.extract("isodow", tz_col),
                func.extract("hour", tz_col),
            )
        )
        rows = (await self.session.execute(stmt)).all()

        cells = [
            HeatmapCell(
                day_of_week=r.dow,
                hour=r.hour,
                count=r.cnt,
            )
            for r in rows
        ]
        max_count = max(c.count for c in cells) if cells else 0

        return OrderHeatmapResponse(cells=cells, max_count=max_count)

    # --- EP-7: Топ клиентов (BR-16) ---

    async def get_top_clients(
        self,
        date_from: date,
        date_to: date,
        limit: int = 10,
        sort_by: str = "total_amount",
    ) -> TopClientsResponse:
        end = date_to + timedelta(days=1)
        order_col = (
            func.sum(Order.total_amount)
            if sort_by == "total_amount"
            else func.count()
        )

        stmt = (
            select(
                User.id.label("cid"),
                User.username.label("cname"),
                User.role.label("ctype"),
                func.count().label("cnt"),
                func.coalesce(func.sum(Order.total_amount), 0).label("amount"),
            )
            .join(User, Order.client_id == User.id)
            .where(
                Order.status.in_(_COMPLETED_STATUSES),
                Order.created_at >= date_from,
                Order.created_at < end,
                Order.is_active.is_(True),
                User.id.not_in(_EXCLUDED_IDS),
            )
            .group_by(User.id, User.username, User.role)
            .order_by(order_col.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()

        return TopClientsResponse(
            clients=[
                TopClientItem(
                    client_id=r.cid,
                    client_name=r.cname,
                    client_type=r.ctype,
                    orders_count=r.cnt,
                    total_amount=r.amount,
                )
                for r in rows
            ]
        )
