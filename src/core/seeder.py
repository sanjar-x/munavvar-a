# src/core/seeder.py
import asyncio
import uuid
from typing import Any

import structlog
from sqlalchemy import select

from src.core.security.password import get_password_hash
from src.infrastructure.database.models import (
    Identity,
    Inventory,
    Product,
    StockTransfer,
    User,
)
from src.infrastructure.database.session import async_session_maker
from src.modules.catalog.enums import ProductType
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
            # Check if products already exist to avoid duplicates
            existing = await session.execute(select(Product))
            if existing.scalars().first():
                logger.info("Products already exist, skipping...")
                for p in await session.scalars(select(Product)):
                    self.products[p.name] = p.id
                return

            # 1. Containers
            tara_hayot = Product(
                name="[MOCK] Тара Hayot 19Л",
                type=ProductType.CONTAINER,
                price=50000,  # 500 units (e.g. 50000 cents/tiyin)
                is_active=True,
            )
            tara_munavvar = Product(
                name="[MOCK] Тара MunavvarA 18.9Л",
                type=ProductType.CONTAINER,
                price=50000,
                is_active=True,
            )
            session.add_all([tara_hayot, tara_munavvar])
            await session.flush()

            # 2. Water (linked to containers)
            voda_hayot = Product(
                name="[MOCK] Вода Hayot 19Л",
                type=ProductType.WATER,
                price=20000,
                returnable_item_id=tara_hayot.id,
                is_active=True,
            )
            voda_munavvar = Product(
                name="[MOCK] Вода MunavvarA 18.9Л",
                type=ProductType.WATER,
                price=25000,
                returnable_item_id=tara_munavvar.id,
                is_active=True,
            )

            # 3. Equipment
            pompa = Product(
                name="[MOCK] Помпа механическая",
                type=ProductType.EQUIPMENT,
                price=15000,
                is_active=True,
            )

            session.add_all([voda_hayot, voda_munavvar, pompa])
            await session.commit()

            logger.info("Products seeded.")
            for p in [tara_hayot, tara_munavvar, voda_hayot, voda_munavvar, pompa]:
                self.products[p.name] = p.id

    async def seed_warehouses(self):
        logger.info("Step 2: Seeding warehouses...")
        async with self.session_factory() as session:
            # Get System User
            system_user = (
                await session.execute(select(User).where(User.role == Role.SYSTEM))
            ).scalar_one()

            # Ensure Virtual Warehouses exist (usually handled by init_data)
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
            self.inventories["vendor"] = vendor.id
            self.inventories["main"] = main_warehouse.id
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

                    inventory = Inventory(
                        user_id=user.id, name=car, type=InventoryType.COURIER
                    )
                    session.add(inventory)
                    await session.flush()
                    self.users[phone] = user.id
                    self.inventories[phone] = inventory.id
                else:
                    self.users[phone] = existing.id
                    inv = (
                        await session.execute(
                            select(Inventory).where(Inventory.user_id == existing.id)
                        )
                    ).scalar_one()
                    self.inventories[phone] = inv.id

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

                    inventory = Inventory(
                        user_id=user.id,
                        name=f"Inventory for {name}",
                        type=InventoryType.CLIENT,
                    )
                    session.add(inventory)
                    await session.flush()
                    self.users[phone] = user.id
                    self.inventories[phone] = inventory.id
                else:
                    self.users[phone] = existing.id
                    inv = (
                        await session.execute(
                            select(Inventory).where(Inventory.user_id == existing.id)
                        )
                    ).scalar_one()
                    self.inventories[phone] = inv.id

            await session.commit()
            logger.info("Users and inventories seeded.")

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

        # Get System User ID
        system_user = (
            await session.execute(select(User).where(User.role == Role.SYSTEM))
        ).scalar_one()

        transfer = StockTransfer(
            from_id=from_inv_id,
            to_id=to_inv_id,
            type=TransferType.FACTORY_RECEIPT,  # Simplified
            status=status,
            created_by_id=system_user.id,
        )
        session.add(transfer)
        await session.flush()

        for product_name, qty in items.items():
            product_id = self.products[product_name]
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
            logger.info("Stock movements seeded.")

    async def seed_orders(self):
        logger.info("Step 5: Seeding orders...")
        from src.infrastructure.database.models import Order, OrderItem

        async with self.session_factory() as session:
            orders_data = [
                # Order 1: NEW, Client 2 (Peter), 2 Water Hayot + 2 Tara Hayot
                {
                    "client_phone": "+998000000012",
                    "status": OrderStatus.NEW,
                    "items": [
                        {"name": "[MOCK] Вода Hayot 19Л", "qty": 2},
                        {"name": "[MOCK] Тара Hayot 19Л", "qty": 2},
                    ],
                },
                # Order 2: IN_PROGRESS, Client 1 (Ivan), 2 Water Hayot, Courier 1
                {
                    "client_phone": "+998000000011",
                    "status": OrderStatus.IN_TRANSIT,
                    "courier_phone": "+998000000002",
                    "items": [{"name": "[MOCK] Вода Hayot 19Л", "qty": 2}],
                },
                # Order 3: DELIVERED, Client 3 (Office IT), 10 Water MunavvarA, Courier 2
                {
                    "client_phone": "+998000000013",
                    "status": OrderStatus.DELIVERED,
                    "courier_phone": "+998000000003",
                    "items": [{"name": "[MOCK] Вода MunavvarA 18.9Л", "qty": 10}],
                },
                # Order 4: NEW, Client 4 (Anna), 1 Water Hayot + 1 Pump
                {
                    "client_phone": "+998000000014",
                    "status": OrderStatus.NEW,
                    "items": [
                        {"name": "[MOCK] Вода Hayot 19Л", "qty": 1},
                        {"name": "[MOCK] Помпа механическая", "qty": 1},
                    ],
                },
                # Order 5: IN_PROGRESS, Client 5 (Restaurant), 15 Water MunavvarA, Courier 2
                {
                    "client_phone": "+998000000015",
                    "status": OrderStatus.IN_TRANSIT,
                    "courier_phone": "+998000000003",
                    "items": [{"name": "[MOCK] Вода MunavvarA 18.9Л", "qty": 15}],
                },
                # Order 6: CANCELLED, Client 1 (Ivan), 1 Water Hayot
                {
                    "client_phone": "+998000000011",
                    "status": OrderStatus.CANCELLED,
                    "items": [{"name": "[MOCK] Вода Hayot 19Л", "qty": 1}],
                },
                # Order 7: NEW, Client 3 (Office IT), 5 Water Hayot + 5 Tara Hayot
                {
                    "client_phone": "+998000000013",
                    "status": OrderStatus.NEW,
                    "items": [
                        {"name": "[MOCK] Вода Hayot 19Л", "qty": 5},
                        {"name": "[MOCK] Тара Hayot 19Л", "qty": 5},
                    ],
                },
                # Order 8: DELIVERED, Client 5 (Restaurant), 5 Water Hayot, Courier 1
                {
                    "client_phone": "+998000000015",
                    "status": OrderStatus.DELIVERED,
                    "courier_phone": "+998000000002",
                    "items": [{"name": "[MOCK] Вода Hayot 19Л", "qty": 5}],
                },
                # Order 9: IN_PROGRESS, Client 4 (Anna), 2 Water MunavvarA + 2 Tara MunavvarA, Courier 3
                {
                    "client_phone": "+998000000014",
                    "status": OrderStatus.IN_TRANSIT,
                    "courier_phone": "+998000000004",
                    "items": [
                        {"name": "[MOCK] Вода MunavvarA 18.9Л", "qty": 2},
                        {"name": "[MOCK] Тара MunavvarA 18.9Л", "qty": 2},
                    ],
                },
                # Order 10: NEW, Client 2 (Peter), 1 Water MunavvarA + 1 Tara MunavvarA
                {
                    "client_phone": "+998000000012",
                    "status": OrderStatus.NEW,
                    "items": [
                        {"name": "[MOCK] Вода MunavvarA 18.9Л", "qty": 1},
                        {"name": "[MOCK] Тара MunavvarA 18.9Л", "qty": 1},
                    ],
                },
            ]

            for o_data in orders_data:
                client_id = self.users[o_data["client_phone"]]
                courier_id = self.users.get(o_data.get("courier_phone"))

                order = Order(
                    client_id=client_id,
                    courier_id=courier_id,
                    status=o_data["status"],
                    payment_method=PaymentMethod.CASH,
                    total_amount=0,
                )
                session.add(order)
                await session.flush()

                total = 0
                # Explicitly typing the list to resolve inference issues
                items_main: list[dict[str, Any]] = o_data["items"]  # type: ignore

                for it in items_main:
                    p_id = self.products[it["name"]]
                    product = (
                        await session.execute(select(Product).where(Product.id == p_id))
                    ).scalar_one()

                    item = OrderItem(
                        order_id=order.id,
                        product_id=p_id,
                        quantity=it["qty"],
                        unit_price=product.price,
                    )
                    session.add(item)
                    total += product.price * it["qty"]

                order.total_amount = total

                # Special logic for DELIVERED orders: create transfers (stock fulfillment)
                if o_data["status"] == OrderStatus.DELIVERED and courier_id:
                    # Courier -> Client (Filled)
                    # For simplicity, we just move items as-is in this seeder
                    # Real logic involves returnable bottles, but we follow the requirement:
                    # "Курьер отдал 5 полных, забрал 5 пустых"
                    courier_inv_id = self.inventories[o_data["courier_phone"]]
                    client_inv_id = self.inventories[o_data["client_phone"]]

                    # Explicitly typing the list to resolve inference issues
                    items_list: list[dict[str, Any]] = o_data["items"]  # type: ignore

                    filled_items = {it["name"]: it["qty"] for it in items_list}
                    await self._create_transfer(
                        courier_inv_id, client_inv_id, filled_items, session
                    )

                    # Client -> Courier (Empty)
                    # Find empty containers for each water item
                    empty_items = {}
                    for it in items_list:
                        product_id = self.products[it["name"]]
                        product = (
                            await session.execute(
                                select(Product).where(Product.id == product_id)
                            )
                        ).scalar_one()
                        if (
                            product.type == ProductType.WATER
                            and product.returnable_item_id
                        ):
                            container = (
                                await session.execute(
                                    select(Product).where(
                                        Product.id == product.returnable_item_id
                                    )
                                )
                            ).scalar_one()
                            empty_items[container.name] = it["qty"]

                    if empty_items:
                        await self._create_transfer(
                            client_inv_id, courier_inv_id, empty_items, session
                        )

            await session.commit()
            logger.info("Orders seeded.")


if __name__ == "__main__":
    from src.core.init import init_data

    async def run():
        await init_data()  # Ensure system user and base stuff exists
        seeder = Seeder()
        await seeder.seed_all()

    asyncio.run(run())
