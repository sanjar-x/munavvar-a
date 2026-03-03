# src/modules/inventory/models.py

import uuid
from typing import TYPE_CHECKING

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
    from src.modules.catalog.models import Product
    from src.modules.orders.models import Order
    from src.modules.users.models import User


class Inventory(BaseModel):
    __tablename__ = "inventories"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        comment="Кто материально ответственен за эту точку?",
    )
    type: Mapped[InventoryType] = mapped_column(
        Enum(InventoryType, name="inventory_type_enum", native_enum=True),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    user: Mapped["User | None"] = relationship(back_populates="inventories")

    outgoing_transactions: Mapped[list["StockTransaction"]] = relationship(
        foreign_keys="StockTransaction.from_id",
        back_populates="from_inventory",
    )
    incoming_transactions: Mapped[list["StockTransaction"]] = relationship(
        foreign_keys="StockTransaction.to_id",
        back_populates="to_inventory",
    )


class StockTransfer(BaseModel):
    __tablename__ = "stock_transfers"
    __table_args__ = (
        CheckConstraint(
            "from_id != to_id", name="ck_stock_transfer_no_circular"
        ),
        UniqueConstraint(
            "id", "from_id", "to_id", name="uq_stock_transfer_route"
        ),
    )

    type: Mapped[TransferType] = mapped_column(
        Enum(TransferType, name="transfer_type_enum", native_enum=True),
        nullable=False,
        index=True,
    )
    status: Mapped[TransferStatus] = mapped_column(
        Enum(TransferStatus, name="transfer_status_enum", native_enum=True),
        nullable=False,
        default=TransferStatus.DRAFT,
        index=True,
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

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    accepted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    from_inventory: Mapped["Inventory"] = relationship(foreign_keys=[from_id])
    to_inventory: Mapped["Inventory"] = relationship(foreign_keys=[to_id])
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])
    accepted_by: Mapped["User | None"] = relationship(
        foreign_keys=[accepted_by_id]
    )
    order: Mapped["Order | None"] = relationship(
        back_populates="stock_transfers"
    )

    items: Mapped[list["StockTransferItem"]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["StockTransaction"]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan"
    )


class StockTransferItem(BaseModel):
    """
    Строки черновика накладной (Корзина).
    Сюда добавляют товары, пока статус DRAFT. Эта таблица НЕ влияет на остатки.
    """

    __tablename__ = "stock_transfer_items"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0", name="ck_stock_transfer_item_quantity_pos"
        ),
    )

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
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    transfer: Mapped["StockTransfer"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


class StockTransaction(BaseModel):
    """
    Строгий Леджер. Истина в последней инстанции для остатков.
    """

    __tablename__ = "stock_transactions"
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
    )
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

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    product: Mapped["Product"] = relationship()
    from_inventory: Mapped["Inventory"] = relationship(
        foreign_keys=[from_id], back_populates="outgoing_transactions"
    )
    to_inventory: Mapped["Inventory"] = relationship(
        foreign_keys=[to_id], back_populates="incoming_transactions"
    )
    transfer: Mapped["StockTransfer"] = relationship(
        back_populates="transactions"
    )
