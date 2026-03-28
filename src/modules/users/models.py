# src/modules/users/models.py
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel
from src.modules.users.enums import AuthProvider, Role

if TYPE_CHECKING:
    from src.modules.finances.models import Account
    from src.modules.inventory.models import Inventory
    from src.modules.orders.models import Order


class Identity(BaseModel):
    __tablename__ = "identities"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Ссылка на профиль пользователя",
    )
    provider: Mapped[AuthProvider] = mapped_column(
        Enum(
            AuthProvider,
            name="auth_provider_enum",
            native_enum=True,
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        comment="Провайдер авторизации (local, google, telegram и т.д.)",
    )
    provider_identity_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Уникальный ID у провайдера: номер телефона, email или субъект (sub) из OAuth",
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        comment="Хэш пароля (заполняется только для provider='local')",
    )

    user: Mapped["User"] = relationship(back_populates="identities")

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_identity_id",
            name="uq_identities_provider_identity_id",
        ),
        {
            "comment": "Учетные данные пользователей и привязки к соцсетям (OAuth)"
        },
    )


class User(BaseModel):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(
        String(length=255),
        nullable=False,
        comment="ФИО (для физлиц) или Название компании (для B2B)",
    )
    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            name="user_role_enum",
            native_enum=True,
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=Role.CLIENT_B2C,
        index=True,
        comment="Уровень доступа (роль) пользователя в системе",
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

    @property
    def phone(self) -> str | None:
        try:
            if self.identities:
                return self.identities[0].provider_identity_id
        except Exception:
            pass
        return None

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

    __table_args__ = (
        {"comment": "Глобальный реестр пользователей, клиентов и сотрудников"},
    )
