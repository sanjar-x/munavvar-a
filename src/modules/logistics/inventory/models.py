import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import INTEGER, UUID, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel
from src.modules.logistics.inventory.enums import InventoryType

if TYPE_CHECKING:
    from src.modules.catalog.models import Product
    from src.modules.logistics.warehouse.models import Transfer
    from src.modules.orders.models import Order
    from src.modules.users.models import User

inventory_type_enum = Enum(
    InventoryType, name="inventory_type_enum", create_type=True
)


class Inventory(BaseModel):
    __tablename__ = "inventories"  # <--- ДОБАВИТЬ ЭТУ СТРОКУ
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(column="users.id", ondelete="RESTRICT"),
        index=True,  # Обязательно: поиск всех складов курьера
        comment="Кто материально ответственен за эту точку?",
    )
    type: Mapped[InventoryType] = mapped_column(
        inventory_type_enum,
        nullable=False,
        index=True,  # Важно для фильтрации по типам (все машины, все заводы)
    )
    name: Mapped[str] = mapped_column(
        VARCHAR(length=255),
        nullable=False,
        comment="Например: 'Склад №1', 'Машина Дамас 01A123BC'",
    )
    user: Mapped["User"] = relationship(back_populates="inventories")

    outgoing_transactions: Mapped[list["StockTransaction"]] = relationship(
        foreign_keys="[StockTransaction.from_id]",
        back_populates="from_inventory",
    )
    incoming_transactions: Mapped[list["StockTransaction"]] = relationship(
        foreign_keys="[StockTransaction.to_id]",
        back_populates="to_inventory",
    )


class StockTransaction(BaseModel):
    __table_args__ = (
        CheckConstraint(
            "(order_id IS NULL) OR (transfer_id IS NULL)",
            name="ck_stock_transaction_exclusive_document",
        ),
        CheckConstraint(
            "from_id != to_id", name="ck_stock_transaction_no_circular"
        ),
        CheckConstraint(
            "quantity > 0", name="ck_stock_transaction_quantity_positive"
        ),
        # 2. Индексы для сверхбыстрых расчетов остатков
        Index("idx_st_product_from", "product_id", "from_id"),
        Index("idx_st_product_to", "product_id", "to_id"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(column="products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # 3. Геометрия перемещения
    from_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(column="inventories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,  # Критично для расчета исходящих остатков
    )
    to_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(column="inventories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,  # Критично для расчета входящих остатков
    )

    quantity: Mapped[int] = mapped_column(INTEGER, nullable=False)

    # 4. Документы-основания
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(column="orders.id", ondelete="SET NULL"),
        index=True,
    )
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transfers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    product: Mapped["Product"] = relationship()
    from_inventory: Mapped["Inventory"] = relationship(
        foreign_keys=[from_id], back_populates="outgoing_transactions"
    )
    to_inventory: Mapped["Inventory"] = relationship(
        foreign_keys=[to_id], back_populates="incoming_transactions"
    )
    order: Mapped["Order"] = relationship(back_populates="stock_transactions")
    transfer: Mapped["Transfer"] = relationship(
        back_populates="stock_transactions"
    )
