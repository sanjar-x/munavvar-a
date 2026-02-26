# src/modules/orders/models.py
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel
from src.modules.orders.enums import OrderStatus, PaymentMethod

# Используем TYPE_CHECKING для избежания циклических импортов
if TYPE_CHECKING:
    from src.modules.catalog.models import Product
    from src.modules.finances.models import Transaction
    from src.modules.users.models import User


class Order(BaseModel):
    # --- 1. Физические колонки в Базе Данных ---
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    courier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method_enum", create_type=True),
        nullable=False,
        comment="Намерение клиента по оплате: Наличные, Карта",
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status_enum", create_type=True),
        nullable=False,
        default=OrderStatus.NEW,
    )

    total_amount: Mapped[int] = mapped_column(
        INTEGER, default=0, nullable=False, comment="Сумма всего заказа"
    )
    client: Mapped["User"] = relationship(foreign_keys=[client_id])
    courier: Mapped["User | None"] = relationship(foreign_keys=[courier_id])
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="order"
    )


class OrderItem(BaseModel):
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(INTEGER, nullable=False)
    unit_price: Mapped[int] = mapped_column(
        INTEGER, nullable=False, comment="Цена за 1 шт на момент оформления"
    )
    # Связи
    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
