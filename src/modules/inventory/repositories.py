import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, desc, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.common.repository import BaseRepository
from src.common.search import ilike_pattern
from src.core.constants import SYSTEM_USER_ID
from src.infrastructure.database.models import (
    Balance,
    Identity,
    Inventory,
    Product,
    StockTransaction,
    StockTransfer,
    StockTransferItem,
    User,
)
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)


class InventoryRepository(BaseRepository[Inventory]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Inventory, session=session)

    async def get_with_user(
        self,
        inventory_id: uuid.UUID,
        active_only: bool = True,
    ) -> Inventory | None:
        query = (
            select(self.model)
            .where(self.model.id == inventory_id)
            .options(joinedload(self.model.user).selectinload(User.identities))
        )
        if active_only:
            query = query.where(self.model.is_active.is_(True))

        result = await self.session.execute(query)
        return result.unique().scalar_one_or_none()

    async def create_courier_inventory(
        self, user_id: uuid.UUID, inventory_name: str
    ) -> Inventory:
        return await self.add(
            {
                "user_id": user_id,
                "type": InventoryType.COURIER,
                "name": inventory_name,
            }
        )

    async def create_client_inventory(
        self, user_id: uuid.UUID, inventory_name: str
    ) -> Inventory:
        return await self.add(
            {
                "user_id": user_id,
                "type": InventoryType.CLIENT,
                "name": inventory_name,
            }
        )

    async def get_system_inventory(
        self, inv_type: InventoryType, with_for_update: bool = False
    ) -> Inventory:
        query = select(self.model).where(
            self.model.user_id == SYSTEM_USER_ID,
            self.model.type == inv_type,
        )
        if with_for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        inventory = result.scalar_one_or_none()
        if inventory is None:
            from src.modules.inventory.exceptions import (
                VirtualInventoryConfigurationError,
            )

            raise VirtualInventoryConfigurationError(v_type=inv_type)
        return inventory

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
            .options(
                selectinload(self.model.balances).joinedload(
                    attr=Balance.product
                )
            )
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
        self, user_id: uuid.UUID
    ) -> Inventory | None:
        query = select(self.model).where(
            self.model.user_id == user_id,
            self.model.type == InventoryType.CLIENT,
            self.model.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalars().first()

    async def search_inventories(
        self,
        search_query: str,
        inv_type: InventoryType | None = None,
        limit: int = 50,
    ) -> Sequence[Inventory]:
        query = select(self.model).where(
            self.model.name.ilike(ilike_pattern(search_query)),
            self.model.is_active.is_(True),
        )
        if inv_type:
            query = query.where(self.model.type == inv_type)

        query = query.limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def search_inventories_cursor(
        self,
        search_query: str,
        inv_type: InventoryType | None = None,
        size: int = 50,
        cursor: tuple[str, uuid.UUID] | None = None,
    ) -> Sequence[Inventory]:
        """Cursor-вариант ``search_inventories`` (FRD §15.2).

        Сортировка: ``(name ASC, id ASC)``.
        Возвращает ``size + 1`` строк — service срезает остаток
        и формирует ``next_cursor``.
        """
        query = select(self.model).where(
            self.model.name.ilike(ilike_pattern(search_query)),
            self.model.is_active.is_(True),
        )
        if inv_type:
            query = query.where(self.model.type == inv_type)
        if cursor is not None:
            last_name, last_id = cursor
            query = query.where(
                tuple_(self.model.name, self.model.id)
                > tuple_(last_name, last_id)
            )
        query = query.order_by(
            self.model.name.asc(), self.model.id.asc()
        ).limit(size + 1)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_inventory_with_balances(
        self,
        inventory_id: uuid.UUID,
        inv_type: InventoryType | None = None,
        with_for_update: bool = False,
    ) -> Inventory | None:
        """Получить инвентарь (склад/транспорт) с актуальными остатками.

        Загружаются все балансы, включая архивированные товары —
        архивный статус отображается в UI, а не скрывается.
        """
        query = select(self.model).where(
            self.model.id == inventory_id,
            self.model.is_active.is_(True),
        )
        if inv_type:
            query = query.where(self.model.type == inv_type)

        if with_for_update:
            query = query.with_for_update()

        # User joinedload uses LEFT OUTER JOIN which PostgreSQL forbids with
        # FOR UPDATE — skip it when locking (user data not needed for writes)
        options = [
            selectinload(self.model.balances).joinedload(Balance.product),
        ]
        if not with_for_update:
            options.append(
                joinedload(self.model.user).selectinload(User.identities)
            )
        query = query.options(*options)
        result = await self.session.execute(query)
        return result.unique().scalar_one_or_none()

    async def get_inventory_with_balances_by_user(
        self,
        user_id: uuid.UUID,
        inv_type: InventoryType,
    ) -> Inventory | None:
        """Найти инвентарь пользователя по типу с балансами.

        Используется для клиентского баланса тары и
        курьерского баланса загруженного товара.
        """
        query = (
            select(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.type == inv_type,
                self.model.is_active.is_(True),
            )
            .options(
                selectinload(self.model.balances).joinedload(Balance.product),
            )
        )
        result = await self.session.execute(query)
        return result.unique().scalars().first()

    async def get_all_warehouses_with_balances(
        self,
        owner_id: uuid.UUID | None = None,
    ) -> Sequence[Inventory]:
        """Получить все склады с их полными товарными остатками.

        Включает балансы по всем товарам, в том числе архивированным.
        Если owner_id задан — возвращаются только склады этого владельца
        (используется для ограничения видимости кладовщика).
        """
        query = (
            select(self.model)
            .where(
                self.model.type == InventoryType.WAREHOUSE,
                self.model.is_active.is_(True),
            )
            .options(
                selectinload(self.model.balances).joinedload(Balance.product),
                joinedload(self.model.user).selectinload(User.identities),
            )
        )
        if owner_id is not None:
            query = query.where(self.model.user_id == owner_id)
        result = await self.session.execute(query)
        return result.unique().scalars().all()

    async def get_all_warehouses_with_balances_cursor(
        self,
        owner_id: uuid.UUID | None = None,
        size: int = 50,
        cursor: tuple[str, uuid.UUID] | None = None,
    ) -> Sequence[Inventory]:
        """Cursor-вариант ``get_all_warehouses_with_balances`` (FRD §15.2).

        Сортировка: ``(name ASC, id ASC)``. Возвращает ``size + 1``
        строк — service срезает и формирует ``next_cursor``.
        """
        query = (
            select(self.model)
            .where(
                self.model.type == InventoryType.WAREHOUSE,
                self.model.is_active.is_(True),
            )
            .options(
                selectinload(self.model.balances).joinedload(Balance.product),
                joinedload(self.model.user).selectinload(User.identities),
            )
        )
        if owner_id is not None:
            query = query.where(self.model.user_id == owner_id)
        if cursor is not None:
            last_name, last_id = cursor
            query = query.where(
                tuple_(self.model.name, self.model.id)
                > tuple_(last_name, last_id)
            )
        query = query.order_by(
            self.model.name.asc(), self.model.id.asc()
        ).limit(size + 1)
        result = await self.session.execute(query)
        return result.unique().scalars().all()


class StockTransferItemRepository(BaseRepository[StockTransferItem]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=StockTransferItem, session=session)


class StockTransferRepository(BaseRepository[StockTransfer]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=StockTransfer, session=session)

    async def get_with_items(
        self, transfer_id: uuid.UUID
    ) -> StockTransfer | None:
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

    async def get_transfer(
        self, transfer_id: uuid.UUID
    ) -> StockTransfer | None:
        query = (
            select(StockTransfer)
            .where(StockTransfer.id == transfer_id)
            .options(
                joinedload(StockTransfer.from_inventory),
                joinedload(StockTransfer.to_inventory),
                selectinload(StockTransfer.items).joinedload(
                    StockTransferItem.product
                ),
                joinedload(StockTransfer.created_by).selectinload(
                    User.identities
                ),
                joinedload(StockTransfer.accepted_by).selectinload(
                    User.identities
                ),
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
        warehouse_owner_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
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
        if warehouse_id is not None:
            query = query.where(
                or_(
                    self.model.from_id == warehouse_id,
                    self.model.to_id == warehouse_id,
                )
            )
        # Storekeeper scoping: show only transfers
        # that touch their warehouse(s)
        if warehouse_owner_id is not None:
            owner_inv_ids = (
                select(Inventory.id)
                .where(
                    Inventory.user_id == warehouse_owner_id,
                    Inventory.type == InventoryType.WAREHOUSE,
                )
                .scalar_subquery()
            )
            query = query.where(
                or_(
                    self.model.from_id.in_(owner_inv_ids),
                    self.model.to_id.in_(owner_inv_ids),
                )
            )

        query = (
            query.options(
                joinedload(self.model.from_inventory),
                joinedload(self.model.to_inventory),
                selectinload(StockTransfer.items).joinedload(
                    StockTransferItem.product
                ),
                joinedload(StockTransfer.created_by).selectinload(
                    User.identities
                ),
                joinedload(StockTransfer.accepted_by).selectinload(
                    User.identities
                ),
            )
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return result.unique().scalars().all()

    async def search_transfers_cursor(
        self,
        size: int = 50,
        cursor: tuple[datetime, uuid.UUID] | None = None,
        status: TransferStatus | None = None,
        transfer_type: TransferType | None = None,
        from_inventory_id: uuid.UUID | None = None,
        to_inventory_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        warehouse_owner_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
    ) -> Sequence[StockTransfer]:
        """Cursor-вариант ``search_transfers`` (FRD §15.2).

        Сортировка: ``(created_at DESC, id DESC)`` — стабильный
        обратный keyset, рассчитан на UUIDv7 (монотонные id).
        Возвращает ``size + 1`` строк — service срезает и формирует
        ``next_cursor``.
        """
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
        if warehouse_id is not None:
            query = query.where(
                or_(
                    self.model.from_id == warehouse_id,
                    self.model.to_id == warehouse_id,
                )
            )
        if warehouse_owner_id is not None:
            owner_inv_ids = (
                select(Inventory.id)
                .where(
                    Inventory.user_id == warehouse_owner_id,
                    Inventory.type == InventoryType.WAREHOUSE,
                )
                .scalar_subquery()
            )
            query = query.where(
                or_(
                    self.model.from_id.in_(owner_inv_ids),
                    self.model.to_id.in_(owner_inv_ids),
                )
            )
        if cursor is not None:
            last_created, last_id = cursor
            query = query.where(
                tuple_(self.model.created_at, self.model.id)
                < tuple_(last_created, last_id)
            )

        query = (
            query.options(
                joinedload(self.model.from_inventory),
                joinedload(self.model.to_inventory),
                selectinload(StockTransfer.items).joinedload(
                    StockTransferItem.product
                ),
                joinedload(StockTransfer.created_by).selectinload(
                    User.identities
                ),
                joinedload(StockTransfer.accepted_by).selectinload(
                    User.identities
                ),
            )
            .order_by(
                self.model.created_at.desc(),
                self.model.id.desc(),
            )
            .limit(size + 1)
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

    async def restore(self, id: uuid.UUID) -> bool:
        raise NotImplementedError(
            "Strict Ledger: Нельзя восстанавливать. История иммутабельна."
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

    async def get_balances(
        self, inventory_id: uuid.UUID
    ) -> list[dict[str, Any]]:
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
            .options(
                selectinload(self.model.transfer),
                joinedload(self.model.product),
            )
            .order_by(self.model.created_at.desc())
        )

        if start_date:
            query = query.where(self.model.created_at >= start_date)
        if end_date:
            query = query.where(self.model.created_at <= end_date)

        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    # --- НОВЫЙ API: Журнал движений (Stock Ledger, FRD §6) ---

    def _apply_stock_transaction_filters(
        self,
        stmt,
        from_inv,
        to_inv,
        product_alias,
        transfer_alias,
        filters,
    ):
        """Наложить WHERE из StockTransactionFilter (FRD §6.1)."""
        from src.modules.inventory.search import (
            extract_phone_digits,
            is_phone_like,
            try_parse_int,
        )
        from src.modules.inventory.search import (
            ilike_pattern as _ilike,
        )

        if filters.product_id is not None:
            stmt = stmt.where(self.model.product_id == filters.product_id)
        if filters.product_id_in:
            stmt = stmt.where(self.model.product_id.in_(filters.product_id_in))
        if filters.product_type_in:
            stmt = stmt.where(product_alias.type.in_(filters.product_type_in))

        if filters.from_id is not None:
            stmt = stmt.where(self.model.from_id == filters.from_id)
        if filters.to_id is not None:
            stmt = stmt.where(self.model.to_id == filters.to_id)

        if filters.inventory_id is not None:
            direction = filters.direction
            if direction == "incoming":
                stmt = stmt.where(self.model.to_id == filters.inventory_id)
            elif direction == "outgoing":
                stmt = stmt.where(self.model.from_id == filters.inventory_id)
            else:
                stmt = stmt.where(
                    or_(
                        self.model.from_id == filters.inventory_id,
                        self.model.to_id == filters.inventory_id,
                    )
                )

        if filters.from_type_in:
            stmt = stmt.where(from_inv.type.in_(filters.from_type_in))
        if filters.to_type_in:
            stmt = stmt.where(to_inv.type.in_(filters.to_type_in))

        if filters.transfer_id is not None:
            stmt = stmt.where(self.model.transfer_id == filters.transfer_id)
        if filters.transfer_type_in:
            stmt = stmt.where(
                transfer_alias.type.in_(filters.transfer_type_in)
            )
        if filters.order_id is not None:
            stmt = stmt.where(transfer_alias.order_id == filters.order_id)
        if filters.created_by_id is not None:
            stmt = stmt.where(
                transfer_alias.created_by_id == filters.created_by_id
            )

        if filters.quantity_eq is not None:
            stmt = stmt.where(self.model.quantity == filters.quantity_eq)
        if filters.quantity_from is not None:
            stmt = stmt.where(self.model.quantity >= filters.quantity_from)
        if filters.quantity_to is not None:
            stmt = stmt.where(self.model.quantity <= filters.quantity_to)

        if filters.date_from is not None:
            stmt = stmt.where(self.model.created_at >= filters.date_from)
        if filters.date_to is not None:
            stmt = stmt.where(self.model.created_at <= filters.date_to)

        if filters.q:
            q = filters.q.strip()
            conditions = []
            # Канал «целое» (только если не телефон)
            if not is_phone_like(q):
                int_val = try_parse_int(q)
                if int_val is not None:
                    conditions.append(self.model.quantity == int_val)
            # Канал «текст»: имя продукта, имена обоих складов, причина
            pat = _ilike(q)
            conditions.extend(
                [
                    product_alias.name.ilike(pat),
                    from_inv.name.ilike(pat),
                    to_inv.name.ilike(pat),
                    transfer_alias.reason.ilike(pat),
                ]
            )
            # Канал «телефон» — суффикс цифр против обоих владельцев
            if is_phone_like(q):
                digits = extract_phone_digits(q)
                phone_pat = f"%{digits}%"
                # Подзапрос: id инвентарей, чей user.identity.local
                # содержит подстроку digits.
                phone_subq = (
                    select(Inventory.id)
                    .join(User, User.id == Inventory.user_id)
                    .join(
                        Identity,
                        and_(
                            Identity.user_id == User.id,
                            Identity.provider == "local",
                        ),
                    )
                    .where(
                        func.regexp_replace(
                            Identity.provider_identity_id,
                            r"\D",
                            "",
                            "g",
                        ).like(phone_pat)
                    )
                ).subquery()
                conditions.append(
                    or_(
                        self.model.from_id.in_(select(phone_subq.c.id)),
                        self.model.to_id.in_(select(phone_subq.c.id)),
                    )
                )
            stmt = stmt.where(or_(*conditions))

        return stmt

    def _stock_transaction_base_joins(self):
        """Подготовить aliased-JOIN'ы для леджера."""
        from sqlalchemy.orm import aliased

        from_inv = aliased(Inventory, name="from_inv_st")
        to_inv = aliased(Inventory, name="to_inv_st")
        product_alias = aliased(Product, name="prod_st")
        transfer_alias = aliased(StockTransfer, name="transfer_st")

        base = (
            select(self.model)
            .join(from_inv, self.model.from_id == from_inv.id)
            .join(to_inv, self.model.to_id == to_inv.id)
            .join(product_alias, self.model.product_id == product_alias.id)
            .join(transfer_alias, self.model.transfer_id == transfer_alias.id)
        )
        return from_inv, to_inv, product_alias, transfer_alias, base

    async def search_with_filters(
        self,
        filters,
        skip: int,
        limit: int,
    ) -> tuple[int, Sequence[StockTransaction]]:
        """Пагинированный список движений с применением фильтра."""
        from sqlalchemy.orm import contains_eager

        (
            from_inv,
            to_inv,
            product_alias,
            transfer_alias,
            base,
        ) = self._stock_transaction_base_joins()
        base = self._apply_stock_transaction_filters(
            base,
            from_inv,
            to_inv,
            product_alias,
            transfer_alias,
            filters,
        )

        count_stmt = select(func.count()).select_from(
            base.with_only_columns(self.model.id).order_by(None).subquery()
        )
        total = (await self.session.execute(count_stmt)).scalar() or 0

        if filters.sort == "quantity":
            sort_col = self.model.quantity
        else:
            sort_col = self.model.created_at
        order_expr = (
            sort_col.asc() if filters.order == "asc" else sort_col.desc()
        )

        query = (
            base.options(
                contains_eager(self.model.from_inventory.of_type(from_inv)),
                contains_eager(self.model.to_inventory.of_type(to_inv)),
                contains_eager(self.model.product.of_type(product_alias)),
                contains_eager(self.model.transfer.of_type(transfer_alias)),
            )
            .order_by(order_expr, self.model.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return total, result.scalars().unique().all()

    async def summarize_with_filters(self, filters) -> dict:
        """Агрегаты по тому же фильтру (FRD §6.5).

        Возвращает dict с total_transactions, total_quantity,
        by_transfer_type.
        """
        (
            from_inv,
            to_inv,
            product_alias,
            transfer_alias,
            base,
        ) = self._stock_transaction_base_joins()
        base = self._apply_stock_transaction_filters(
            base,
            from_inv,
            to_inv,
            product_alias,
            transfer_alias,
            filters,
        )

        # totals
        totals_stmt = select(
            func.count(self.model.id),
            func.coalesce(func.sum(self.model.quantity), 0),
        ).select_from(base.subquery())
        totals_row = (await self.session.execute(totals_stmt)).one()
        total_transactions = int(totals_row[0])
        total_quantity = int(totals_row[1])

        # by_transfer_type — отдельный запрос с GROUP BY на исходном
        # join'е (subquery() прячет колонки transfer.type).
        (
            from_inv2,
            to_inv2,
            product_alias2,
            transfer_alias2,
            base2,
        ) = self._stock_transaction_base_joins()
        base2 = self._apply_stock_transaction_filters(
            base2,
            from_inv2,
            to_inv2,
            product_alias2,
            transfer_alias2,
            filters,
        )
        by_type_stmt = (
            base2.with_only_columns(
                transfer_alias2.type,
                func.coalesce(func.sum(self.model.quantity), 0),
            )
            .group_by(transfer_alias2.type)
            .order_by(None)
        )
        by_type_rows = (await self.session.execute(by_type_stmt)).all()
        by_transfer_type = {
            (row[0].value if hasattr(row[0], "value") else str(row[0])): int(
                row[1]
            )
            for row in by_type_rows
        }
        return {
            "total_transactions": total_transactions,
            "total_quantity": total_quantity,
            "by_transfer_type": by_transfer_type,
        }


# =====================================================================
# BalanceRepository — кросс-вью на materialized inventory_balances
# (FRD §9). Выделен в отдельный класс, потому что domain-операции с
# балансами (запись / триггеры) выполняются на уровне БД, и read-only
# срез не нуждается в наследовании от BaseRepository[Balance].
# =====================================================================


class BalanceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_balance_filters(
        self, stmt, product_alias, inventory_alias, filters
    ):
        from src.modules.inventory.search import ilike_pattern as _ilike

        if filters.nonzero_only:
            stmt = stmt.where(Balance.quantity > 0)

        if filters.product_id is not None:
            stmt = stmt.where(Balance.product_id == filters.product_id)
        if filters.product_id_in:
            stmt = stmt.where(Balance.product_id.in_(filters.product_id_in))
        if filters.product_type_in:
            stmt = stmt.where(product_alias.type.in_(filters.product_type_in))

        if filters.inventory_type_in:
            stmt = stmt.where(
                inventory_alias.type.in_(filters.inventory_type_in)
            )
        if filters.inventory_id_in:
            stmt = stmt.where(
                Balance.inventory_id.in_(filters.inventory_id_in)
            )
        if filters.user_id is not None:
            stmt = stmt.where(inventory_alias.user_id == filters.user_id)

        if filters.quantity_from is not None:
            stmt = stmt.where(Balance.quantity >= filters.quantity_from)
        if filters.quantity_to is not None:
            stmt = stmt.where(Balance.quantity <= filters.quantity_to)

        if filters.q:
            q = filters.q.strip()
            pat = _ilike(q)
            stmt = stmt.where(
                or_(
                    product_alias.name.ilike(pat),
                    inventory_alias.name.ilike(pat),
                )
            )
        return stmt

    def _balance_base_joins(self):
        from sqlalchemy.orm import aliased

        product_alias = aliased(Product, name="prod_bal")
        inventory_alias = aliased(Inventory, name="inv_bal")
        base = (
            select(Balance)
            .join(product_alias, Balance.product_id == product_alias.id)
            .join(inventory_alias, Balance.inventory_id == inventory_alias.id)
        )
        return product_alias, inventory_alias, base

    async def search_with_filters(
        self, filters, skip: int, limit: int
    ) -> tuple[int, Sequence[Balance]]:
        from sqlalchemy.orm import contains_eager

        (
            product_alias,
            inventory_alias,
            base,
        ) = self._balance_base_joins()
        base = self._apply_balance_filters(
            base, product_alias, inventory_alias, filters
        )

        count_stmt = select(func.count()).select_from(
            base.with_only_columns(Balance.id).order_by(None).subquery()
        )
        total = (await self.session.execute(count_stmt)).scalar() or 0

        if filters.sort == "product_name":
            sort_col = product_alias.name
        elif filters.sort == "inventory_name":
            sort_col = inventory_alias.name
        else:
            sort_col = Balance.quantity
        order_expr = (
            sort_col.asc() if filters.order == "asc" else sort_col.desc()
        )

        query = (
            base.options(
                contains_eager(Balance.product.of_type(product_alias)),
                contains_eager(Balance.inventory.of_type(inventory_alias)),
            )
            .order_by(order_expr, Balance.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return total, result.scalars().unique().all()

    async def summarize_with_filters(self, filters) -> dict:
        """`{total_quantity, by_inventory_type}` (FRD §9.4)."""
        (
            product_alias,
            inventory_alias,
            base,
        ) = self._balance_base_joins()
        base = self._apply_balance_filters(
            base, product_alias, inventory_alias, filters
        )
        total_stmt = select(
            func.coalesce(func.sum(Balance.quantity), 0)
        ).select_from(base.subquery())
        total_quantity = int(
            (await self.session.execute(total_stmt)).scalar() or 0
        )

        # by_inventory_type — отдельный запрос с GROUP BY
        (
            product_alias2,
            inventory_alias2,
            base2,
        ) = self._balance_base_joins()
        base2 = self._apply_balance_filters(
            base2, product_alias2, inventory_alias2, filters
        )
        by_type_stmt = (
            base2.with_only_columns(
                inventory_alias2.type,
                func.coalesce(func.sum(Balance.quantity), 0),
            )
            .group_by(inventory_alias2.type)
            .order_by(None)
        )
        rows = (await self.session.execute(by_type_stmt)).all()
        by_inventory_type = {
            (row[0].value if hasattr(row[0], "value") else str(row[0])): int(
                row[1]
            )
            for row in rows
        }
        return {
            "total_quantity": total_quantity,
            "by_inventory_type": by_inventory_type,
        }
