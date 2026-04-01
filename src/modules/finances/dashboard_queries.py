# src/modules/finances/dashboard_queries.py
"""Read-only SQL-запросы для Dashboard API — домен Finance."""

from datetime import date, timedelta

from sqlalchemy import Date, Integer, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    SYSTEM_USER_ID,
    WALKIN_USER_ID,
)
from src.modules.finances.dashboard_schemas import (
    AgingBucket,
    DebtAgingResponse,
    FinanceSummaryKPIs,
    PaymentMethodFinanceStats,
    PaymentMethodsFinanceResponse,
    RevenueBySegmentResponse,
    RevenueTrendPoint,
    RevenueTrendResponse,
    SegmentRevenue,
    TopDebtorItem,
    TopDebtorsResponse,
)
from src.modules.finances.enums import (
    AccountType,
    TransactionStatus,
)
from src.modules.finances.models import (
    Account,
    Transaction,
)
from src.modules.orders.enums import OrderStatus
from src.modules.orders.models import Order
from src.modules.users.enums import Role
from src.modules.users.models import User

_COMPLETED_STATUSES = [
    OrderStatus.DELIVERED,
    OrderStatus.PICKUP_COMPLETED,
]

_EXCLUDED_IDS = [SYSTEM_USER_ID, WALKIN_USER_ID]

# Aging-бакеты адаптированные под недельный цикл
_AGING_BUCKETS = [
    ("0-7 дней", 0, 7),
    ("8-14 дней", 8, 14),
    ("15-30 дней", 15, 30),
    ("31-60 дней", 31, 60),
    ("60+ дней", 61, None),
]


