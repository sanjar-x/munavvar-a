import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Sequence,  # Добавь импорт
)
from sqlalchemy.dialects.postgresql import INTEGER, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel
from src.modules.logistics.warehouse.enums import TransferStatus

if TYPE_CHECKING:
    from src.modules.catalog.models import Product
    from src.modules.logistics.inventory.models import (
        Inventory,
        StockTransaction,
    )
    from src.modules.users.models import User

transfer_status_enum = Enum(
    TransferStatus, name="transfer_status_enum", create_type=True
)


class Transfer(BaseModel):
    __tablename__ = "transfers"

    # Бизнес-номер накладной (для людей)
    number: Mapped[int] = mapped_column(
        INTEGER,
        primary_key=False,  # У нас первичный ключ — UUID, поэтому это важно
        autoincrement=True,
        unique=True,
        index=True,
    )

    from_inventory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,  # Обязательно для выборок по складу
    )
    to_inventory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    initiator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[TransferStatus] = mapped_column(
        transfer_status_enum,
        nullable=False,
        default=TransferStatus.DRAFT,
        index=True,
    )

    __table_args__ = (
        CheckConstraint(
            "from_inventory_id != to_inventory_id",
            name="check_transfer_different_inventories",
        ),
    )

    items: Mapped[list["TransferItem"]] = relationship(
        back_populates="transfer",
        cascade="all, delete-orphan",
        passive_deletes=True,  # Позволяет БД самой удалить строки при CASCADE
    )

    from_inventory: Mapped["Inventory"] = relationship(
        foreign_keys=[from_inventory_id]
    )
    to_inventory: Mapped["Inventory"] = relationship(
        foreign_keys=[to_inventory_id]
    )
    initiator: Mapped["User"] = relationship(foreign_keys=[initiator_id])

    stock_transactions: Mapped[list["StockTransaction"]] = relationship(
        back_populates="transfer"
    )


class TransferItem(BaseModel):
    transfer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transfers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        INTEGER,
        CheckConstraint(
            "quantity > 0", name="check_transfer_item_quantity_positive"
        ),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_transfer_product_unique",
            "transfer_id",
            "product_id",
            unique=True,
        ),
    )

    transfer: Mapped["Transfer"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
