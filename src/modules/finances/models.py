# src/modules/finances/models.py
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import BIGINT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel
from src.modules.finances.enums import AccountType, TransactionStatus

if TYPE_CHECKING:
    from src.infrastructure.database.models import User
    from src.modules.orders.models import Order

account_type_enum = Enum(
    AccountType,
    name="account_type_enum",
    native_enum=True,
    create_type=True,
    values_callable=lambda e: [m.value for m in e],
)
transaction_status_enum = Enum(
    TransactionStatus,
    name="transaction_status_enum",
    native_enum=True,
    create_type=True,
    values_callable=lambda e: [m.value for m in e],
)


class Account(BaseModel):
    __tablename__ = "accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Владелец счета",
    )

    type: Mapped[AccountType] = mapped_column(
        account_type_enum,
        nullable=False,
        index=True,
        comment="Тип счета (CASH, CARD, DEBT, COMPANY_PROFIT)",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Название (например: 'Касса Водителя', 'Лицевой счет')",
    )
    balance: Mapped[int] = mapped_column(
        BIGINT,
        default=0,
        server_default=text("0"),
        nullable=False,
        comment=(
            "Текущий баланс. Обновляется строго через SQL-триггер транзакций!"
        ),
    )

    user: Mapped[User] = relationship(back_populates="accounts")

    outgoing_transactions: Mapped[list[Transaction]] = relationship(
        foreign_keys="[Transaction.from_id]",
        back_populates="from_account",
    )
    incoming_transactions: Mapped[list[Transaction]] = relationship(
        foreign_keys="[Transaction.to_id]",
        back_populates="to_account",
    )

    # --- Meta ---
    __table_args__ = (
        Index("idx_account_user_type", "user_id", "type"),
        {
            "comment": (
                "Счета для хранения денег (наличные, безнал, долги клиентов)"
            ),
        },
    )


class Transaction(BaseModel):
    __tablename__ = "transactions"

    # --- Foreign Keys ---
    from_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Счет списания",
    )
    to_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Счет зачисления",
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL"),
        index=True,
        comment="Заказ, за который прошла оплата (если есть)",
    )
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Сотрудник (бухгалтер), подтвердивший перевод",
    )

    amount: Mapped[int] = mapped_column(
        BIGINT,
        nullable=False,
        comment="Сумма перевода",
    )
    status: Mapped[TransactionStatus] = mapped_column(
        transaction_status_enum,
        nullable=False,
        default=TransactionStatus.PENDING,
        comment=(
            "Статус (PENDING - ожидание,"
            " COMPLETED - исполнено, REJECTED - отмена)"
        ),
    )
    reason: Mapped[str] = mapped_column(
        String(length=255),
        nullable=False,
        comment=(
            "Основание/Комментарий (например: 'Оплата картой по заказу #123')"
        ),
    )

    # --- Relationships ---
    from_account: Mapped[Account] = relationship(
        foreign_keys=[from_id], back_populates="outgoing_transactions"
    )
    to_account: Mapped[Account] = relationship(
        foreign_keys=[to_id], back_populates="incoming_transactions"
    )
    order: Mapped[Order | None] = relationship(back_populates="transactions")
    verified_by: Mapped[User | None] = relationship(
        foreign_keys=[verified_by_id]
    )

    # --- Meta ---
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transaction_amount_pos"),
        CheckConstraint(
            "from_id != to_id", name="ck_transaction_no_self_transfer"
        ),
        Index("idx_transaction_from_status", "from_id", "status"),
        Index("idx_transaction_to_status", "to_id", "status"),
        {
            "comment": (
                "Финансовый леджер (Event Sourcing)."
                " Строго только добавление (Append-only)"
            ),
        },
    )
