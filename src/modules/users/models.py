# src/modules/users/models.py
import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel

if TYPE_CHECKING:
    from src.modules.finances.models import Account
    from src.modules.inventory.models import Inventory
    from src.modules.orders.models import Order


class Role(enum.Enum):
    SYSTEM = "system"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    STOREKEEPER = "storekeeper"
    CASHIER = "cashier"
    COURIER = "courier"
    CLIENT_B2C = "client_b2c"
    CLIENT_B2B = "client_b2b"


class AuthProvider(enum.Enum):
    LOCAL = "local"
    GOOGLE = "google"
    TELEGRAM = "telegram"
    APPLE = "apple"


class Identity(BaseModel):
    __tablename__ = "identities"  # Явно указываем для DBA
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, name="auth_provider_enum", create_type=True),
        nullable=False,
    )
    provider_identity_id: Mapped[str] = mapped_column(
        String(255), index=True, nullable=False
    )
    password_hash: Mapped[str | None] = mapped_column(String(255))

    user: Mapped["User"] = relationship(back_populates="identities")

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_identity_id",
            name="uq_identities_provider_identity_id",
        ),
    )


class User(BaseModel):
    username: Mapped[str] = mapped_column(
        String(length=255),
        nullable=False,
        comment="ФИО или Название компании",
    )
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role_enum", create_type=True),
        nullable=False,
        default=Role.CLIENT_B2C,
    )

    identities: Mapped[list["Identity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    accounts: Mapped[list["Account"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    inventories: Mapped[list["Inventory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    # НОВЫЕ СВЯЗИ ДЛЯ ЗАКАЗОВ
    client_orders: Mapped[list["Order"]] = relationship(
        "Order",
        foreign_keys="[Order.client_id]",
        back_populates="client",
        order_by="desc(Order.created_at)",
    )
    courier_orders: Mapped[list["Order"]] = relationship(
        "Order",
        foreign_keys="[Order.courier_id]",
        back_populates="courier",
        order_by="desc(Order.created_at)",
    )
