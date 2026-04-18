# src/modules/inventory/models.py

import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)

if TYPE_CHECKING:
    from src.infrastructure.database.models import User
    from src.modules.catalog.models import Product
    from src.modules.orders.models import Order


class Inventory(BaseModel):
    __tablename__ = "inventories"
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment=(
            "Кто материально ответственен за эту точку"
            " (курьер, клиент, кладовщик)?"
        ),
    )
    type: Mapped[InventoryType] = mapped_column(
        Enum(
            InventoryType,
            name="inventory_type_enum",
            native_enum=True,
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        index=True,
        comment="Тип инвентаря: WAREHOUSE, COURIER, CLIENT, VIRTUAL",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Понятное название (например: 'Машина АВ123', 'Склад Центр')",
    )
    user: Mapped[User] = relationship(back_populates="inventories")

    outgoing_transactions: Mapped[list[StockTransaction]] = relationship(
        foreign_keys="StockTransaction.from_id",
        back_populates="from_inventory",
        viewonly=True,
        overlaps="transactions",
    )
    incoming_transactions: Mapped[list[StockTransaction]] = relationship(
        foreign_keys="StockTransaction.to_id",
        back_populates="to_inventory",
        viewonly=True,
        overlaps="transactions",
    )
    balances: Mapped[list[Balance]] = relationship(
        back_populates="inventory", cascade="all, delete-orphan"
    )
    __table_args__ = (
        Index(
            "uq_active_courier_inventory",
            "user_id",
            unique=True,
            postgresql_where=sa.text("type = 'COURIER' AND is_active = true"),
        ),
        Index("idx_inventory_user_type", "user_id", "type"),
        {
            "comment": (
                "Реестр всех физических и виртуальных мест хранения"
                " (склады, машины, клиенты)"
            ),
        },
    )


class StockTransfer(BaseModel):
    __tablename__ = "stock_transfers"

    from_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    to_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Кто создал документ перемещения",
    )
    accepted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        comment="Кто физически принял товар (подтвердил накладную)",
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Ссылка на клиентский заказ (если применимо)",
    )
    reason: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
        comment="Причина (для списания LOSS_WRITE_OFF)",
    )
    route_sheet_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID,
        nullable=True,
        index=True,
        comment="ID маршрутного листа (для COURIER_LOAD)",
    )

    type: Mapped[TransferType] = mapped_column(
        Enum(
            TransferType,
            name="transfer_type_enum",
            native_enum=True,
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        index=True,
    )
    status: Mapped[TransferStatus] = mapped_column(
        Enum(
            TransferStatus,
            name="transfer_status_enum",
            native_enum=True,
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=TransferStatus.DRAFT,
        index=True,
        comment="Статус документа (DRAFT, COMPLETED, CANCELLED)",
    )

    from_inventory: Mapped[Inventory] = relationship(foreign_keys=[from_id])
    to_inventory: Mapped[Inventory] = relationship(foreign_keys=[to_id])
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    accepted_by: Mapped[User | None] = relationship(
        foreign_keys=[accepted_by_id]
    )
    order: Mapped[Order | None] = relationship(
        back_populates="stock_transfers"
    )

    items: Mapped[list[StockTransferItem]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan"
    )
    transactions: Mapped[list[StockTransaction]] = relationship(
        back_populates="transfer",
        cascade="all, delete-orphan",
        overlaps="outgoing_transactions,incoming_transactions",
    )

    __table_args__ = (
        CheckConstraint(
            "from_id != to_id", name="ck_stock_transfer_no_circular"
        ),
        UniqueConstraint(
            "id", "from_id", "to_id", name="uq_stock_transfer_route"
        ),
        {
            "comment": (
                "Документы (накладные) на перемещение товаров"
                " между складами/клиентами"
            ),
        },
    )


class StockTransferItem(BaseModel):
    __tablename__ = "stock_transfer_items"

    transfer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_transfers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Количество в документе"
    )
    transfer: Mapped[StockTransfer] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()

    __table_args__ = (
        CheckConstraint(
            "quantity > 0", name="ck_stock_transfer_item_quantity_pos"
        ),
        {
            "comment": (
                "Черновик строк накладной"
                " (не влияет на остатки, пока статус DRAFT)"
            ),
        },
    )


class Balance(BaseModel):
    __tablename__ = "inventory_balances"

    inventory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventories.id", ondelete="CASCADE"),
        nullable=False,
        # УДАЛЕНО index=True: покрывается индексом от UniqueConstraint
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Фактический остаток"
    )

    inventory: Mapped[Inventory] = relationship(back_populates="balances")
    product: Mapped[Product] = relationship()

    # ВАЖНО: глобальный CHECK (quantity >= 0) намеренно НЕ
    # объявлен. Виртуальные инвентари VIRTUAL_VENDOR /
    # VIRTUAL_LOSS по дизайну держат отрицательный/растущий
    # баланс (источник оприходования и яма списаний).
    # Партиальная проверка «non-virtual ⇒ quantity >= 0»
    # реализована в триггере `update_inventory_balances`
    # (`scripts/update_inventory_balances.sql`). PostgreSQL не
    # поддерживает CHECK с подзапросом — поэтому DDL CHECK
    # эквивалент построить нельзя, и триггер остаётся единственным
    # местом enforcement.
    __table_args__ = (
        UniqueConstraint(
            "inventory_id", "product_id", name="uq_inventory_product_balance"
        ),
        {
            "comment": (
                "Материализованные (закэшированные) остатки."
                " Обновляется триггером базы данных"
            ),
        },
    )


class StockTransaction(BaseModel):
    __tablename__ = "stock_transactions"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    transfer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    from_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    to_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Проведенное количество"
    )

    product: Mapped[Product] = relationship()
    from_inventory: Mapped[Inventory] = relationship(
        foreign_keys=[from_id],
        back_populates="outgoing_transactions",
        overlaps="transactions",
    )
    to_inventory: Mapped[Inventory] = relationship(
        foreign_keys=[to_id],
        back_populates="incoming_transactions",
        overlaps="transactions",
    )
    transfer: Mapped[StockTransfer] = relationship(
        back_populates="transactions",
        overlaps=(
            "incoming_transactions,to_inventory,"
            "outgoing_transactions,from_inventory"
        ),
    )

    __table_args__ = (
        CheckConstraint(
            "quantity > 0", name="ck_stock_transaction_quantity_positive"
        ),
        ForeignKeyConstraint(
            ["transfer_id", "from_id", "to_id"],
            [
                "stock_transfers.id",
                "stock_transfers.from_id",
                "stock_transfers.to_id",
            ],
            ondelete="CASCADE",
            name="fk_stock_transaction_strict_route",
        ),
        Index("idx_st_product_from", "product_id", "from_id"),
        Index("idx_st_product_to", "product_id", "to_id"),
        {
            "comment": (
                "Строгий леджер движения товаров (Event Sourcing)."
                " Истина в последней инстанции"
            ),
        },
    )
