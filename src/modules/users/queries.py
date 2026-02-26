# src/modules/users/queries.py
from collections import defaultdict

from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.catalog.models import Product, ProductType
from src.modules.finances.models import Account, AccountType
from src.modules.logistics.inventory.enums import InventoryType
from src.modules.logistics.inventory.models import Inventory, StockTransaction
from src.modules.users.models import AuthProvider, Identity, Role, User
from src.modules.users.schemas import (
    InventoryProduct,
    UsersDashboard,
    UsersDashboardResponse,
)


class UsersDashboardQuery:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_clients(
        self, skip: int = 0, limit: int = 50
    ) -> UsersDashboardResponse:
        # ЗАПРОС 1: Пагинация
        users_stmt = select(
            User.id, User.full_name, User.role
        )  # full_name уже тут
        users_stmt = users_stmt.where(
            User.role.in_([Role.CLIENT_B2B, Role.CLIENT_B2C])
        )
        count_stmt = select(func.count()).select_from(users_stmt.subquery())
        total_count = await self.session.scalar(count_stmt) or 0

        if total_count == 0:
            return UsersDashboardResponse(total_count=0, users=[])

        users_page = (
            users_stmt.offset(skip).limit(limit).subquery("users_page")
        )

        phone_subq = (
            select(Identity.provider_identity_id)
            .where(
                Identity.user_id == users_page.c.id,
                Identity.provider == AuthProvider.LOCAL,
            )
            .limit(1)
            .scalar_subquery()
        )

        balance_subq = (
            select(Account.balance)
            .where(
                Account.user_id == users_page.c.id,
                Account.type == AccountType.CLIENT,
            )
            .limit(1)
            .scalar_subquery()
        )

        stmt = select(
            users_page.c.id,
            users_page.c.full_name,
            users_page.c.role,
            phone_subq.label("phone"),
            func.coalesce(balance_subq, 0).label("balance"),
        )
        users_result = await self.session.execute(stmt)
        users_data = users_result.mappings().all()

        user_ids = [u["id"] for u in users_data]
        if not user_ids:
            return UsersDashboardResponse(total_count=total_count, users=[])

        # ЗАПРОС 2: Склад (Только контейнеры)
        user_balconies_stmt = (
            select(Inventory.id.label("inv_id"), Inventory.user_id).where(
                Inventory.user_id.in_(user_ids),
                Inventory.type == InventoryType.CLIENT_BALCONY,
            )
        ).subquery("user_balconies")

        incoming = select(
            StockTransaction.to_id.label("inv_id"),
            StockTransaction.product_id,
            StockTransaction.quantity,
        )
        outgoing = select(
            StockTransaction.from_id.label("inv_id"),
            StockTransaction.product_id,
            -StockTransaction.quantity,
        )
        ledger = union_all(incoming, outgoing).subquery("ledger")

        balances = (
            select(
                user_balconies_stmt.c.user_id,
                ledger.c.product_id,
                func.sum(ledger.c.quantity).label("quantity"),
            )
            .join(
                user_balconies_stmt,
                user_balconies_stmt.c.inv_id == ledger.c.inv_id,
            )
            .group_by(user_balconies_stmt.c.user_id, ledger.c.product_id)
            .having(func.sum(ledger.c.quantity) != 0)
        ).subquery("balances")

        inv_stmt = (
            select(
                balances.c.user_id,
                Product.type,  # ДОБАВЛЕНО: Тип продукта
                Product.name,
                Product.attributes,
                balances.c.quantity,
            )
            .join(Product, Product.id == balances.c.product_id)
            .where(Product.type == ProductType.CONTAINER)
        )
        inv_result = await self.session.execute(inv_stmt)
        inv_data = inv_result.mappings().all()

        # ЭТАП 3: Сшивание
        inventory_by_user = defaultdict(list)
        for row in inv_data:
            product = InventoryProduct(
                type=row["type"],  # МАППИНГ ТИПА
                name=row["name"],
                attributes=row["attributes"],
                quantity=row["quantity"],
            )
            inventory_by_user[row["user_id"]].append(product)

        final_users = [
            UsersDashboard(
                id=u["id"],
                full_name=u["full_name"],  # ДОБАВЛЕНО: Имя
                phone=u["phone"] or "Нет телефона",
                role=u["role"],
                balance=u["balance"],
                inventory=inventory_by_user.get(u["id"], []),
            )
            for u in users_data
        ]

        return UsersDashboardResponse(
            total_count=total_count, users=final_users
        )

    async def get_couriers(
        self, skip: int = 0, limit: int = 50
    ) -> UsersDashboardResponse:
        # ЗАПРОС 1: Пагинация курьеров
        users_stmt = select(User.id, User.full_name, User.role).where(
            User.role == Role.COURIER
        )
        count_stmt = select(func.count()).select_from(users_stmt.subquery())
        total_count = await self.session.scalar(count_stmt) or 0

        if total_count == 0:
            return UsersDashboardResponse(total_count=0, users=[])

        users_page = (
            users_stmt.offset(skip).limit(limit).subquery("users_page")
        )

        phone_subq = (
            select(Identity.provider_identity_id)
            .where(
                Identity.user_id == users_page.c.id,
                Identity.provider == AuthProvider.LOCAL,
            )
            .limit(1)
            .scalar_subquery()
        )

        balance_subq = (
            select(Account.balance)
            .where(
                Account.user_id == users_page.c.id,
                Account.type == AccountType.COURIER,
            )
            .limit(1)
            .scalar_subquery()
        )

        stmt = select(
            users_page.c.id,
            users_page.c.full_name,
            users_page.c.role,
            phone_subq.label("phone"),
            func.coalesce(balance_subq, 0).label("balance"),
        )
        users_result = await self.session.execute(stmt)
        users_data = users_result.mappings().all()

        user_ids = [u["id"] for u in users_data]
        if not user_ids:
            return UsersDashboardResponse(total_count=total_count, users=[])

        # ЗАПРОС 2: Расчет склада курьеров
        user_cars_stmt = (
            select(Inventory.id.label("inv_id"), Inventory.user_id).where(
                Inventory.user_id.in_(user_ids),
                Inventory.type == InventoryType.COURIER_CAR,
            )
        ).subquery("user_cars")

        incoming = select(
            StockTransaction.to_id.label("inv_id"),
            StockTransaction.product_id,
            StockTransaction.quantity,
        )
        outgoing = select(
            StockTransaction.from_id.label("inv_id"),
            StockTransaction.product_id,
            -StockTransaction.quantity,
        )
        ledger = union_all(incoming, outgoing).subquery("ledger")

        balances = (
            select(
                user_cars_stmt.c.user_id,
                ledger.c.product_id,
                func.sum(ledger.c.quantity).label("quantity"),
            )
            .join(user_cars_stmt, user_cars_stmt.c.inv_id == ledger.c.inv_id)
            .group_by(user_cars_stmt.c.user_id, ledger.c.product_id)
            .having(func.sum(ledger.c.quantity) != 0)
        ).subquery("balances")

        inv_stmt = (
            select(
                balances.c.user_id,
                Product.id.label("product_id"),  # Нужен для идентификации тары
                Product.type,
                Product.name,
                Product.attributes,
                Product.returnable_item_id,  # ДОБАВЛЕНО: Для логики вычитания
                balances.c.quantity,
            ).join(Product, Product.id == balances.c.product_id)
            # У курьера забираем всё (и воду, и тару, и оборудование)
        )
        inv_result = await self.session.execute(inv_stmt)
        inv_data = inv_result.mappings().all()

        # ==========================================================
        # ЭТАП 3: Умное Сшивание (Вычитаем воду из тар)
        # ==========================================================
        raw_inventory_by_user = defaultdict(list)
        occupied_containers_by_user = defaultdict(lambda: defaultdict(int))

        for row in inv_data:
            raw_inventory_by_user[row["user_id"]].append(row)
            if row["type"] == ProductType.WATER and row["returnable_item_id"]:
                occupied_containers_by_user[row["user_id"]][
                    row["returnable_item_id"]
                ] += row["quantity"]

        inventory_by_user = defaultdict(list)

        for user_id, items in raw_inventory_by_user.items():
            occupied_containers = occupied_containers_by_user[user_id]

            for item in items:
                qty = item["quantity"]

                # Если это Тара, вычитаем из неё количество "занятых" тар
                if item["type"] == ProductType.CONTAINER:
                    qty -= occupied_containers.get(item["product_id"], 0)

                qty = max(0, qty)

                # Выводим в список только если количество больше нуля
                if qty > 0:
                    product = InventoryProduct(
                        type=item["type"],
                        name=item["name"],
                        attributes=item["attributes"],
                        quantity=qty,
                    )
                    inventory_by_user[user_id].append(product)

        # Собираем финальный ответ
        final_users = [
            UsersDashboard(
                id=u["id"],
                full_name=u["full_name"],  # ДОБАВЛЕНО: Имя
                phone=u["phone"] or "Нет телефона",
                role=u["role"],
                balance=u["balance"],
                inventory=inventory_by_user.get(u["id"], []),
            )
            for u in users_data
        ]

        return UsersDashboardResponse(
            total_count=total_count, users=final_users
        )
