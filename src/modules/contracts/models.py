# src/modules/contracts/models.py
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel
from src.modules.contracts.enums import ContractStatus, InvoiceStatus

if TYPE_CHECKING:
    from src.modules.orders.models import Order
    from src.modules.users.models import User
    # ContractPriceItem и Invoice определены в этом же файле —
    # не импортировать в TYPE_CHECKING (self-import).


class Contract(BaseModel):
    # __tablename__ = "contracts"  ← авто из BaseModel

    number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="Номер договора (HOD-2025-001)",
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="B2B клиент (role=CLIENT_B2B)",
    )
    status: Mapped[ContractStatus] = mapped_column(
        Enum(
            ContractStatus,
            name="contract_status_enum",
            native_enum=True,
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ContractStatus.DRAFT,
        index=True,
    )

    # Сроки
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="None = бессрочный договор",
    )

    # Финансовые условия
    credit_limit: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Кредитный лимит в тийинах. 0 = без ограничений.",
    )
    credit_used: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment=(
            "In-flight: сумма заказов в статусах NEW..ARRIVED, "
            "ещё не попавших на счёт. Обновляется приложением "
            "(не триггером) при create_order/complete_delivery."
        ),
    )
    payment_due_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        comment="Отсрочка платежа: Net-15, Net-30, Net-60",
    )

    # Реквизиты юр. лица (для документооборота)
    legal_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Полное юридическое название организации",
    )
    inn: Mapped[str] = mapped_column(
        String(14),
        nullable=False,
        comment="ИНН/ПИНФЛ юридического лица",
    )
    legal_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(
        String(25),
        nullable=True,
        comment="Расчётный счёт клиента (для актов сверки)",
    )
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Служебные поля
    notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Внутренние примечания"
    )
    signed_at: Mapped[datetime | None] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=True
    )
    signed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        comment="Кем активирован (admin user)",
    )
    suspended_at: Mapped[datetime | None] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=True
    )
    suspension_reason: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    terminated_at: Mapped[datetime | None] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=True
    )
    termination_reason: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )

    # Связи
    client: Mapped["User"] = relationship(
        foreign_keys=[client_id], lazy="raise"
    )
    signed_by: Mapped["User | None"] = relationship(
        foreign_keys=[signed_by_id], lazy="raise"
    )
    price_items: Mapped[list["ContractPriceItem"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    invoices: Mapped[list["Invoice"]] = relationship(
        back_populates="contract",
        # No cascade: ondelete="RESTRICT" on Invoice.contract_id
        # prevents deletion when invoices exist. passive_deletes
        # avoids SQLAlchemy loading all rows before the DB error.
        passive_deletes=True,
        lazy="raise",
    )
    orders: Mapped[list["Order"]] = relationship(
        back_populates="contract",
        foreign_keys="[Order.contract_id]",
        passive_deletes=True,
        lazy="raise",
    )
    status_logs: Mapped[list["ContractStatusLog"]] = relationship(
        back_populates="contract",
        # Append-only audit log — never delete. RESTRICT on FK.
        passive_deletes=True,
        lazy="raise",
        order_by="ContractStatusLog.created_at",
    )
    amendments: Mapped[list["ContractAmendment"]] = relationship(
        back_populates="contract",
        # Legal documents — never delete. RESTRICT on FK.
        passive_deletes=True,
        lazy="raise",
        order_by="ContractAmendment.effective_date",
    )

    __table_args__ = (
        CheckConstraint(
            "credit_limit >= 0",
            name="ck_contract_credit_limit_non_neg",
        ),
        CheckConstraint(
            "credit_used >= 0",
            name="ck_contract_credit_used_non_neg",
        ),
        CheckConstraint(
            "credit_used <= credit_limit OR credit_limit = 0",
            name="ck_contract_credit_used_le_limit",
        ),
        # ⚠️ Если admin уменьшает credit_limit ниже текущего
        # credit_used, любой последующий UPDATE строки contracts
        # завершится ошибкой CHECK constraint violation.
        # Решение: сервисный слой должен проверять
        # new_credit_limit >= credit_used перед UPDATE.
        CheckConstraint(
            "payment_due_days > 0",
            name="ck_contract_payment_due_days_pos",
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date > start_date",
            name="ck_contract_dates_order",
        ),
        # ОДИН активный договор на клиента
        # Partial unique index: только active+is_active строки
        Index(
            "uq_one_active_contract_per_client",
            "client_id",
            unique=True,
            postgresql_where=sa.text("status = 'active' AND is_active = true"),
        ),
        Index("idx_contract_client_status", "client_id", "status"),
        {"comment": "Договоры с юридическими лицами (B2B)"},
    )


class ContractPriceItem(BaseModel):
    # __tablename__ = "contract_price_items"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment=("Договор (CASCADE: при удалении договора — удаляются цены)"),
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    price: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Договорная цена в тийинах",
    )

    contract: Mapped["Contract"] = relationship(
        back_populates="price_items",
        lazy="raise",  # N+1 guard — загружать явно через selectinload
    )

    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "product_id",
            name="uq_contract_price_item_product",
        ),
        CheckConstraint(
            "price >= 0",
            name="ck_contract_price_item_price_non_neg",
        ),
        {
            "comment": (
                "Индивидуальный прайс-лист по договору. "
                "При отсутствии позиции — фолбэк на products.price."
            )
        },
    )


