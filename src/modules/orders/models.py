# src/modules/orders/models.py
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import BIGINT, INTEGER, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel
from src.modules.orders.enums import OrderStatus, PaymentMethod, SaleType

if TYPE_CHECKING:
    from src.infrastructure.database.models import User
    from src.modules.catalog.models import Product
    from src.modules.contracts.models import Contract
    from src.modules.finances.models import Transaction
    from src.modules.inventory.models import Inventory, StockTransfer


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
        comment=(
            "Назначенный курьер"
            " (может быть пустым, пока заказ не взят в работу)"
        ),
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(
            PaymentMethod,
            name="payment_method_enum",
            native_enum=True,
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        comment="Намерение клиента по оплате: Наличные, Карта и т.д.",
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(
            OrderStatus,
            name="order_status_enum",
            native_enum=True,
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
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
    capitalization_applied: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
        comment="Было ли авто-оприходование тары при создании заказа",
    )
    sale_type: Mapped[SaleType] = mapped_column(
        Enum(
            SaleType,
            name="sale_type_enum",
            native_enum=True,
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=SaleType.DELIVERY,
        server_default="delivery",
        nullable=False,
        index=True,
        comment=(
            "Тип продажи: delivery (доставка) или warehouse_pickup (самовывоз)"
        ),
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Склад-источник (заполняется только для самовывоза)",
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment=(
            "Договор (обязателен при payment_method=CONTRACT, "
            "иначе NULL). ondelete=RESTRICT: нельзя удалить "
            "договор с привязанными заказами."
        ),
    )
    reserved_credit_amount: Mapped[int | None] = mapped_column(
        BIGINT,
        nullable=True,
        default=None,
        comment=(
            "Зарезервированная сумма кредита при создании заказа. "
            "Используется для корректного возврата credit_used "
            "при частичной доставке или отмене. "
            "NULL для не-CONTRACT заказов."
        ),
    )
    cancellation_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        default=None,
        comment="Причина отмены заказа (заполняется при CANCELLED)",
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        default=None,
        comment=(
            "Заметки / инструкции по доставке (например, код домофона, этаж)"
        ),
    )
    client: Mapped[User] = relationship(
        foreign_keys=[client_id],
        back_populates="client_orders",
    )
    client_inventory: Mapped[Inventory] = relationship(
        foreign_keys=[client_inventory_id]
    )
    warehouse: Mapped[Inventory | None] = relationship(
        foreign_keys=[warehouse_id],
    )
    courier: Mapped[User | None] = relationship(
        foreign_keys=[courier_id],
        back_populates="courier_orders",
    )
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )

    stock_transfers: Mapped[list[StockTransfer]] = relationship(
        "StockTransfer",
        back_populates="order",
        # No cascade: StockTransfer.order_id is RESTRICT — stock ledger
        # records must persist after order cancellation for audit.
        passive_deletes=True,
        lazy="raise",
    )
    transactions: Mapped[list[Transaction]] = relationship(
        "Transaction",
        back_populates="order",
        # No cascade: financial ledger is append-only; transactions
        # must never be deleted by ORM cascade.
        passive_deletes=True,
        lazy="raise",
    )
    contract: Mapped[Contract | None] = relationship(
        foreign_keys=[contract_id],
        back_populates="orders",
        lazy="raise",
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

    @property
    def total(self) -> int:
        return self.quantity * self.unit_price

    # --- Связи ---
    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_item_quantity_pos"),
        CheckConstraint("unit_price >= 0", name="ck_order_item_price_pos"),
        {"comment": "Строки (позиции) конкретного заказа"},
    )


class OrderStatusLog(BaseModel):
    """Лог переходов статуса заказа для аудита и аналитики."""

    __tablename__ = "order_status_logs"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_status: Mapped[OrderStatus | None] = mapped_column(
        Enum(
            OrderStatus,
            name="order_status_enum",
            native_enum=True,
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
        comment="Статус до перехода (NULL при создании)",
    )
    new_status: Mapped[OrderStatus] = mapped_column(
        Enum(
            OrderStatus,
            name="order_status_enum",
            native_enum=True,
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        comment="Статус после перехода",
    )
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Кто инициировал переход (NULL для системных)",
    )
    reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Причина перехода (при отмене/возврате)",
    )

    order: Mapped["Order"] = relationship()

    __table_args__ = (
        {"comment": ("Аудит-лог всех переходов статуса заказа")},
    )
