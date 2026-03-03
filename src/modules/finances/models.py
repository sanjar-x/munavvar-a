# src/modules/finances.models.py
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import BIGINT, UUID, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel
from src.modules.finances.enums import AccountType, TransactionStatus

if TYPE_CHECKING:
    from src.modules.orders.models import Order
    from src.modules.users.models import User


account_type_enum = Enum(
    AccountType, name="account_type_enum", create_type=True
)
transaction_status_enum = Enum(
    TransactionStatus, name="transaction_status_enum", create_type=True
)


class Account(BaseModel):
    type: Mapped[AccountType] = mapped_column(
        account_type_enum, nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(column="users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(VARCHAR(length=255), nullable=False)

    balance: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="accounts")

    outgoing_transactions: Mapped[list["Transaction"]] = relationship(
        foreign_keys="[Transaction.from_id]",
        back_populates="from_account",
    )
    incoming_transactions: Mapped[list["Transaction"]] = relationship(
        foreign_keys="[Transaction.to_id]",
        back_populates="to_account",
    )


class Transaction(BaseModel):
    __tablename__ = "transactions"

    # 1. СТРОГИЕ ПРАВИЛА ЦЕЛОСТНОСТИ
    __table_args__ = (
        CheckConstraint(
            "amount > 0", name="check_transaction_amount_positive"
        ),
        CheckConstraint("from_id != to_id", name="check_no_self_transfer"),
        # Индекс для быстрых выписок по счету
        Index("idx_transaction_from_status", "from_id", "status"),
        Index("idx_transaction_to_status", "to_id", "status"),
    )

    from_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(column="accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    to_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(column="accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    amount: Mapped[int] = mapped_column(BIGINT, nullable=False)

    status: Mapped[TransactionStatus] = mapped_column(
        transaction_status_enum,
        nullable=False,
        default=TransactionStatus.COMPLETED,
        index=True,
    )

    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(column="orders.id", ondelete="SET NULL"),
        index=True,
    )
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(column="users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    reason: Mapped[str] = mapped_column(VARCHAR(length=255), nullable=False)

    # Связи
    from_account: Mapped["Account"] = relationship(
        foreign_keys=[from_id], back_populates="outgoing_transactions"
    )
    to_account: Mapped["Account"] = relationship(
        foreign_keys=[to_id], back_populates="incoming_transactions"
    )
    order: Mapped["Order"] = relationship(back_populates="transactions")
    verified_by: Mapped["User | None"] = relationship(
        foreign_keys=[verified_by_id]
    )