class Invoice(BaseModel):
    # __tablename__ = "invoices"

    number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Номер счёта (СФ-2025-001)",
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(
            InvoiceStatus,
            name="invoice_status_enum",
            native_enum=True,
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=InvoiceStatus.DRAFT,
        index=True,
    )

    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Сумма заказов за период",
    )
    due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment=("Срок оплаты = issued_at + contract.payment_due_days"),
    )
    issued_at: Mapped[datetime | None] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=True
    )

    contract: Mapped["Contract"] = relationship(
        back_populates="invoices",
        lazy="raise",
    )

    __table_args__ = (
        CheckConstraint(
            "period_to > period_from",
            name="ck_invoice_period_order",
        ),
        CheckConstraint(
            "amount >= 0",
            name="ck_invoice_amount_non_neg",
        ),
        UniqueConstraint(
            "contract_id",
            "number",
            name="uq_invoice_contract_number",
        ),
        {
            "comment": (
                "Счета-фактуры, выставляемые по биллинговому циклу договора"
            )
        },
    )


class ContractStatusLog(BaseModel):
    """Аудит-лог переходов статуса договора.

    Append-only — никогда не обновляется и не удаляется.
    changed_at = created_at из BaseModel.
    """

    # __tablename__ = "contract_status_logs"  ← авто из BaseModel

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[ContractStatus | None] = mapped_column(
        Enum(
            ContractStatus,
            name="contract_status_enum",
            native_enum=True,
            create_type=False,  # тип уже создан Contract
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
        comment="NULL = запись при создании договора",
    )
    to_status: Mapped[ContractStatus] = mapped_column(
        Enum(
            ContractStatus,
            name="contract_status_enum",
            native_enum=True,
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Кто изменил статус (admin); NULL = системное действие",
    )
    reason: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="Причина приостановки / расторжения / истечения",
    )

    contract: Mapped["Contract"] = relationship(
        back_populates="status_logs",
        lazy="raise",
    )

    __table_args__ = (
        Index("idx_contract_status_log_contract", "contract_id"),
        {"comment": "Append-only аудит переходов статуса договора"},
    )


class ContractAmendment(BaseModel):
    """Дополнительные соглашения к договору.

    Формализует изменения условий договора без замены основного документа.
    """

    # __tablename__ = "contract_amendments"  ← авто из BaseModel

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Номер ДС в рамках договора (ДС-001, ДС-002...)",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Описание изменений (что и почему изменилось)",
    )
    effective_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Дата вступления в силу доп. соглашения",
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Кто создал ДС (admin)",
    )

    contract: Mapped["Contract"] = relationship(
        back_populates="amendments",
        lazy="raise",
    )

    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "number",
            name="uq_contract_amendment_number",
        ),
        {"comment": "Дополнительные соглашения к договорам"},
    )
