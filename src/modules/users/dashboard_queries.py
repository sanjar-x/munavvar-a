# src/modules/users/dashboard_queries.py
"""Read-only SQL-запросы для Dashboard API — домен Couriers."""

import uuid
from datetime import date, timedelta

from sqlalchemy import Date, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.catalog.enums import ProductType
from src.modules.catalog.models import Product
from src.modules.finances.enums import (
    AccountType,
    TransactionStatus,
)
from src.modules.finances.models import Account, Transaction
from src.modules.inventory.enums import (
    InventoryType,
    TransferType,
)
from src.modules.inventory.models import (
    Balance,
    Inventory,
    StockTransaction,
    StockTransfer,
)
from src.modules.orders.enums import OrderStatus
from src.modules.orders.models import Order
from src.modules.users.dashboard_schemas import (
    CourierDayLoad,
    CourierFleetCard,
    CourierFleetResponse,
    CourierLoadResponse,
    CourierVehicleBalance,
)
from src.modules.users.enums import Role
from src.modules.users.models import User


class CourierDashboardQueries:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_fleet(self) -> CourierFleetResponse:
        # Sargable "today" range — позволяет использовать
        # индексы на created_at вместо func.date().
        _today = func.current_date()
        _tomorrow = _today + text("INTERVAL '1 day'")

        # Все активные курьеры
        couriers_stmt = select(User.id, User.username).where(
            User.role == Role.COURIER,
            User.is_active.is_(True),
        )
        courier_rows = (await self.session.execute(couriers_stmt)).all()

        if not courier_rows:
            return CourierFleetResponse(
                couriers=[],
                total_active=0,
                total_stock_on_couriers=0,
                total_courier_cash=0,
            )

        courier_ids = [r.id for r in courier_rows]
        courier_names = {r.id: r.username for r in courier_rows}

        # Транспорт (активные инвентари COURIER)
        vehicles_stmt = select(
            Inventory.user_id,
            Inventory.id.label("vid"),
            Inventory.name.label("vname"),
        ).where(
            Inventory.type == InventoryType.COURIER,
            Inventory.is_active.is_(True),
            Inventory.user_id.in_(courier_ids),
        )
        vehicle_rows = (await self.session.execute(vehicles_stmt)).all()
        vehicles = {r.user_id: (r.vid, r.vname) for r in vehicle_rows}
        vehicle_ids = [r.vid for r in vehicle_rows]

        # Остатки в машинах
        balance_rows = []
        if vehicle_ids:
            balances_stmt = (
                select(
                    Balance.inventory_id,
                    Product.id.label("pid"),
                    Product.name.label("pname"),
                    Balance.quantity,
                )
                .join(
                    Product,
                    Balance.product_id == Product.id,
                )
                .where(
                    Balance.inventory_id.in_(vehicle_ids),
                    Balance.quantity > 0,
                )
            )
            balance_rows = (await self.session.execute(balances_stmt)).all()

        vehicle_stock: dict[uuid.UUID, list[CourierVehicleBalance]] = {}
        total_stock = 0
        for r in balance_rows:
            vehicle_stock.setdefault(r.inventory_id, []).append(
                CourierVehicleBalance(
                    product_id=r.pid,
                    product_name=r.pname,
                    quantity=r.quantity,
                )
            )
            total_stock += r.quantity

        # Кассы курьеров
        cash_stmt = select(
            Account.user_id,
            Account.balance,
        ).where(
            Account.type == AccountType.COURIER,
            Account.user_id.in_(courier_ids),
        )
        cash_rows = (await self.session.execute(cash_stmt)).all()
        cash_map = {r.user_id: r.balance for r in cash_rows}

        # Заказы за сегодня (не-отменённые)
        orders_stmt = (
            select(
                Order.courier_id,
                func.count().label("assigned"),
                func.count()
                .filter(Order.status == OrderStatus.DELIVERED)
                .label("delivered"),
            )
            .where(
                Order.created_at >= _today,
                Order.created_at < _tomorrow,
                Order.courier_id.in_(courier_ids),
                Order.is_active.is_(True),
                Order.status != OrderStatus.CANCELLED,
            )
            .group_by(Order.courier_id)
        )
        order_rows = (await self.session.execute(orders_stmt)).all()
        orders_map = {
            r.courier_id: (r.assigned, r.delivered) for r in order_rows
        }

        # Наличные, собранные за сегодня
        collected_stmt = (
            select(
                Account.user_id,
                func.coalesce(func.sum(Transaction.amount), 0).label(
                    "collected"
                ),
            )
            .join(
                Account,
                Transaction.to_id == Account.id,
            )
            .where(
                Account.type == AccountType.COURIER,
                Transaction.status == TransactionStatus.COMPLETED,
                Transaction.created_at >= _today,
                Transaction.created_at < _tomorrow,
                Account.user_id.in_(courier_ids),
            )
            .group_by(Account.user_id)
        )
        coll_rows = (await self.session.execute(collected_stmt)).all()
        collected_map = {r.user_id: r.collected for r in coll_rows}

        # Тара собранная за сегодня (CLIENT_RETURN)
        tara_rows = []
        if vehicle_ids:
            tara_stmt = (
                select(
                    StockTransfer.to_id,
                    func.coalesce(
                        func.sum(StockTransaction.quantity),
                        0,
                    ).label("tara"),
                )
                .select_from(StockTransaction)
                .join(
                    StockTransfer,
                    StockTransaction.transfer_id == StockTransfer.id,
                )
                .join(
                    Product,
                    StockTransaction.product_id == Product.id,
                )
                .where(
                    StockTransfer.type == TransferType.CLIENT_RETURN,
                    Product.type == ProductType.CONTAINER,
                    StockTransaction.created_at >= _today,
                    StockTransaction.created_at < _tomorrow,
                    StockTransfer.to_id.in_(vehicle_ids),
                )
                .group_by(StockTransfer.to_id)
            )
            tara_rows = (await self.session.execute(tara_stmt)).all()
        # to_id -> vehicle_id -> courier_id
        vid_to_uid = {vid: uid for uid, (vid, _) in vehicles.items()}
        tara_map: dict[uuid.UUID, int] = {}
        for r in tara_rows:
            uid = vid_to_uid.get(r.to_id)
            if uid:
                tara_map[uid] = tara_map.get(uid, 0) + r.tara

        # Собираем карточки
        cards: list[CourierFleetCard] = []
        total_cash = 0
        active_count = 0

        for cid in courier_ids:
            v = vehicles.get(cid)
            is_active = v is not None
            if is_active:
                active_count += 1
            vid = v[0] if v else None
            vname = v[1] if v else None

            cash_bal = cash_map.get(cid, 0)
            total_cash += max(cash_bal, 0)

            o = orders_map.get(cid, (0, 0))

            cards.append(
                CourierFleetCard(
                    courier_id=cid,
                    courier_name=courier_names[cid],
                    vehicle_id=vid,
                    vehicle_name=vname,
                    is_active=is_active,
                    vehicle_balances=(
                        vehicle_stock.get(vid, []) if vid else []
                    ),
                    orders_assigned_today=o[0],
                    orders_delivered_today=o[1],
                    cash_balance=cash_bal,
                    cash_collected_today=(collected_map.get(cid, 0)),
                    containers_collected_today=(tara_map.get(cid, 0)),
                )
            )

        return CourierFleetResponse(
            couriers=cards,
            total_active=active_count,
            total_stock_on_couriers=total_stock,
            total_courier_cash=total_cash,
        )

    # --- EP-20: Загрузка курьеров по дням (BR-19) ---

    async def get_courier_load(
        self,
        date_from: date,
        date_to: date,
    ) -> CourierLoadResponse:
        end = date_to + timedelta(days=1)
        stmt = (
            select(
                func.date(Order.created_at).cast(Date).label("day"),
                Order.courier_id.label("cid"),
                User.username.label("cname"),
                func.count().label("cnt"),
            )
            .join(User, Order.courier_id == User.id)
            .where(
                Order.status == OrderStatus.DELIVERED,
                Order.created_at >= date_from,
                Order.created_at < end,
                Order.courier_id.is_not(None),
                Order.is_active.is_(True),
            )
            .group_by(
                func.date(Order.created_at),
                Order.courier_id,
                User.username,
            )
            .order_by(
                func.date(Order.created_at),
                func.count().desc(),
            )
        )
        rows = (await self.session.execute(stmt)).all()

        data = [
            CourierDayLoad(
                date=str(r.day),
                courier_id=r.cid,
                courier_name=r.cname,
                deliveries_count=r.cnt,
            )
            for r in rows
        ]
        total = sum(d.deliveries_count for d in data)
        unique_couriers = len({d.courier_id for d in data})
        max_load = max(d.deliveries_count for d in data) if data else 0

        return CourierLoadResponse(
            data=data,
            total_deliveries=total,
            avg_per_courier=(
                round(total / unique_couriers, 2)
                if unique_couriers > 0
                else 0.0
            ),
            max_load=max_load,
        )
