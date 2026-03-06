# src/modules/orders/models.py
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import BIGINT, INTEGER, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel
from src.modules.orders.enums import OrderStatus, PaymentMethod

if TYPE_CHECKING:
    from src.modules.catalog.models import Product
    from src.modules.finances.models import Transaction
    from src.modules.inventory.models import Inventory, StockTransfer
    from src.modules.users.models import User


class Order(BaseModel):
    __tablename__ = "orders"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Покупатель (B2B или B2C)",
    )
    client_inventory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Инвентарь (адрес) клиента для отгрузки товаров и тары",
    )
    courier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        comment="Назначенный курьер (может быть пустым, пока заказ не взят в работу)",
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(
            PaymentMethod,
            name="payment_method_enum",
            native_enum=True,
            create_type=True,
        ),
        nullable=False,
        comment="Намерение клиента по оплате: Наличные, Карта и т.д.",
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status_enum", native_enum=True, create_type=True),
        nullable=False,
        default=OrderStatus.NEW,
        index=True,
        comment="Текущий статус жизненного цикла заказа",
    )
    total_amount: Mapped[int] = mapped_column(
        BIGINT,
        default=0,
        nullable=False,
        comment="Сумма всего заказа",
    )
    client: Mapped["User"] = relationship(
        foreign_keys=[client_id],
        back_populates="client_orders",
    )
    client_inventory: Mapped["Inventory"] = relationship(
        foreign_keys=[client_inventory_id]
    )
    courier: Mapped["User | None"] = relationship(
        foreign_keys=[courier_id],
        back_populates="courier_orders",
    )
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )

    stock_transfers: Mapped[list["StockTransfer"]] = relationship(
        "StockTransfer",
        back_populates="order",
        cascade="all, delete-orphan",
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="order",
        cascade="all, delete-orphan",
    )

    __table_args__ = ({"comment": "Главная таблица заказов клиентов"},)


class OrderItem(BaseModel):
    __tablename__ = "order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
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
        INTEGER,
        nullable=False,
        comment="Количество позиций",
    )
    unit_price: Mapped[int] = mapped_column(
        BIGINT,
        nullable=False,
        comment="Цена за 1 шт на момент оформления (фиксируется исторически)",
    )

    # --- Связи ---
    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_item_quantity_pos"),
        CheckConstraint("unit_price >= 0", name="ck_order_item_price_pos"),
        {"comment": "Строки (позиции) конкретного заказа"},
    )
