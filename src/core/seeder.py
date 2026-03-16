# src/core/seeder.py
import asyncio
import uuid
from typing import Any, cast

import structlog
from sqlalchemy import select

from src.core.security.password import get_password_hash
from src.infrastructure.database.models import (
    Account,
    Identity,
    Inventory,
    Product,
    StockTransfer,
    User,
)
from src.infrastructure.database.session import async_session_maker
from src.modules.catalog.enums import ProductType
from src.modules.finances.enums import AccountType
from src.modules.inventory.enums import InventoryType, TransferStatus, TransferType
from src.modules.orders.enums import OrderStatus, PaymentMethod
from src.modules.users.enums import AuthProvider, Role

logger = structlog.get_logger(__name__)


class Seeder:
    def __init__(self):
        self.session_factory = async_session_maker
        self.products = {}
        self.users = {}
        self.inventories = {}

    async def seed_all(self):
        logger.info("Starting database seeding...")
        await self.seed_products()
        await self.seed_warehouses()
        await self.seed_users()
        await self.seed_stock_movements()
        await self.seed_orders()
        logger.info("Seeding completed successfully!")

    async def seed_products(self):
        logger.info("Step 1: Seeding products...")
        async with self.session_factory() as session:
            # 1. Containers
            containers_data = [
                {"name": "[MOCK] Тара Hayot 19Л", "price": 50000},
                {"name": "[MOCK] Тара MunavvarA 18.9Л", "price": 50000},
            ]
            for c_data in containers_data:
                existing = await session.execute(
                    select(Product).where(Product.name == c_data["name"])
                )
                if not existing.scalars().first():
                    product = Product(
                        name=c_data["name"],
                        type=ProductType.CONTAINER,
                        price=c_data["price"],
                        is_active=True,
                    )
                    session.add(product)
            await session.flush()

            # Map containers for water links
            all_prods = (await session.execute(select(Product))).scalars().all()
            prod_map = {p.name: p for p in all_prods}

            # 2. Water (linked to containers)
            water_data = [
                {
                    "name": "[MOCK] Вода Hayot 19Л",
                    "price": 20000,
                    "container": "[MOCK] Тара Hayot 19Л",
                },
                {
                    "name": "[MOCK] Вода MunavvarA 18.9Л",
                    "price": 25000,
                    "container": "[MOCK] Тара MunavvarA 18.9Л",
                },
            ]
            for w_data in water_data:
                existing = await session.execute(
                    select(Product).where(Product.name == w_data["name"])
                )
                if not existing.scalars().first():
                    container = prod_map.get(w_data["container"])
                    product = Product(
                        name=w_data["name"],
                        type=ProductType.WATER,
                        price=w_data["price"],
                        returnable_item_id=container.id if container else None,
                        is_active=True,
                    )
                    session.add(product)

            # 3. Equipment
            equipment_data = [{"name": "[MOCK] Помпа механическая", "price": 15000}]
            for e_data in equipment_data:
                existing = await session.execute(
                    select(Product).where(Product.name == e_data["name"])
                )
                if not existing.scalars().first():
                    product = Product(
                        name=e_data["name"],
                        type=ProductType.EQUIPMENT,
                        price=e_data["price"],
                        is_active=True,
                    )
                    session.add(product)

            await session.commit()

            # Populate total mapping
            all_final = (await session.execute(select(Product))).scalars().all()
            for p in all_final:
                self.products[p.name] = p.id

            logger.info(f"Products seeded. Total in map: {len(self.products)}")

    async def seed_warehouses(self):
        logger.info("Step 2: Seeding warehouses...")
        async with self.session_factory() as session:
            # Get System User
            system_user = (
                await session.execute(select(User).where(User.role == Role.SYSTEM))
            ).scalar_one()

            # Ensure Virtual Warehouses exist
            vendor = (
                await session.execute(
                    select(Inventory).where(
                        Inventory.type == InventoryType.VIRTUAL_VENDOR
                    )
                )
            ).scalar_one_or_none()
            if not vendor:
                vendor = Inventory(
                    user_id=system_user.id,
                    name="VIRTUAL_VENDOR",
                    type=InventoryType.VIRTUAL_VENDOR,
                )
                session.add(vendor)

            loss = (
                await session.execute(
                    select(Inventory).where(
                        Inventory.type == InventoryType.VIRTUAL_LOSS
                    )
                )
            ).scalar_one_or_none()
            if not loss:
                loss = Inventory(
                    user_id=system_user.id,
                    name="VIRTUAL_LOSS",
                    type=InventoryType.VIRTUAL_LOSS,
                )
                session.add(loss)

            # Create Mock Main Warehouse
            main_warehouse = (
                await session.execute(
                    select(Inventory).where(Inventory.name == "[MOCK] Главный Склад")
                )
            ).scalar_one_or_none()
            if not main_warehouse:
                main_warehouse = Inventory(
                    user_id=system_user.id,
                    name="[MOCK] Главный Склад",
                    type=InventoryType.WAREHOUSE,
                )
                session.add(main_warehouse)

            await session.commit()

            # Refresh inventories mapping reliably
            all_invs = (await session.execute(select(Inventory))).scalars().all()
            for inv in all_invs:
                if inv.type == InventoryType.VIRTUAL_VENDOR:
                    self.inventories["vendor"] = inv.id
                elif inv.name == "[MOCK] Главный Склад":
                    self.inventories["main"] = inv.id

            logger.info("Warehouses seeded.")

    async def seed_users(self):
        logger.info("Step 3: Seeding users and their inventories...")
        async with self.session_factory() as session:
            password_hash = get_password_hash("password123")

            # Couriers
            couriers_data = [
                ("+998000000002", "[MOCK] Курьер Азиз", "[MOCK] Машина 01-A"),
                ("+998000000003", "[MOCK] Курьер Бобур", "[MOCK] Машина 02-B"),
                ("+998000000004", "[MOCK] Курьер Тимур", "[MOCK] Машина 03-C"),
            ]

            for phone, name, car in couriers_data:
                existing = (
                    await session.execute(
                        select(User)
                        .join(Identity)
                        .where(Identity.provider_identity_id == phone)
                    )
                ).scalar_one_or_none()
                if not existing:
                    user = User(username=name, role=Role.COURIER, is_active=True)
                    session.add(user)
                    await session.flush()

                    identity = Identity(
                        user_id=user.id,
                        provider=AuthProvider.LOCAL,
                        provider_identity_id=phone,
                        password_hash=password_hash,
                    )
                    session.add(identity)
                    account = Account(
                        user_id=user.id,
                        type=AccountType.COURIER,
                        name=f"Касса {name}",
                    )
                    session.add(account)
                    inventory = Inventory(
                        user_id=user.id, name=car, type=InventoryType.COURIER
                    )
                    session.add(inventory)
                    await session.flush()

            # Clients
            clients_data = [
                ("+998000000011", "[MOCK] Иван Иванов", Role.CLIENT_B2C),
                ("+998000000012", "[MOCK] Петр Петров", Role.CLIENT_B2C),
                ("+998000000013", "[MOCK] Офис IT", Role.CLIENT_B2B),
                ("+998000000014", "[MOCK] Анна Смирнова", Role.CLIENT_B2C),
                ("+998000000015", "[MOCK] Ресторан Чайхона", Role.CLIENT_B2B),
            ]

            for phone, name, role in clients_data:
                existing = (
                    await session.execute(
                        select(User)
                        .join(Identity)
                        .where(Identity.provider_identity_id == phone)
                    )
                ).scalar_one_or_none()
                if not existing:
                    user = User(username=name, role=role, is_active=True)
                    session.add(user)
                    await session.flush()

                    identity = Identity(
                        user_id=user.id,
                        provider=AuthProvider.LOCAL,
                        provider_identity_id=phone,
                        password_hash=password_hash,
                    )
                    session.add(identity)

                    account = Account(
                        user_id=user.id,
                        type=AccountType.CLIENT,
                        name=f"Cчёт клиента {name}",
                    )
                    session.add(account)
                    inventory = Inventory(
                        user_id=user.id,
                        name=f"Inventory for {name}",
                        type=InventoryType.CLIENT,
                    )
                    session.add(inventory)
                    await session.flush()

            await session.commit()

            # Robust population of user/inventory mappings
            all_u = (
                await session.execute(
                    select(User, Identity.provider_identity_id).join(User.identities)
                )
            ).all()
            for u_rec, phone in all_u:
                self.users[phone] = u_rec.id

            all_inv = (
                await session.execute(
                    select(Inventory, User.username, Identity.provider_identity_id)
                    .join(Inventory.user)
                    .join(User.identities)
                )
            ).all()
            for inv_rec, _, phone in all_inv:
                self.inventories[phone] = inv_rec.id

            logger.info(f"Users seeded. Total in maps: {len(self.users)}")

    async def _create_transfer(
        self,
        from_inv_id: uuid.UUID,
        to_inv_id: uuid.UUID,
        items: dict,
        session,
        status=TransferStatus.COMPLETED,
    ):
        from src.infrastructure.database.models import (
            StockTransaction,
            StockTransferItem,
        )

        system_user = (
            await session.execute(select(User).where(User.role == Role.SYSTEM))
        ).scalar_one()

        transfer = StockTransfer(
            from_id=from_inv_id,
            to_id=to_inv_id,
            type=TransferType.FACTORY_RECEIPT,
            status=status,
            created_by_id=system_user.id,
        )
        session.add(transfer)
        await session.flush()

        for product_name, qty in items.items():
            product_id = self.products.get(product_name)
            if not product_id:
                res = await session.execute(
                    select(Product).where(Product.name == product_name)
                )
                p = res.scalars().first()
                if p:
                    product_id = p.id
                    self.products[product_name] = p.id
                else:
                    raise KeyError(f"Product '{product_name}' does not exist")

            item = StockTransferItem(
                transfer_id=transfer.id, product_id=product_id, quantity=qty
            )
            session.add(item)

            if status == TransferStatus.COMPLETED:
                transaction = StockTransaction(
                    product_id=product_id,
                    transfer_id=transfer.id,
                    from_id=from_inv_id,
                    to_id=to_inv_id,
                    quantity=qty,
                )
                session.add(transaction)

        await session.flush()

    async def seed_stock_movements(self):
        logger.info("Step 4: Seeding stock movements...")
        async with self.session_factory() as session:
            # 1. Vendor -> Main Warehouse
            await self._create_transfer(
                self.inventories["vendor"],
                self.inventories["main"],
                {
                    "[MOCK] Вода Hayot 19Л": 500,
                    "[MOCK] Тара Hayot 19Л": 500,
                    "[MOCK] Вода MunavvarA 18.9Л": 500,
                    "[MOCK] Тара MunavvarA 18.9Л": 500,
                    "[MOCK] Помпа механическая": 50,
                },
                session,
            )

            # 2. Vendor -> Clients (Existing bottles)
            client_initial_bottles = {
                "+998000000011": {"[MOCK] Тара Hayot 19Л": 2},
                "+998000000013": {"[MOCK] Тара MunavvarA 18.9Л": 10},
                "+998000000014": {"[MOCK] Тара Hayot 19Л": 1},
                "+998000000015": {
                    "[MOCK] Тара MunavvarA 18.9Л": 15,
                    "[MOCK] Тара Hayot 19Л": 5,
                },
            }
            for phone, items in client_initial_bottles.items():
                await self._create_transfer(
                    self.inventories["vendor"],
                    self.inventories[phone],
                    items,
                    session,
                )

            # 3. Main Warehouse -> Couriers
            await self._create_transfer(
                self.inventories["main"],
                self.inventories["+998000000002"],
                {"[MOCK] Вода Hayot 19Л": 50, "[MOCK] Вода MunavvarA 18.9Л": 20},
                session,
            )
            await self._create_transfer(
                self.inventories["main"],
                self.inventories["+998000000003"],
                {"[MOCK] Вода MunavvarA 18.9Л": 40, "[MOCK] Вода Hayot 19Л": 10},
                session,
            )

            await session.commit()

    async def seed_orders(self):
        logger.info("Step 5: Seeding orders...")
        from src.infrastructure.database.models import Order, OrderItem

        async with self.session_factory() as session:
            orders_data: list[dict[str, Any]] = [
                {
                    "client_phone": "+998000000012",
                    "status": OrderStatus.NEW,
                    "items": [
                        {"name": "[MOCK] Вода Hayot 19Л", "qty": 2},
                        {"name": "[MOCK] Тара Hayot 19Л", "qty": 2},
                    ],
                },
                {
                    "client_phone": "+998000000011",
                    "status": OrderStatus.IN_TRANSIT,
                    "courier_phone": "+998000000002",
                    "items": [{"name": "[MOCK] Вода Hayot 19Л", "qty": 2}],
                },
                {
                    "client_phone": "+998000000013",
                    "status": OrderStatus.DELIVERED,
                    "courier_phone": "+998000000003",
                    "items": [{"name": "[MOCK] Вода MunavvarA 18.9Л", "qty": 10}],
                },
                {
                    "client_phone": "+998000000014",
                    "status": OrderStatus.NEW,
                    "items": [
                        {"name": "[MOCK] Вода Hayot 19Л", "qty": 1},
                        {"name": "[MOCK] Помпа механическая", "qty": 1},
                    ],
                },
                {
                    "client_phone": "+998000000015",
                    "status": OrderStatus.IN_TRANSIT,
                    "courier_phone": "+998000000003",
                    "items": [{"name": "[MOCK] Вода MunavvarA 18.9Л", "qty": 15}],
                },
            ]

            for o_data in orders_data:
                client_id = self.users.get(o_data["client_phone"])
                if not client_id:
                    continue

                courier_id = self.users.get(o_data.get("courier_phone", ""))
                client_inv_id = self.inventories.get(o_data["client_phone"])

                order = Order(
                    client_id=client_id,
                    client_inventory_id=client_inv_id,
                    courier_id=courier_id,
                    status=o_data["status"],
                    payment_method=PaymentMethod.CASH,
                    total_amount=0,
                )
                session.add(order)
                await session.flush()

                total = 0
                items_main = cast(list[dict[str, Any]], o_data["items"])
                for it in items_main:
                    p_name = cast(str, it["name"])
                    p_id = self.products.get(p_name)
                    if not p_id:
                        continue

                    product = (
                        await session.execute(select(Product).where(Product.id == p_id))
                    ).scalar_one()

                    item = OrderItem(
                        order_id=order.id,
                        product_id=p_id,
                        quantity=cast(int, it["qty"]),
                        unit_price=product.price,
                    )
                    session.add(item)
                    total += product.price * cast(int, it["qty"])

                order.total_amount = total

                if o_data["status"] == OrderStatus.DELIVERED and courier_id:
                    await self._handle_delivered_order(session, o_data, items_main)

            await session.commit()
            logger.info("Orders seeded.")

    async def _handle_delivered_order(self, session, o_data, items_main):
        """Processes stock transfers for delivered orders during seeding."""
        c_phone = cast(str, o_data.get("courier_phone", ""))
        cl_phone = cast(str, o_data["client_phone"])

        c_inv_id = self.inventories.get(c_phone)
        cl_inv_id = self.inventories.get(cl_phone)

        if not (c_inv_id and cl_inv_id):
            return

        # 1. Courier -> Client (Filled)
        filled = {cast(str, i["name"]): cast(int, i["qty"]) for i in items_main}
        await self._create_transfer(c_inv_id, cl_inv_id, filled, session)

        # 2. Client -> Courier (Empty containers)
        empty_items = {}
        for it in items_main:
            p_name = cast(str, it["name"])
            p_id = self.products.get(p_name)
            if not p_id:
                continue

            p = (
                await session.execute(select(Product).where(Product.id == p_id))
            ).scalar_one()

            if p.type == ProductType.WATER and p.returnable_item_id:
                ret_p = (
                    await session.execute(
                        select(Product).where(Product.id == p.returnable_item_id)
                    )
                ).scalar_one()
                empty_items[ret_p.name] = cast(int, it["qty"])

        if empty_items:
            await self._create_transfer(cl_inv_id, c_inv_id, empty_items, session)


if __name__ == "__main__":
    from src.core.init import init_data

    async def run():
        await init_data()
        seeder = Seeder()
        await seeder.seed_all()

    asyncio.run(run())
