# src/modules/logistics/repositories.py
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Result, RowMapping, func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select, Subquery

from src.common.repository import BaseRepository
from src.modules.catalog.models import Product
from src.modules.logistics.inventory.enums import InventoryType
from src.modules.logistics.inventory.models import (
    Inventory,
    StockTransaction,
)


class InventoryRepository(BaseRepository[Inventory]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Inventory, session=session)

    async def get_all_by_type(
        self, inventory_type: InventoryType
    ) -> Sequence[Inventory]:
        self.get_multi_by(type=inventory_type)
        query: Select[tuple[Inventory]] = select(Inventory).where(
            Inventory.type == inventory_type,
            Inventory.is_active.is_(other=True),
        )
        result: Result[Any] = await self.session.execute(statement=query)
        return list(result.scalars().all())

    async def get_all_by_user(self, user_id: uuid.UUID) -> Sequence[Inventory]:
        query: Select[tuple[Inventory]] = select(Inventory).where(
            Inventory.user_id == user_id,
            Inventory.is_active.is_(other=True),
        )
        result: Result[Any] = await self.session.execute(statement=query)
        return list(result.scalars().all())

    async def get_all_by_user_and_type(
        self, user_id: uuid.UUID, inventory_type: InventoryType
    ) -> Sequence[Inventory]:
        query: Select[tuple[Inventory]] = select(Inventory).where(
            Inventory.user_id == user_id,
            Inventory.type == inventory_type,
            Inventory.is_active.is_(other=True),
        )
        result: Result[Any] = await self.session.execute(statement=query)
        return list(result.scalars().all())

    async def get_by_user_and_type(
        self, user_id: uuid.UUID, inventory_type: InventoryType
    ) -> Inventory | None:
        query: Select[tuple[Inventory]] = select(Inventory).where(
            Inventory.user_id == user_id,
            Inventory.type == inventory_type,
            Inventory.is_active.is_(other=True),
        )
        result: Result[Any] = await self.session.execute(statement=query)
        return result.scalar_one_or_none()

    async def get_factory_inventory(
        self, system_user_id: uuid.UUID
    ) -> Inventory:
        query = select(self.model).where(
            self.model.user_id == system_user_id,
            self.model.type == InventoryType.FACTORY,
            self.model.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_warehouse_inventory(
        self, system_user_id: uuid.UUID
    ) -> Inventory:
        query = select(self.model).where(
            self.model.user_id == system_user_id,
            self.model.type == InventoryType.WAREHOUSE,
            self.model.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_courier_inventory(
        self, courier_id: uuid.UUID
    ) -> Inventory | None:
        return await self.get_by_user_and_type(
            user_id=courier_id, inventory_type=InventoryType.COURIER_CAR
        )

    async def get_client_balcony(
        self, client_id: uuid.UUID
    ) -> Inventory | None:
        return await self.get_by_user_and_type(
            user_id=client_id, inventory_type=InventoryType.CLIENT_BALCONY
        )

    async def get_inventories_with_balances(
        self, inventory_type: InventoryType
    ) -> Sequence[RowMapping]:
        target_inventories: Select[tuple[uuid.UUID]] = select(
            Inventory.id
        ).where(
            Inventory.type == inventory_type, Inventory.is_active.is_(True)
        )

        incoming = select(
            StockTransaction.to_id.label("inventory_id"),
            StockTransaction.product_id,
            StockTransaction.quantity,
        ).where(StockTransaction.to_id.in_(target_inventories))

        outgoing = select(
            StockTransaction.from_id.label("inventory_id"),
            StockTransaction.product_id,
            -StockTransaction.quantity,
        ).where(StockTransaction.from_id.in_(target_inventories))

        ledger: Subquery = union_all(incoming, outgoing).subquery("ledger")

        balances: Subquery = (
            select(
                ledger.c.inventory_id,
                ledger.c.product_id,
                func.sum(ledger.c.quantity).label("balance"),
            )
            .group_by(ledger.c.inventory_id, ledger.c.product_id)
            .having(func.sum(ledger.c.quantity) != 0)
        ).subquery("balances")

        final_query = (
            select(
                Inventory,
                Product,
                balances.c.balance,
            )
            .select_from(Inventory)
            .outerjoin(balances, Inventory.id == balances.c.inventory_id)
            .outerjoin(Product, balances.c.product_id == Product.id)
            .where(
                Inventory.type == inventory_type, Inventory.is_active.is_(True)
            )
            .order_by(Inventory.name, Product.type, Product.name)
        )

        result: Result[Any] = await self.session.execute(final_query)
        return result.mappings().all()

    async def get_courier_inventories_with_balances(
        self,
    ) -> Sequence[RowMapping]:
        return await self.get_inventories_with_balances(
            inventory_type=InventoryType.COURIER_CAR
        )

    async def get_client_inventories_with_balances(
        self,
    ) -> Sequence[RowMapping]:
        return await self.get_inventories_with_balances(
            inventory_type=InventoryType.CLIENT_BALCONY
        )

    async def get_inventory_balances(
        self, inventory_id: uuid.UUID
    ) -> list[RowMapping]:

        incoming = select(
            StockTransaction.product_id, StockTransaction.quantity
        ).where(StockTransaction.to_id == inventory_id)

        outgoing = select(
            StockTransaction.product_id, -StockTransaction.quantity
        ).where(StockTransaction.from_id == inventory_id)

        ledger = union_all(incoming, outgoing).subquery("ledger")

        balances = (
            select(
                ledger.c.product_id,
                func.sum(ledger.c.quantity).label("balance"),
            )
            .group_by(ledger.c.product_id)
            .having(func.sum(ledger.c.quantity) != 0)
        ).subquery("balances")

        final_query = (
            select(
                balances.c.product_id,
                Product.name,
                Product.type,
                Product.attributes,
                balances.c.balance,
            )
            .join(Product, balances.c.product_id == Product.id)
            .order_by(Product.type, Product.name)
        )
        result: Result[Any] = await self.session.execute(final_query)

        return list(result.mappings().all())


class StockTransactionRepository(BaseRepository[StockTransaction]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=StockTransaction, session=session)

    async def get_by_order_id(
        self, order_id: uuid.UUID
    ) -> Sequence[StockTransaction]:
        """
        Получить все движения тары по конкретному заказу (для аудита и отмен).
        """
        query = select(StockTransaction).where(
            StockTransaction.order_id == order_id
        )
        result: Result[Any] = await self.session.execute(query)
        return result.scalars().all()

    async def get_inventory_history(
        self, inventory_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> Sequence[StockTransaction]:
        """
        История перемещений по конкретному складу/машине курьера.
        """
        query = (
            select(StockTransaction)
            .where(
                or_(
                    StockTransaction.from_id == inventory_id,
                    StockTransaction.to_id == inventory_id,
                )
            )
            .order_by(StockTransaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result: Result[Any] = await self.session.execute(query)
        return result.scalars().all()
