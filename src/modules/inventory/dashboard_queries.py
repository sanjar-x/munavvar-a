# src/modules/inventory/dashboard_queries.py
"""Read-only SQL-запросы для Dashboard API — домен Inventory."""

import uuid
from datetime import date, timedelta

from sqlalchemy import Date, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    SYSTEM_USER_ID,
    WALKIN_USER_ID,
)
from src.modules.catalog.enums import ProductType
from src.modules.catalog.models import Product
from src.modules.inventory.dashboard_schemas import (
    ContainerDebtorItem,
    ContainerDebtorsResponse,
    ContainerDistribution,
    ContainerProductBreakdown,
    InventorySummary,
    InventoryTrendPoint,
    InventoryTrendResponse,
    LossTrendPoint,
    MovementStatsResponse,
    MovementTypeStats,
    VirtualAccountsResponse,
    VirtualProductBalance,
)
from src.modules.inventory.enums import InventoryType
from src.modules.inventory.models import (
    Balance,
    Inventory,
    StockTransaction,
    StockTransfer,
)
from src.modules.orders.enums import OrderStatus
from src.modules.orders.models import Order
from src.modules.users.models import User

_EXCLUDED_IDS = [SYSTEM_USER_ID, WALKIN_USER_ID]


class InventoryDashboardQueries:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- EP-13: Складская сводка (BR-10) ---

    async def get_summary(
        self,
        warehouse_owner_id: uuid.UUID | None = None,
    ) -> InventorySummary:
        # Кладовщик видит ТОЛЬКО свои склады (BRD BR-10).
        # Данные по курьерам и клиентам скрываются.
        is_storekeeper = warehouse_owner_id is not None

        _wh_co = [
            InventoryType.WAREHOUSE,
            InventoryType.COURIER,
        ]

        stock_stmt = (
            select(
                func.coalesce(
                    func.sum(Balance.quantity).filter(
                        Product.type == ProductType.WATER,
                        Inventory.type.in_(_wh_co),
                    ),
                    0,
                ).label("water"),
                func.coalesce(
                    func.sum(Balance.quantity).filter(
                        Product.type == ProductType.CONTAINER,
                        Inventory.type.in_(_wh_co),
                    ),
                    0,
                ).label("container"),
                func.coalesce(
                    func.sum(Balance.quantity).filter(
                        Product.type == ProductType.EQUIPMENT,
                        Inventory.type.in_(_wh_co),
                    ),
                    0,
                ).label("equipment"),
                func.coalesce(
                    func.sum(Balance.quantity).filter(
                        Product.type == ProductType.CONTAINER,
                        Inventory.type == InventoryType.CLIENT,
                    ),
                    0,
                ).label("at_clients"),
                func.coalesce(
                    func.sum(Balance.quantity).filter(
                        Inventory.type == InventoryType.COURIER,
                    ),
                    0,
                ).label("on_couriers"),
            )
            .select_from(Balance)
            .join(
                Inventory,
                Balance.inventory_id == Inventory.id,
            )
            .join(
                Product,
                Balance.product_id == Product.id,
            )
            .where(Balance.quantity > 0)
        )

        if is_storekeeper:
            # Только склады кладовщика.
            # at_clients и on_couriers вернут 0, т.к.
            # ни один ряд не пройдёт inner-фильтры.
            stock_stmt = stock_stmt.where(
                Inventory.type == InventoryType.WAREHOUSE,
                Inventory.user_id == warehouse_owner_id,
            )

        row = (await self.session.execute(stock_stmt)).one()

        # Потери за сегодня (sargable range)
        _today = func.current_date()
        _tomorrow = _today + text("INTERVAL '1 day'")
        losses_stmt = (
            select(
                func.coalesce(
                    func.sum(StockTransaction.quantity),
                    0,
                )
            )
            .join(
                Inventory,
                StockTransaction.to_id == Inventory.id,
            )
            .where(
                Inventory.type == InventoryType.VIRTUAL_LOSS,
                StockTransaction.created_at >= _today,
                StockTransaction.created_at < _tomorrow,
            )
        )
        losses_today = await self.session.scalar(losses_stmt) or 0

        # Активные курьеры
        couriers_stmt = select(
            func.count(func.distinct(Inventory.user_id))
        ).where(
            Inventory.type == InventoryType.COURIER,
            Inventory.is_active.is_(True),
        )
        active_couriers = await self.session.scalar(couriers_stmt) or 0

        return InventorySummary(
            total_water_stock=row.water,
            total_container_stock=row.container,
            total_equipment_stock=row.equipment,
            containers_at_clients=row.at_clients,
            stock_on_couriers=row.on_couriers,
            losses_today=losses_today,
            active_couriers_count=active_couriers,
        )

    # --- EP-14: Распределение тары (BR-11) ---

    async def get_container_distribution(
        self,
    ) -> ContainerDistribution:
        # Агрегат по всей таре
        agg_stmt = (
            select(
                Inventory.type.label("inv_type"),
                func.coalesce(func.sum(Balance.quantity), 0).label("qty"),
            )
            .select_from(Balance)
            .join(
                Inventory,
                Balance.inventory_id == Inventory.id,
            )
            .join(
                Product,
                Balance.product_id == Product.id,
            )
            .where(
                Product.type == ProductType.CONTAINER,
            )
            .group_by(Inventory.type)
        )
        agg_rows = (await self.session.execute(agg_stmt)).all()

        totals: dict[str, int] = {}
        for r in agg_rows:
            totals[r.inv_type] = r.qty

        # Разбивка по продуктам
        prod_stmt = (
            select(
                Product.id.label("pid"),
                Product.name.label("pname"),
                Inventory.type.label("inv_type"),
                func.coalesce(func.sum(Balance.quantity), 0).label("qty"),
            )
            .select_from(Balance)
            .join(
                Inventory,
                Balance.inventory_id == Inventory.id,
            )
            .join(
                Product,
                Balance.product_id == Product.id,
            )
            .where(
                Product.type == ProductType.CONTAINER,
            )
            .group_by(
                Product.id,
                Product.name,
                Inventory.type,
            )
        )
        prod_rows = (await self.session.execute(prod_stmt)).all()

        products: dict[uuid.UUID, ContainerProductBreakdown] = {}
        for r in prod_rows:
            if r.pid not in products:
                products[r.pid] = ContainerProductBreakdown(
                    product_id=r.pid,
                    product_name=r.pname,
                )
            p = products[r.pid]
            inv = r.inv_type
            if inv == InventoryType.WAREHOUSE:
                p.at_warehouses = r.qty
            elif inv == InventoryType.COURIER:
                p.at_couriers = r.qty
            elif inv == InventoryType.CLIENT:
                p.at_clients = r.qty
            elif inv == InventoryType.VIRTUAL_LOSS:
                p.lost = r.qty

        for p in products.values():
            p.total = p.at_warehouses + p.at_couriers + p.at_clients + p.lost

        wh = totals.get(InventoryType.WAREHOUSE, 0)
        co = totals.get(InventoryType.COURIER, 0)
        cl = totals.get(InventoryType.CLIENT, 0)
        lo = totals.get(InventoryType.VIRTUAL_LOSS, 0)
        vv = abs(totals.get(InventoryType.VIRTUAL_VENDOR, 0))

        return ContainerDistribution(
            at_warehouses=wh,
            at_couriers=co,
            at_clients=cl,
            lost=lo,
            total_in_system=vv,
            per_product=list(products.values()),
        )

    # --- EP-19: Виртуальные счета + целостность (BR-18) ---

    async def get_virtual_accounts(
        self,
    ) -> VirtualAccountsResponse:
        stmt = (
            select(
                Product.id.label("pid"),
                Product.name.label("pname"),
                Inventory.type.label("inv_type"),
                func.coalesce(func.sum(Balance.quantity), 0).label("qty"),
            )
            .select_from(Balance)
            .join(
                Inventory,
                Balance.inventory_id == Inventory.id,
            )
            .join(
                Product,
                Balance.product_id == Product.id,
            )
            .group_by(
                Product.id,
                Product.name,
                Inventory.type,
            )
        )
        rows = (await self.session.execute(stmt)).all()

        vendor_by_product: dict[uuid.UUID, int] = {}
        loss_by_product: dict[uuid.UUID, int] = {}
        names: dict[uuid.UUID, str] = {}
        vendor_total = 0
        loss_total = 0
        real_total = 0

        real_types = {
            InventoryType.WAREHOUSE,
            InventoryType.COURIER,
            InventoryType.CLIENT,
        }

        for r in rows:
            names[r.pid] = r.pname
            if r.inv_type == InventoryType.VIRTUAL_VENDOR:
                vendor_by_product[r.pid] = (
                    vendor_by_product.get(r.pid, 0) + r.qty
                )
                vendor_total += r.qty
            elif r.inv_type == InventoryType.VIRTUAL_LOSS:
                loss_by_product[r.pid] = loss_by_product.get(r.pid, 0) + r.qty
                loss_total += r.qty
            elif r.inv_type in real_types:
                real_total += r.qty

        abs_vendor = abs(vendor_total)
        diff = abs_vendor - loss_total - real_total

        per_product = []
        for pid, name in names.items():
            vb = vendor_by_product.get(pid, 0)
            lb = loss_by_product.get(pid, 0)
            if vb != 0 or lb != 0:
                per_product.append(
                    VirtualProductBalance(
                        product_id=pid,
                        product_name=name,
                        vendor_balance=vb,
                        loss_balance=lb,
                    )
                )

        # Тренд потерь за 30 дней (PRD EP-19)
        trend_stmt = (
            select(
                func.date(StockTransaction.created_at).label("day"),
                func.sum(StockTransaction.quantity).label("qty"),
            )
            .join(
                Inventory,
                StockTransaction.to_id == Inventory.id,
            )
            .where(
                Inventory.type == InventoryType.VIRTUAL_LOSS,
                StockTransaction.created_at
                >= func.current_date() - text("INTERVAL '30 days'"),
            )
            .group_by(func.date(StockTransaction.created_at))
            .order_by(func.date(StockTransaction.created_at))
        )
        trend_rows = (await self.session.execute(trend_stmt)).all()
        loss_trend = [
            LossTrendPoint(date=str(r.day), quantity=r.qty) for r in trend_rows
        ]

        return VirtualAccountsResponse(
            vendor_total=abs_vendor,
            loss_total=loss_total,
            real_total=real_total,
            integrity_ok=diff == 0,
            integrity_diff=diff,
            per_product=per_product,
            loss_trend_30d=loss_trend,
        )

    # --- EP-15: Должники по таре (BR-12) ---

    async def get_container_debtors(
        self, limit: int = 10
    ) -> ContainerDebtorsResponse:
        # Последний завершённый заказ клиента
        last_order = (
            select(func.max(Order.created_at).cast(Date))
            .where(
                Order.client_id == User.id,
                Order.status.in_(
                    [
                        OrderStatus.DELIVERED,
                        OrderStatus.PICKUP_COMPLETED,
                    ]
                ),
            )
            .correlate(User)
            .scalar_subquery()
        )

        stmt = (
            select(
                User.id.label("cid"),
                User.username.label("cname"),
                User.role.label("ctype"),
                func.sum(Balance.quantity).label("balance"),
                last_order.label("last_ord"),
            )
            .select_from(Balance)
            .join(
                Inventory,
                Balance.inventory_id == Inventory.id,
            )
            .join(
                Product,
                Balance.product_id == Product.id,
            )
            .join(User, Inventory.user_id == User.id)
            .where(
                Inventory.type == InventoryType.CLIENT,
                Product.type == ProductType.CONTAINER,
                Balance.quantity > 0,
                User.id.not_in(_EXCLUDED_IDS),
            )
            .group_by(User.id, User.username, User.role)
            .order_by(func.sum(Balance.quantity).desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()

        total_stmt = (
            select(func.coalesce(func.sum(Balance.quantity), 0))
            .join(
                Inventory,
                Balance.inventory_id == Inventory.id,
            )
            .join(
                Product,
                Balance.product_id == Product.id,
            )
            .where(
                Inventory.type == InventoryType.CLIENT,
                Product.type == ProductType.CONTAINER,
                Balance.quantity > 0,
            )
        )
        total = await self.session.scalar(total_stmt) or 0

        debtors = [
            ContainerDebtorItem(
                client_id=r.cid,
                client_name=r.cname,
                client_type=r.ctype,
                container_balance=r.balance,
                last_order_date=(str(r.last_ord) if r.last_ord else None),
                days_since_last_order=None,
            )
            for r in rows
        ]

        return ContainerDebtorsResponse(
            debtors=debtors,
            total_containers_at_clients=total,
        )

    # --- EP-16: Статистика перемещений (BR-13) ---

    async def get_movement_stats(
        self,
        date_from: date,
        date_to: date,
        warehouse_owner_id: uuid.UUID | None = None,
    ) -> MovementStatsResponse:
        end = date_to + timedelta(days=1)
        stmt = (
            select(
                StockTransfer.type.label("ttype"),
                func.count(func.distinct(StockTransfer.id)).label("tcnt"),
                func.coalesce(
                    func.sum(StockTransaction.quantity),
                    0,
                ).label("items"),
            )
            .select_from(StockTransaction)
            .join(
                StockTransfer,
                StockTransaction.transfer_id == StockTransfer.id,
            )
            .where(
                StockTransfer.created_at >= date_from,
                StockTransfer.created_at < end,
            )
            .group_by(StockTransfer.type)
        )

        if warehouse_owner_id is not None:
            # Кладовщик видит только свои склады
            own_wh = (
                select(Inventory.id).where(
                    Inventory.user_id == warehouse_owner_id,
                    Inventory.type == InventoryType.WAREHOUSE,
                )
            ).scalar_subquery()
            stmt = stmt.where(
                StockTransfer.from_id.in_(own_wh)
                | StockTransfer.to_id.in_(own_wh)
            )

        rows = (await self.session.execute(stmt)).all()

        types = [
            MovementTypeStats(
                transfer_type=r.ttype,
                transfers_count=r.tcnt,
                total_items=r.items,
            )
            for r in rows
        ]

        return MovementStatsResponse(
            types=types,
            total_transfers=sum(t.transfers_count for t in types),
            total_items=sum(t.total_items for t in types),
        )

    # --- EP-18: Тренды остатков (BR-17) ---

    async def get_inventory_trends(
        self,
        date_from: date,
        date_to: date,
    ) -> InventoryTrendResponse:
        # Подход: текущий баланс - будущие изменения.
        # Для каждого дня D:
        #   balance_on_D = current - SUM(changes after D)
        # «change» = +qty для to_id, -qty для from_id.
        # Считаем net daily change для WAREHOUSE+COURIER
        # и отдельно для CLIENT.

        end = date_to + timedelta(days=1)

        # Текущие балансы
        cur_stmt = (
            select(
                func.coalesce(
                    func.sum(Balance.quantity).filter(
                        Product.type == ProductType.WATER,
                        Inventory.type.in_(
                            [
                                InventoryType.WAREHOUSE,
                                InventoryType.COURIER,
                            ]
                        ),
                    ),
                    0,
                ).label("water"),
                func.coalesce(
                    func.sum(Balance.quantity).filter(
                        Product.type == ProductType.CONTAINER,
                        Inventory.type.in_(
                            [
                                InventoryType.WAREHOUSE,
                                InventoryType.COURIER,
                            ]
                        ),
                    ),
                    0,
                ).label("container"),
                func.coalesce(
                    func.sum(Balance.quantity).filter(
                        Product.type == ProductType.CONTAINER,
                        Inventory.type == InventoryType.CLIENT,
                    ),
                    0,
                ).label("clients"),
            )
            .select_from(Balance)
            .join(
                Inventory,
                Balance.inventory_id == Inventory.id,
            )
            .join(
                Product,
                Balance.product_id == Product.id,
            )
        )
        cur = (await self.session.execute(cur_stmt)).one()

        # Ежедневные net-изменения после date_from
        # Входящие (+) и исходящие (-) по дням
        day_col = func.date(StockTransaction.created_at)
        inv_to = Inventory.__table__.alias("i_to")
        inv_from = Inventory.__table__.alias("i_from")

        net_stmt = (
            select(
                day_col.label("day"),
                # Net water на складах+курьерах
                func.coalesce(
                    func.sum(StockTransaction.quantity).filter(
                        Product.type == ProductType.WATER,
                        inv_to.c.type.in_(
                            [
                                InventoryType.WAREHOUSE,
                                InventoryType.COURIER,
                            ]
                        ),
                    ),
                    0,
                ).label("water_in"),
                func.coalesce(
                    func.sum(StockTransaction.quantity).filter(
                        Product.type == ProductType.WATER,
                        inv_from.c.type.in_(
                            [
                                InventoryType.WAREHOUSE,
                                InventoryType.COURIER,
                            ]
                        ),
                    ),
                    0,
                ).label("water_out"),
                # Net container на складах+курьерах
                func.coalesce(
                    func.sum(StockTransaction.quantity).filter(
                        Product.type == ProductType.CONTAINER,
                        inv_to.c.type.in_(
                            [
                                InventoryType.WAREHOUSE,
                                InventoryType.COURIER,
                            ]
                        ),
                    ),
                    0,
                ).label("cont_in"),
                func.coalesce(
                    func.sum(StockTransaction.quantity).filter(
                        Product.type == ProductType.CONTAINER,
                        inv_from.c.type.in_(
                            [
                                InventoryType.WAREHOUSE,
                                InventoryType.COURIER,
                            ]
                        ),
                    ),
                    0,
                ).label("cont_out"),
                # Net container у клиентов
                func.coalesce(
                    func.sum(StockTransaction.quantity).filter(
                        Product.type == ProductType.CONTAINER,
                        inv_to.c.type == InventoryType.CLIENT,
                    ),
                    0,
                ).label("cl_in"),
                func.coalesce(
                    func.sum(StockTransaction.quantity).filter(
                        Product.type == ProductType.CONTAINER,
                        inv_from.c.type == InventoryType.CLIENT,
                    ),
                    0,
                ).label("cl_out"),
            )
            .select_from(
                StockTransaction.__table__.join(
                    inv_to,
                    StockTransaction.to_id == inv_to.c.id,
                )
                .join(
                    inv_from,
                    StockTransaction.from_id == inv_from.c.id,
                )
                .join(
                    Product.__table__,
                    StockTransaction.product_id == Product.id,
                )
            )
            .where(
                StockTransaction.created_at >= date_from,
                StockTransaction.created_at < end,
            )
            .group_by(day_col)
            .order_by(day_col)
        )
        net_rows = (await self.session.execute(net_stmt)).all()

        # Строим точки: идём от конца к началу,
        # вычитая изменения из текущих балансов.
        water_now = cur.water
        cont_now = cur.container
        cl_now = cur.clients

        # Собираем net-changes по дням
        day_nets: list[tuple[str, int, int, int]] = []
        for r in net_rows:
            w_net = r.water_in - r.water_out
            c_net = r.cont_in - r.cont_out
            cl_net = r.cl_in - r.cl_out
            day_nets.append((str(r.day), w_net, c_net, cl_net))

        # Reverse accumulation: от последнего дня
        # к первому вычитаем будущие изменения
        points: list[InventoryTrendPoint] = []
        # Сначала добавим "после последнего дня" = текущее
        accum_w = 0
        accum_c = 0
        accum_cl = 0

        for day_str, w, c, cl in reversed(day_nets):
            points.append(
                InventoryTrendPoint(
                    date=day_str,
                    water_stock=water_now - accum_w,
                    container_stock=(cont_now - accum_c),
                    containers_at_clients=(cl_now - accum_cl),
                )
            )
            accum_w += w
            accum_c += c
            accum_cl += cl

        points.reverse()

        return InventoryTrendResponse(points=points)
