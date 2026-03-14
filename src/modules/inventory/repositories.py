import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.common.repository import BaseRepository
from src.core.config import settings
from src.infrastructure.database.models import (
    Balance,
    Inventory,
    Product,
    StockTransaction,
    StockTransfer,
    StockTransferItem,
)
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)


class InventoryRepository(BaseRepository[Inventory]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Inventory, session=session)

    async def create_courier_inventory(
        self, user_id: uuid.UUID, inventory_name: str
    ) -> Inventory:
        return await self.add({
            "user_id": user_id,
            "type": InventoryType.COURIER,
            "name": inventory_name,
        })

    async def create_client_inventory(
        self, user_id: uuid.UUID, inventory_name: str
    ) -> Inventory:
        return await self.add({
            "user_id": user_id,
            "type": InventoryType.CLIENT,
            "name": inventory_name,
        })

    async def get_system_inventory(self, inv_type: InventoryType) -> Inventory:
        query = select(self.model).where(
            self.model.user_id == settings.SYSTEM_USER_ID, self.model.type == inv_type
        )
        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_vendor_inventory(self) -> Inventory:
        return await self.get_system_inventory(InventoryType.VIRTUAL_VENDOR)

    async def get_loss_inventory(self) -> Inventory:
        return await self.get_system_inventory(InventoryType.VIRTUAL_LOSS)

    async def get_courier_inventory(
        self,
        courier_id: uuid.UUID,
    ) -> Inventory | None:
        query = (
            select(self.model)
            .where(
                self.model.user_id == courier_id,
                self.model.type == InventoryType.COURIER,
                self.model.is_active.is_(True),
            )
            .options(selectinload(self.model.balances).joinedload(attr=Balance.product))
        )
        result = await self.session.execute(query)
        return result.unique().scalar_one_or_none()

    async def get_couriers_inventory(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Inventory]:
        query = (
            select(self.model)
            .where(
                self.model.is_active.is_(True),
                self.model.type == InventoryType.COURIER,
            )
            .options(joinedload(self.model.user))
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return result.scalars().all()

    # --- СЦЕНАРИИ КЛИЕНТА (B2C / B2B) ---

    async def get_client_inventory(
        self, user_id: uuid.UUID, inventory_id: uuid.UUID
    ) -> Inventory | None:
        query = select(self.model).where(
            self.model.id == inventory_id,
            self.model.user_id == user_id,
            self.model.type == InventoryType.CLIENT,
            self.model.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def search_inventories(
        self,
        search_query: str,
        inv_type: InventoryType | None = None,
        limit: int = 50,
    ) -> Sequence[Inventory]:
        query = select(self.model).where(
            self.model.name.ilike(f"%{search_query}%"),
            self.model.is_active.is_(True),
        )
        if inv_type:
            query = query.where(self.model.type == inv_type)

        query = query.limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_with_balances(self, inventory_id: uuid.UUID) -> Inventory | None:
        """Получить транспорт (инвентарь курьера) с актуальными остатками."""
        query = (
            select(self.model)
            .where(
                self.model.id == inventory_id,
                self.model.type == InventoryType.COURIER,
                self.model.is_active.is_(True),
            )
            .options(selectinload(self.model.balances).joinedload(Balance.product))
        )
        result = await self.session.execute(query)
        return result.unique().scalar_one_or_none()


class StockTransferItemRepository(BaseRepository[StockTransferItem]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=StockTransferItem, session=session)


class StockTransferRepository(BaseRepository[StockTransfer]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=StockTransfer, session=session)

    async def get_with_items(self, transfer_id: uuid.UUID) -> StockTransfer | None:
        query = (
            select(StockTransfer)
            .where(StockTransfer.id == transfer_id)
            .options(selectinload(StockTransfer.items))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_with_items_for_update(
        self, transfer_id: uuid.UUID
    ) -> StockTransfer | None:
        query = (
            select(StockTransfer)
            .where(StockTransfer.id == transfer_id)
            .options(selectinload(StockTransfer.items))
            .with_for_update()
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_transfer(self, transfer_id: uuid.UUID) -> StockTransfer | None:
        query = (
            select(StockTransfer)
            .where(StockTransfer.id == transfer_id)
            .options(
                joinedload(StockTransfer.from_inventory),
                joinedload(StockTransfer.to_inventory),
                selectinload(StockTransfer.items).joinedload(StockTransferItem.product),
            )
        )

        result = await self.session.execute(query)
        return result.unique().scalar_one_or_none()

    async def change_status(
        self,
        transfer_id: uuid.UUID,
        new_status: TransferStatus,
        accepted_by_id: uuid.UUID | None = None,
    ) -> StockTransfer | None:
        transfer = await self.get_with_items_for_update(transfer_id)
        if transfer:
            transfer.status = new_status
            transfer.accepted_by_id = accepted_by_id
            await self.session.flush()
        return transfer

    async def search_transfers(
        self,
        skip: int = 0,
        limit: int = 50,
        status: TransferStatus | None = None,
        transfer_type: TransferType | None = None,
        from_inventory_id: uuid.UUID | None = None,
        to_inventory_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Sequence[StockTransfer]:
        query = select(self.model)

        if status:
            query = query.where(self.model.status == status)
        if transfer_type:
            query = query.where(self.model.type == transfer_type)
        if from_inventory_id:
            query = query.where(self.model.from_id == from_inventory_id)
        if to_inventory_id:
            query = query.where(self.model.to_id == to_inventory_id)
        if date_from:
            query = query.where(self.model.created_at >= date_from)
        if date_to:
            query = query.where(self.model.created_at <= date_to)

        query = (
            query
            .options(
                joinedload(self.model.from_inventory),
                joinedload(self.model.to_inventory),
                selectinload(StockTransfer.items).joinedload(StockTransferItem.product),
            )
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return result.unique().scalars().all()


class StockTransactionRepository(BaseRepository[StockTransaction]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=StockTransaction, session=session)

    async def archive(self, id: uuid.UUID) -> bool:
        raise NotImplementedError(
            "Strict Ledger: Нельзя скрывать (archive). История иммутабельна."
        )

    async def delete(self, id: uuid.UUID) -> bool:
        raise NotImplementedError(
            "Strict Ledger: Нельзя удалять. Баланс должен сходиться 1-в-1."
        )

    # --- ОПЕРАЦИОННАЯ ЛОГИКА (Для Unit of Work) ---

    async def get_by_transfer(
        self, transfer_id: uuid.UUID
    ) -> Sequence[StockTransaction]:
        """Получить все проводки конкретного документа (Накладной)."""
        query = select(self.model).where(self.model.transfer_id == transfer_id)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_balances_for_products(
        self, inventory_id: uuid.UUID, product_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not product_ids:
            return {}

        balance_expr = func.sum(
            case(
                (self.model.to_id == inventory_id, self.model.quantity),
                (self.model.from_id == inventory_id, -self.model.quantity),
                else_=0,
            )
        ).label("balance")

        query = (
            select(self.model.product_id, balance_expr)
            .where(
                self.model.product_id.in_(product_ids),
                or_(
                    self.model.to_id == inventory_id,
                    self.model.from_id == inventory_id,
                ),
            )
            .group_by(self.model.product_id)
        )

        result = await self.session.execute(query)

        balances = dict.fromkeys(product_ids, 0)

        # 3. Обновляем нули реальными данными из БД
        for row in result.all():
            balances[row.product_id] = row.balance

        return balances

    async def get_balance(
        self,
        inventory_id: uuid.UUID,
        product_id: uuid.UUID,
        as_of_date: datetime | None = None,
    ) -> int:
        query = select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            self.model.to_id == inventory_id,
                            self.model.quantity,
                        ),
                        (
                            self.model.from_id == inventory_id,
                            -self.model.quantity,
                        ),
                        else_=0,
                    )
                ),
                0,
            )
        ).where(
            self.model.product_id == product_id,
            or_(
                self.model.to_id == inventory_id,
                self.model.from_id == inventory_id,
            ),
        )

        if as_of_date:
            query = query.where(self.model.created_at <= as_of_date)

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_balances(self, inventory_id: uuid.UUID) -> list[dict[str, Any]]:
        balance_expr = func.sum(
            case(
                (self.model.to_id == inventory_id, self.model.quantity),
                (self.model.from_id == inventory_id, -self.model.quantity),
                else_=0,
            )
        )
        query = (
            select(balance_expr.label("quantity"), Product)
            .join(Product, self.model.product_id == Product.id)
            .where(
                or_(
                    self.model.to_id == inventory_id,
                    self.model.from_id == inventory_id,
                )
            )
            .group_by(Product.id)
            .having(balance_expr != 0)
        )

        result = await self.session.execute(query)
        return [
            {
                "quantity": row.quantity,
                "product": row.Product,
            }
            for row in result.all()
        ]

    # --- АНАЛИТИКА: ДОЛГИ ПО ТАРЕ И ОБОРАЧИВАЕМОСТЬ (HOD Specific) ---

    async def get_client_total_debt(
        self, user_id: uuid.UUID, empty_bottle_id: uuid.UUID
    ) -> int:
        client_inv_ids = (
            select(Inventory.id)
            .where(
                Inventory.user_id == user_id,
                Inventory.type == InventoryType.CLIENT,
            )
            .scalar_subquery()
        )

        query = select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            self.model.to_id.in_(client_inv_ids),
                            self.model.quantity,
                        ),
                        (
                            self.model.from_id.in_(client_inv_ids),
                            -self.model.quantity,
                        ),
                        else_=0,
                    )
                ),
                0,
            )
        ).where(
            self.model.product_id == empty_bottle_id,
            or_(
                self.model.to_id.in_(client_inv_ids),
                self.model.from_id.in_(client_inv_ids),
            ),
        )

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_debtors_report(
        self, empty_bottle_id: uuid.UUID, min_debt: int = 1
    ) -> dict[uuid.UUID, int]:
        """
        Аналитика Merchant: Топ должников (кто не вернул тару).
        """
        balance_expr = func.sum(
            case(
                (self.model.to_id == Inventory.id, self.model.quantity),
                (self.model.from_id == Inventory.id, -self.model.quantity),
                else_=0,
            )
        )

        query = (
            select(Inventory.user_id, balance_expr.label("debt"))
            .select_from(self.model)
            .join(
                Inventory,
                or_(
                    self.model.to_id == Inventory.id,
                    self.model.from_id == Inventory.id,
                ),
            )
            .where(
                Inventory.type == InventoryType.CLIENT,
                self.model.product_id == empty_bottle_id,
            )
            .group_by(Inventory.user_id)
            .having(balance_expr >= min_debt)
            .order_by(desc("debt"))
        )

        result = await self.session.execute(query)
        return {row.user_id: row.debt for row in result.all()}

    async def get_turnover_by_period(
        self,
        transfer_type: TransferType,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[uuid.UUID, int]:
        """
        Аналитика Merchant: Объем операций за период.
        Пример: Сколько полных бутылей мы доставили (CLIENT_DELIVERY)?
        """
        query = (
            select(
                self.model.product_id,
                func.sum(self.model.quantity).label("total_volume"),
            )
            .select_from(self.model)
            .join(StockTransfer, self.model.transfer_id == StockTransfer.id)
            .where(
                StockTransfer.type == transfer_type,
                self.model.created_at >= start_date,
                self.model.created_at <= end_date,
            )
            .group_by(self.model.product_id)
        )

        result = await self.session.execute(query)
        return {row.product_id: row.total_volume for row in result.all()}

    # --- ВЫПИСКИ ДЛЯ UI И СВЕРКИ СМЕН ---

    async def get_inventory_statement(
        self,
        inventory_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> Sequence[StockTransaction]:
        """UI: История движений (Выписка) по складу/курьеру с пагинацией."""
        query = (
            select(self.model)
            .where(
                or_(
                    self.model.to_id == inventory_id,
                    self.model.from_id == inventory_id,
                )
            )
            .options(selectinload(self.model.transfer))
            .order_by(self.model.created_at.desc())
        )

        if start_date:
            query = query.where(self.model.created_at >= start_date)
        if end_date:
            query = query.where(self.model.created_at <= end_date)

        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()