class FinanceDashboardQueries:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- EP-8: Динамика выручки (BR-6) ---

    async def get_revenue_trend(
        self,
        date_from: date,
        date_to: date,
        granularity: str = "day",
    ) -> RevenueTrendResponse:
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
        rows = (await self.session.execute(stmt)).all()

        points = [
            RevenueTrendPoint(
                period=str(r.period),
                revenue=r.rev,
                orders_count=r.cnt,
            )
            for r in rows
        ]
        total_rev = sum(p.revenue for p in points)
        total_ord = sum(p.orders_count for p in points)

        # % изменения vs предыдущий аналогичный период
        delta = date_to - date_from
        prev_from = date_from - delta - timedelta(days=1)
        prev_to = date_from - timedelta(days=1)

        prev_stmt = select(
            func.coalesce(func.sum(Order.total_amount), 0)
        ).where(
            Order.status.in_(_COMPLETED_STATUSES),
            Order.created_at >= prev_from,
            Order.created_at < prev_to + timedelta(days=1),
            Order.is_active.is_(True),
        )
        prev_rev = await self.session.scalar(prev_stmt) or 0

        change_pct = None
        if prev_rev > 0:
            change_pct = round((total_rev - prev_rev) / prev_rev, 4)

        return RevenueTrendResponse(
            points=points,
            total_revenue=total_rev,
            total_orders=total_ord,
            change_percent=change_pct,
        )

    # --- EP-9: Aging-бакеты дебиторки (BR-7) ---

    async def get_debt_aging(self) -> DebtAgingResponse:
        # CTE: клиенты с долгом + дата последнего платежа
        last_pay = (
            select(func.max(Transaction.created_at))
            .where(
                Transaction.from_id == Account.id,
                Transaction.status == TransactionStatus.COMPLETED,
            )
            .correlate(Account)
            .scalar_subquery()
        )

        # EXTRACT(epoch ...) / 86400 — total days.
        # EXTRACT(day ...) возвращает только day-компонент
        # интервала (15 из «2 months 15 days»), не total.
        days_expr = (
            func.extract(
                "epoch",
                func.current_timestamp()
                - func.coalesce(last_pay, Account.created_at),
            )
            / 86400
        )

        bucket_label = case(
            (days_expr <= 7, "0-7 дней"),
            (days_expr <= 14, "8-14 дней"),
            (days_expr <= 30, "15-30 дней"),
            (days_expr <= 60, "31-60 дней"),
            else_="60+ дней",
        )

        stmt = (
            select(
                bucket_label.label("label"),
                func.count().label("cnt"),
                func.coalesce(func.sum(Account.balance), 0).label("amount"),
                func.min(days_expr).label("min_d"),
            )
            .where(
                Account.type == AccountType.CLIENT,
                Account.balance > 0,
                Account.user_id.not_in(_EXCLUDED_IDS),
            )
            .group_by(bucket_label)
            .order_by(func.min(days_expr))
        )
        rows = (await self.session.execute(stmt)).all()

        label_to_range = {b[0]: (b[1], b[2]) for b in _AGING_BUCKETS}

        buckets = []
        total_debt = 0
        total_debtors = 0
        for r in rows:
            rng = label_to_range.get(r.label, (0, None))
            buckets.append(
                AgingBucket(
                    label=r.label,
                    min_days=rng[0],
                    max_days=rng[1],
                    clients_count=r.cnt,
                    total_amount=r.amount,
                )
            )
            total_debt += r.amount
            total_debtors += r.cnt

        return DebtAgingResponse(
            buckets=buckets,
            total_debt=total_debt,
            total_debtors=total_debtors,
        )

    # --- EP-10: Топ должников (BR-8) ---

    async def get_top_debtors(self, limit: int = 10) -> TopDebtorsResponse:
        last_pay = (
            select(func.max(Transaction.created_at).cast(Date))
            .where(
                Transaction.from_id == Account.id,
                Transaction.status == TransactionStatus.COMPLETED,
            )
            .correlate(Account)
            .scalar_subquery()
        )

        # EXTRACT(epoch ...) / 86400 — total days.
        # EXTRACT(day ...) возвращает только day-компонент
        # интервала (15 из «2 months 15 days»), не total.
        days_expr = (
            func.extract(
                "epoch",
                func.current_timestamp()
                - func.coalesce(last_pay, Account.created_at),
            )
            / 86400
        ).cast(Integer)

        stmt = (
            select(
                Account.user_id.label("cid"),
                User.username.label("cname"),
                User.role.label("ctype"),
                Account.balance.label("debt"),
                last_pay.label("last_pay"),
                days_expr.label("days"),
            )
            .join(User, Account.user_id == User.id)
            .where(
                Account.type == AccountType.CLIENT,
                Account.balance > 0,
                Account.user_id.not_in(_EXCLUDED_IDS),
            )
            .order_by(Account.balance.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()

        # Телефон — через Identity (первый provider_identity_id)
        # Для dashboard достаточно без телефона,
        # т.к. User.phone — property через lazy relationship.
        # Вместо N+1 запросов возвращаем None.
        debtors = [
            TopDebtorItem(
                client_id=r.cid,
                client_name=r.cname,
                client_type=r.ctype,
                phone=None,
                debt_amount=r.debt,
                last_payment_date=r.last_pay,
                days_overdue=r.days or 0,
            )
            for r in rows
        ]

        total_stmt = select(func.coalesce(func.sum(Account.balance), 0)).where(
            Account.type == AccountType.CLIENT,
            Account.balance > 0,
            Account.user_id.not_in(_EXCLUDED_IDS),
        )
        total_debt = await self.session.scalar(total_stmt) or 0

        return TopDebtorsResponse(
            debtors=debtors,
            total_debt=total_debt,
        )

    # --- EP-12: Финансовые KPI (BR-9) ---

    async def get_summary_kpis(
        self,
        date_from: date,
        date_to: date,
    ) -> FinanceSummaryKPIs:
        end = date_to + timedelta(days=1)

        # AOV + revenue
        order_stmt = select(
            func.count().label("cnt"),
            func.coalesce(func.sum(Order.total_amount), 0).label("rev"),
        ).where(
            Order.status.in_(_COMPLETED_STATUSES),
            Order.created_at >= date_from,
            Order.created_at < end,
            Order.is_active.is_(True),
        )
        o = (await self.session.execute(order_stmt)).one()
        aov = o.rev // o.cnt if o.cnt > 0 else 0

        # Карточные платежи
        card_stmt = (
            select(
                func.count().label("total"),
                func.count()
                .filter(Transaction.status == TransactionStatus.COMPLETED)
                .label("confirmed"),
                func.count()
                .filter(Transaction.status == TransactionStatus.REJECTED)
                .label("rejected"),
                func.avg(
                    func.extract(
                        "epoch",
                        Transaction.updated_at - Transaction.created_at,
                    )
                    / 3600
                )
                .filter(Transaction.status == TransactionStatus.COMPLETED)
                .label("avg_h"),
            )
            .join(
                Account,
                Transaction.to_id == Account.id,
            )
            .where(
                Account.type == AccountType.CARD,
                Transaction.created_at >= date_from,
                Transaction.created_at < end,
            )
        )
        c = (await self.session.execute(card_stmt)).one()
        card_total = c.total or 0
        conf_rate = (c.confirmed / card_total) if card_total > 0 else 0.0
        rej_rate = (c.rejected / card_total) if card_total > 0 else 0.0

        # Инкассация курьеров — два отдельных запроса,
        # чтобы избежать OR-join (cartesian explosion).
        _courier_ids = (
            select(Account.id)
            .where(Account.type == AccountType.COURIER)
            .scalar_subquery()
        )
        _period = [
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.created_at >= date_from,
            Transaction.created_at < end,
        ]

        collected_stmt = select(
            func.coalesce(func.sum(Transaction.amount), 0)
        ).where(
            Transaction.to_id.in_(_courier_ids),
            *_period,
        )
        deposited_stmt = select(
            func.coalesce(func.sum(Transaction.amount), 0)
        ).where(
            Transaction.from_id.in_(_courier_ids),
            *_period,
        )
        collected = await self.session.scalar(collected_stmt) or 0
        deposited = await self.session.scalar(deposited_stmt) or 0
        coll_rate = (deposited / collected) if collected > 0 else 0.0

        # Просроченная задолженность (>7 дней)
        last_pay_sub = (
            select(func.max(Transaction.created_at))
            .where(
                Transaction.from_id == Account.id,
                Transaction.status == TransactionStatus.COMPLETED,
            )
            .correlate(Account)
            .scalar_subquery()
        )
        days_sub = (
            func.extract(
                "epoch",
                func.current_timestamp()
                - func.coalesce(last_pay_sub, Account.created_at),
            )
            / 86400
        )

        debt_stmt = select(
            func.coalesce(func.sum(Account.balance), 0).label("total"),
            func.coalesce(
                func.sum(Account.balance).filter(days_sub > 7),
                0,
            ).label("overdue"),
        ).where(
            Account.type == AccountType.CLIENT,
            Account.balance > 0,
            Account.user_id.not_in(_EXCLUDED_IDS),
        )
        d = (await self.session.execute(debt_stmt)).one()
        overdue_ratio = (d.overdue / d.total) if d.total > 0 else 0.0

        return FinanceSummaryKPIs(
            avg_order_value=aov,
            total_orders=o.cnt,
            total_revenue=o.rev,
            card_confirmation_rate=round(conf_rate, 4),
            card_rejection_rate=round(rej_rate, 4),
            avg_card_confirmation_hours=(
                round(c.avg_h, 2) if c.avg_h else None
            ),
            collection_rate=round(coll_rate, 4),
            overdue_debt_ratio=round(overdue_ratio, 4),
        )

    # --- EP-21: Выручка B2B/B2C (BR-20) ---

    async def get_revenue_by_segment(
        self,
        date_from: date,
        date_to: date,
    ) -> RevenueBySegmentResponse:
        end = date_to + timedelta(days=1)
        stmt = (
            select(
                User.role.label("segment"),
                func.count().label("cnt"),
                func.coalesce(func.sum(Order.total_amount), 0).label("rev"),
            )
            .join(User, Order.client_id == User.id)
            .where(
                Order.status.in_(_COMPLETED_STATUSES),
                Order.created_at >= date_from,
                Order.created_at < end,
                Order.is_active.is_(True),
                User.id.not_in(_EXCLUDED_IDS),
                User.role.in_([Role.CLIENT_B2B, Role.CLIENT_B2C]),
            )
            .group_by(User.role)
        )
        rows = (await self.session.execute(stmt)).all()

        segments = [
            SegmentRevenue(
                segment=r.segment,
                orders_count=r.cnt,
                total_revenue=r.rev,
                avg_order_value=(r.rev // r.cnt if r.cnt > 0 else 0),
            )
            for r in rows
        ]

        return RevenueBySegmentResponse(
            segments=segments,
            total_orders=sum(s.orders_count for s in segments),
            total_revenue=sum(s.total_revenue for s in segments),
        )

    # --- EP-11: Способы оплаты — фин. призма (BR-5) ---

    async def get_payment_methods(
        self,
        date_from: date,
        date_to: date,
    ) -> PaymentMethodsFinanceResponse:
        end = date_to + timedelta(days=1)
        stmt = (
            select(
                Order.payment_method.label("method"),
                func.count().label("cnt"),
                func.coalesce(func.sum(Order.total_amount), 0).label("amount"),
            )
            .where(
                Order.status.in_(_COMPLETED_STATUSES),
                Order.created_at >= date_from,
                Order.created_at < end,
                Order.is_active.is_(True),
            )
            .group_by(Order.payment_method)
        )
        rows = (await self.session.execute(stmt)).all()

        return PaymentMethodsFinanceResponse(
            methods=[
                PaymentMethodFinanceStats(
                    method=r.method,
                    transactions_count=r.cnt,
                    total_amount=r.amount,
                )
                for r in rows
            ]
        )
