# Архитектурное исследование: Интеграция сущности «Договор» (Contract) для Юр. лиц — Senior Enterprise Edition

> **Статус:** Финальная редакция  
> **Покрытие:** Полный цикл — от ERD до тест-стратегии, включая race conditions, audit trail, Invoice lifecycle  
> **Глубина:** Все файлы codebase изучены вживую. Ссылки на конкретные строки кода.

---

## 1. Диагностика текущего состояния

### 1.1 Клиентские типы и их текущий учёт

| Тип               | Роль        | PaymentMethod          | Финансовое закрытие                                                        | Статус                                 |
| ----------------- | ----------- | ---------------------- | -------------------------------------------------------------------------- | -------------------------------------- |
| Анонимный Walk-in | SYSTEM user | CASH                   | Revenue→Client→Cash (COMPLETED), затем списание в VIRTUAL_LOSS             | ✅ Полностью реализован                |
| B2C (физлицо)     | CLIENT_B2C  | CASH / CARD            | Revenue→Client + Client→Courier/Card                                       | ✅ Полностью реализован                |
| B2B (юрлицо)      | CLIENT_B2B  | CASH / CARD / CONTRACT | CONTRACT: только Revenue→Client (COMPLETED). Долг висит на Account.balance | ⚠️ Долг накапливается, но нет договора |

### 1.2 Что уже есть в codebase (не нужно создавать)

Из реального чтения кода:

```python
# src/modules/orders/enums.py
class PaymentMethod(enum.StrEnum):
    CASH = "cash"
    CARD = "card"
    CONTRACT = "contract"   # ✅ уже есть

# src/modules/finances/enums.py
class AccountType(enum.StrEnum):
    BANK = "bank"           # ✅ уже есть (системный расчётный счёт)

# src/modules/finances/repositories.py
async def get_system_bank_account(self) -> Account | None:  # ✅ уже есть

# src/core/security/permissions.py
Scope.BILLS_READ = "bills:read"  # ✅ уже есть для CLIENT_B2B и ACCOUNTANT
```

```python
# src/modules/orders/services.py — строки 1152–1154
# CONTRACT: только Revenue → Client, долг остается
# на балансе клиента до оплаты по договору
# (ветка CONTRACT в _process_financial_settlement уже корректна)
```

```python
# src/common/repository.py
async def get(
    self, id: uuid.UUID,
    active_only: bool = True,
    with_for_update: bool = False,   # ✅ FOR UPDATE уже реализован
) -> ModelType | None:
    ...
    if with_for_update:
        query = query.with_for_update()
```

### 1.3 Критические пробелы (то, чего нет)

| Пробел                   | Файл                                  | Последствие                                          |
| ------------------------ | ------------------------------------- | ---------------------------------------------------- |
| Модель `Contract`        | не существует                         | B2B заказы юридически не обоснованы                  |
| `Order.contract_id`      | `src/modules/orders/models.py`        | Нет привязки заказа к договору                       |
| Индивидуальный прайс     | не существует                         | Все B2B платят по общему каталогу                    |
| Кредитный лимит          | не существует                         | Долг может расти бесконечно — финансовый риск        |
| `credit_used`            | не существует                         | Race condition при параллельных заказах              |
| Invoice (счёт-фактура)   | не существует                         | Нет документооборота                                 |
| `accept_payment("bank")` | `src/modules/finances/schemas.py:282` | Поддерживается только `cash\|card`                   |
| Scopes contracts:\*      | `src/core/security/permissions.py`    | RBAC не настроен                                     |
| `contracts.dependencies` | не существует                         | `conftest.py` `_SESSION_FACTORY_MODULES` не обновлён |

---

## 2. Модель данных — полная схема

### 2.1 Новые сущности

#### 2.1.1 Contract (Договор)

```python
# src/modules/contracts/models.py

import enum
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
from src.modules.contracts.enums import ContractStatus

if TYPE_CHECKING:
    from src.infrastructure.database.models import User
    from src.modules.orders.models import Order
    # NOTE: ContractPriceItem и Invoice определены в этом же файле —
    # импортировать их в TYPE_CHECKING нельзя (self-import).
    # В аннотациях Mapped[] используются строковые forward refs:
    # Mapped[list["ContractPriceItem"]], Mapped[list["Invoice"]].


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
    start_date: Mapped[date] = mapped_column(
        Date, nullable=False
    )
    end_date: Mapped[date | None] = mapped_column(
        Date, nullable=True,
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
        String(255), nullable=False,
        comment="Полное юридическое название организации",
    )
    inn: Mapped[str] = mapped_column(
        String(14), nullable=False,
        comment="ИНН/ПИНФЛ юридического лица",
    )
    legal_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(
        String(25), nullable=True,
        comment="Расчётный счёт клиента (для актов сверки)",
    )
    bank_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

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
        cascade="all, delete-orphan",
        lazy="raise",
    )
    orders: Mapped[list["Order"]] = relationship(
        back_populates="contract",
        foreign_keys="[Order.contract_id]",
        lazy="raise",
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
        # ⚠️ ВАЖНО: Если admin уменьшает credit_limit ниже текущего
        # credit_used, любой последующий UPDATE строки contracts
        # завершится ошибкой CHECK constraint violation.
        # Решение: сервисный слой должен проверять
        # new_credit_limit >= credit_used перед UPDATE,
        # либо использовать DEFERRABLE INITIALLY DEFERRED constraint.
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
            postgresql_where=sa.text(
                "status = 'active' AND is_active = true"
            ),
        ),
        Index("idx_contract_client_status", "client_id", "status"),
        {"comment": "Договоры с юридическими лицами (B2B)"},
    )
```

#### 2.1.2 ContractPriceItem (Позиция прайс-листа)

```python
class ContractPriceItem(BaseModel):
    # __tablename__ = "contract_price_items"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Договор (CASCADE: при удалении договора — удаляются цены)",
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
            "price >= 0", name="ck_contract_price_item_price_non_neg"
        ),
        {
            "comment": (
                "Индивидуальный прайс-лист по договору. "
                "При отсутствии позиции — фолбэк на products.price."
            )
        },
    )
```

#### 2.1.3 Invoice (Счёт-фактура)

```python
# Invoice — вторая фаза. Полный код здесь для проектирования.

class Invoice(BaseModel):
    # __tablename__ = "invoices"

    number: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Номер счёта (СФ-2025-001)",
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status_enum", ...),
        nullable=False,
        default=InvoiceStatus.DRAFT,
        index=True,
    )

    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Сумма заказов за период",
    )
    due_date: Mapped[date | None] = mapped_column(
        Date, nullable=True,
        comment="Срок оплаты = issued_at + contract.payment_due_days",
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
            "contract_id", "number",
            name="uq_invoice_contract_number",
        ),
        {"comment": "Счета-фактуры, выставляемые по биллинговому циклу договора"},
    )
```

### 2.2 Изменения в существующих моделях

#### 2.2.1 Order — добавить contract_id

```python
# src/modules/orders/models.py — добавить в класс Order:

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

    # В TYPE_CHECKING секцию добавить:
    # from src.modules.contracts.models import Contract

    contract: Mapped["Contract | None"] = relationship(
        foreign_keys=[contract_id],
        back_populates="orders",
        lazy="raise",
    )
```

**Почему `lazy="raise"` на relationship?** В `search_orders()` и `get_with_details()` используется `joinedload` — явно. `lazy="raise"` предотвращает случайные N+1 запросы, которые были бы незаметны при `lazy="select"`.

### 2.3 ERD (полная схема связей)

```
┌────────────────────────────┐
│          users             │
│  id (PK, UUIDv7)           │
│  username                  │
│  role (CLIENT_B2B)         │
└──────────────┬─────────────┘
               │ 1
               │
               ▼ N
┌──────────────────────────────────────────────────────────────┐
│                        contracts                             │
│  id (PK, UUIDv7)                                             │
│  client_id ──────────────────────────────── FK → users.id    │
│  number (UNIQUE)                                             │
│  status (DRAFT/ACTIVE/SUSPENDED/TERMINATED/EXPIRED)          │
│  credit_limit (0 = unlimited)                                │
│  credit_used  ← приложение обновляет (НЕ триггер)            │
│  payment_due_days                                            │
│  start_date / end_date (NULL = бессрочный)                   │
│  legal_name, inn, legal_address, bank_account_number         │
│  signed_by_id ──────────────────────────────── FK → users.id │
│  PARTIAL UNIQUE INDEX: (client_id) WHERE status='active'     │
└───────────┬──────────────────────────────────────────────────┘
            │ 1                              │ 1
            │                                │
            ▼ N                             ▼ N
┌───────────────────────┐   ┌───────────────────────────────────┐
│   contract_price_items│   │           invoices                │
│  id                   │   │  id                               │
│  contract_id ─→ FK    │   │  contract_id ─→ FK                │
│  product_id ──→ FK    │   │  number (UNIQUE per contract)     │
│  price (override)     │   │  status (DRAFT/ISSUED/PAID/etc.)  │
│  UNIQUE(cid, pid)     │   │  period_from / period_to          │
└───────────────────────┘   │  amount / due_date / paid_at      │
                            └───────────────────────────────────┘
            │ 1
            │
            ▼ N
┌───────────────────────────────────────────────┐
│                  orders                       │
│  id                                           │
│  client_id ──────────────── FK → users.id     │
│  contract_id (nullable) ─── FK → contracts.id │
│  payment_method (CONTRACT)                    │
│  total_amount                                 │
│  status (NEW → ... → DELIVERED)               │
└───────────────────────────────────────────────┘
```

---

## 3. Перечисления (Enums)

```python
# src/modules/contracts/enums.py

import enum


class ContractStatus(enum.StrEnum):
    DRAFT = "draft"           # Создан, условия согласовываются
    ACTIVE = "active"         # Подписан, заказы разрешены
    SUSPENDED = "suspended"   # Приостановлен (просрочка/нарушение)
    TERMINATED = "terminated" # Расторгнут досрочно
    EXPIRED = "expired"       # Истёк end_date


class InvoiceStatus(enum.StrEnum):
    DRAFT = "draft"           # Формируется автоматически
    ISSUED = "issued"         # Выставлен клиенту
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"             # Полностью погашен
    OVERDUE = "overdue"       # Срок оплаты прошёл
    CANCELLED = "cancelled"   # Аннулирован
```

**Конечный автомат договора:**

```
         ┌─────────────────────────────────────┐
         │                                     │
    ┌────▼────┐   activate()   ┌──────────┐    │
    │  DRAFT  │──────────────▶ │  ACTIVE  │    │
    └─────────┘                └────┬─────┘    │
                                    │          │
                         suspend()  │          │ reinstate()
                                    ▼          │
                               ┌───────────┐   │
                               │ SUSPENDED │───┘
                               └─────┬─────┘
                                     │ terminate()
                                     ▼
                               ┌────────────┐
                               │ TERMINATED │
                               └────────────┘
    ACTIVE ─────(end_date прошёл)────▶ EXPIRED
```

**Правила переходов:**

| Из → В                 | Метод         | Кто    | Условие                            |
| ---------------------- | ------------- | ------ | ---------------------------------- |
| DRAFT → ACTIVE         | `activate()`  | ADMIN  | `signed_at` должен быть установлен |
| ACTIVE → SUSPENDED     | `suspend()`   | ADMIN  | Есть причина (reason обязателен)   |
| SUSPENDED → ACTIVE     | `reinstate()` | ADMIN  | Клиент погасил задолженность       |
| ACTIVE → TERMINATED    | `terminate()` | ADMIN  | Есть причина                       |
| SUSPENDED → TERMINATED | `terminate()` | ADMIN  | Есть причина                       |
| ACTIVE → EXPIRED       | автомат/check | System | `end_date < today` (если не NULL)  |

---

## 4. Репозитории

```python
# src/modules/contracts/repositories.py

import uuid
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from src.common.repository import BaseRepository
from src.modules.contracts.enums import ContractStatus
from src.modules.contracts.models import Contract, ContractPriceItem, Invoice


class ContractRepository(BaseRepository[Contract]):
    def __init__(self, session):
        super().__init__(model=Contract, session=session)

    async def get_active_for_client(
        self,
        client_id: uuid.UUID,
        with_for_update: bool = False,
    ) -> Contract | None:
        """Активный договор клиента.
        with_for_update=True — при проверке кредитного лимита
        для предотвращения race condition.
        """
        query = (
            select(Contract)
            .where(
                Contract.client_id == client_id,
                Contract.status == ContractStatus.ACTIVE,
                Contract.is_active.is_(True),
            )
        )
        if with_for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_with_price_items(
        self,
        contract_id: uuid.UUID,
    ) -> Contract | None:
        """Договор с eager-loaded прайс-листом (для API ответа)."""
        query = (
            select(Contract)
            .options(selectinload(Contract.price_items))
            .where(
                Contract.id == contract_id,
                Contract.is_active.is_(True),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_price_map_for_products(
        self,
        contract_id: uuid.UUID,
        product_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, int]:
        """Возвращает {product_id: price} из договорного прайс-листа.
        Только для запрошенных product_ids.
        Используется в create_order() для override каталожных цен.
        """
        if not product_ids:
            return {}
        query = select(ContractPriceItem).where(
            ContractPriceItem.contract_id == contract_id,
            ContractPriceItem.product_id.in_(product_ids),
            ContractPriceItem.is_active.is_(True),
        )
        result = await self.session.execute(query)
        items = result.scalars().all()
        return {item.product_id: item.price for item in items}

    async def get_multi_with_client(
        self,
        status: ContractStatus | None,
        client_id: uuid.UUID | None,
        skip: int,
        limit: int,
    ) -> tuple[int, Sequence[Contract]]:
        """Пагинированный список договоров (backoffice)."""
        base = (
            select(Contract)
            .options(joinedload(Contract.client))
            .where(Contract.is_active.is_(True))
        )
        count_q = (
            sa.select(sa.func.count())
            .select_from(Contract)
            .where(Contract.is_active.is_(True))
        )
        if status:
            base = base.where(Contract.status == status)
            count_q = count_q.where(Contract.status == status)
        if client_id:
            base = base.where(Contract.client_id == client_id)
            count_q = count_q.where(Contract.client_id == client_id)

        total = (await self.session.execute(count_q)).scalar() or 0
        result = await self.session.execute(
            base.order_by(Contract.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return total, result.scalars().unique().all()

    async def increment_credit_used(
        self,
        contract_id: uuid.UUID,
        amount: int,
    ) -> None:
        """Атомарный инкремент credit_used при создании заказа.
        Вызывается ПОСЛЕ lock на строку договора (with_for_update=True).
        """
        stmt = (
            sa.update(Contract)
            .where(Contract.id == contract_id)
            .values(credit_used=Contract.credit_used + amount)
        )
        await self.session.execute(stmt)

    async def decrement_credit_used(
        self,
        contract_id: uuid.UUID,
        amount: int,
    ) -> None:
        """Уменьшение credit_used при завершении доставки.
        Долг переходит с credit_used на account.balance (через триггер).
        """
        stmt = (
            sa.update(Contract)
            .where(Contract.id == contract_id)
            .values(
                credit_used=sa.func.greatest(
                    Contract.credit_used - amount, 0
                )
            )
        )
        await self.session.execute(stmt)


class ContractPriceItemRepository(
    BaseRepository[ContractPriceItem]
):
    def __init__(self, session):
        super().__init__(model=ContractPriceItem, session=session)

    async def get_by_contract_and_product(
        self,
        contract_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> ContractPriceItem | None:
        return await self.get_by(
            contract_id=contract_id,
            product_id=product_id,
        )


class InvoiceRepository(BaseRepository[Invoice]):
    def __init__(self, session):
        super().__init__(model=Invoice, session=session)
```

### 4.2 Дополнение OrderRepository

```python
# src/modules/orders/repositories.py — добавить метод:

from src.modules.orders.enums import OrderStatus

class OrderRepository(BaseRepository[Order]):
    # ... существующие методы ...

    async def get_delivered_by_contract(
        self,
        contract_id: uuid.UUID,
        date_from: date,
        date_to: date,
    ) -> Sequence[Order]:
        """Все выполненные заказы по договору за период.
        Используется при генерации Invoice и Reconciliation.
        """
        query = (
            select(Order)
            .where(
                Order.contract_id == contract_id,
                Order.status.in_([
                    OrderStatus.DELIVERED,
                    OrderStatus.PICKUP_COMPLETED,
                ]),
                Order.created_at >= date_from,
                Order.created_at < date_to,
                Order.is_active.is_(True),
            )
            .order_by(Order.created_at)
        )
        result = await self.session.execute(query)
        return result.scalars().all()
```

---

## 5. Unit of Work

```python
# src/modules/contracts/uow.py

from src.common.uow import IUnitOfWork
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.contracts.repositories import (
    ContractPriceItemRepository,
    ContractRepository,
    InvoiceRepository,
)
from src.modules.orders.repositories import OrderRepository


class IContractUnitOfWork(IUnitOfWork):
    contracts: ContractRepository
    price_items: ContractPriceItemRepository
    invoices: InvoiceRepository
    orders: OrderRepository  # ← нужен для generate_invoice()


class ContractUnitOfWork(BaseSQLAlchemyUoW, IContractUnitOfWork):
    async def __aenter__(self) -> "ContractUnitOfWork":
        await super().__aenter__()
        self.contracts = ContractRepository(session=self.session)
        self.price_items = ContractPriceItemRepository(
            session=self.session
        )
        self.invoices = InvoiceRepository(session=self.session)
        self.orders = OrderRepository(session=self.session)  # ← НОВОЕ
        return self
```

---

## 6. Сервис

```python
# src/modules/contracts/services.py

class ContractService:
    """Управление договорами с юридическими лицами.

    Бизнес-инварианты:
    - Один клиент → один ACTIVE договор (partial unique index)
    - credit_used: обновляется приложением (не триггером)
    - credit_limit == 0 → безлимитный договор
    - Только ACTIVE договоры разрешают создание заказов
    - Snapshot pricing: цена фиксируется в OrderItem.unit_price
    """

    def __init__(self, uow: IContractUnitOfWork):
        self.uow = uow

    # ─── LIFECYCLE ───────────────────────────────────────────────

    async def create_contract(
        self,
        client_id: uuid.UUID,
        dto: ContractCreate,
    ) -> Contract:
        """Создать договор в статусе DRAFT.
        Проверяет, что у клиента нет другого ACTIVE договора.
        DRAFT-дубликаты разрешены (обсуждение условий).
        """
        async with self.uow:
            # Проверяем коллизию (active)
            existing = await self.uow.contracts.get_active_for_client(
                client_id
            )
            if existing:
                raise ContractAlreadyActiveError(
                    client_id=client_id,
                    existing_contract_id=existing.id,
                )
            contract = await self.uow.contracts.add({
                "client_id": client_id,
                "number": dto.number,
                "status": ContractStatus.DRAFT,
                "start_date": dto.start_date,
                "end_date": dto.end_date,
                "credit_limit": dto.credit_limit,
                "payment_due_days": dto.payment_due_days,
                "legal_name": dto.legal_name,
                "inn": dto.inn,
                "legal_address": dto.legal_address,
                "bank_account_number": dto.bank_account_number,
                "bank_name": dto.bank_name,
                "notes": dto.notes,
            })
            await self.uow.commit()
            return contract

    async def activate_contract(
        self,
        contract_id: uuid.UUID,
        signed_by_id: uuid.UUID,
    ) -> Contract:
        """DRAFT → ACTIVE. Подписание договора.

        Raises:
            ContractNotFoundError: договор не найден
            ContractNotActiveError: если статус не DRAFT
            ContractAlreadyActiveError: если у клиента уже ACTIVE
        """
        async with self.uow:
            contract = await self.uow.contracts.get(
                contract_id, with_for_update=True
            )
            if not contract:
                raise ContractNotFoundError(contract_id)

            if contract.status != ContractStatus.DRAFT:
                raise ContractStatusTransitionError(
                    contract_id=contract_id,
                    current=contract.status,
                    target=ContractStatus.ACTIVE,
                )

            # Проверяем коллизию активных
            existing = await self.uow.contracts.get_active_for_client(
                contract.client_id
            )
            if existing and existing.id != contract_id:
                raise ContractAlreadyActiveError(
                    client_id=contract.client_id,
                    existing_contract_id=existing.id,
                )

            updated = await self.uow.contracts.update(
                contract_id,
                {
                    "status": ContractStatus.ACTIVE,
                    "signed_at": datetime.now(tz=timezone.utc),
                    "signed_by_id": signed_by_id,
                },
            )
            await self.uow.commit()
            return updated

    async def suspend_contract(
        self,
        contract_id: uuid.UUID,
        reason: str,
    ) -> Contract:
        """ACTIVE → SUSPENDED."""
        async with self.uow:
            contract = await self.uow.contracts.get(
                contract_id, with_for_update=True
            )
            if not contract:
                raise ContractNotFoundError(contract_id)
            if contract.status != ContractStatus.ACTIVE:
                raise ContractStatusTransitionError(
                    contract_id=contract_id,
                    current=contract.status,
                    target=ContractStatus.SUSPENDED,
                )
            updated = await self.uow.contracts.update(
                contract_id,
                {
                    "status": ContractStatus.SUSPENDED,
                    "suspended_at": datetime.now(tz=timezone.utc),
                    "suspension_reason": reason,
                },
            )
            await self.uow.commit()
            return updated

    async def reinstate_contract(
        self, contract_id: uuid.UUID
    ) -> Contract:
        """SUSPENDED → ACTIVE."""
        ...  # Аналогично suspend_contract

    async def terminate_contract(
        self,
        contract_id: uuid.UUID,
        reason: str,
    ) -> Contract:
        """ACTIVE/SUSPENDED → TERMINATED."""
        ...

    # ─── ЦЕНООБРАЗОВАНИЕ ─────────────────────────────────────────

    async def set_price_item(
        self,
        contract_id: uuid.UUID,
        product_id: uuid.UUID,
        price: int,
    ) -> ContractPriceItem:
        """Установить/обновить договорную цену на товар.
        Идемпотентна: если позиция уже есть — обновляет.
        """
        async with self.uow:
            existing = (
                await self.uow.price_items
                .get_by_contract_and_product(
                    contract_id, product_id
                )
            )
            if existing:
                item = await self.uow.price_items.update(
                    existing.id, {"price": price}
                )
            else:
                item = await self.uow.price_items.add({
                    "contract_id": contract_id,
                    "product_id": product_id,
                    "price": price,
                })
            await self.uow.commit()
            return item

    async def remove_price_item(
        self,
        contract_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> None:
        """Удалить позицию из прайс-листа → фолбэк на каталог."""
        async with self.uow:
            item = (
                await self.uow.price_items
                .get_by_contract_and_product(
                    contract_id, product_id
                )
            )
            if not item:
                raise ContractPriceItemNotFoundError(
                    contract_id, product_id
                )
            await self.uow.price_items.delete(item.id)
            await self.uow.commit()

    # ─── QUERY ───────────────────────────────────────────────────

    async def get_active_contract(
        self, client_id: uuid.UUID
    ) -> Contract | None:
        async with self.uow:
            return await self.uow.contracts.get_active_for_client(
                client_id
            )

    async def get_contract_with_prices(
        self, contract_id: uuid.UUID
    ) -> Contract:
        async with self.uow:
            contract = await self.uow.contracts.get_with_price_items(
                contract_id
            )
            if not contract:
                raise ContractNotFoundError(contract_id)
            return contract
```

---

## 7. Исключения модуля

```python
# src/modules/contracts/exceptions.py

import uuid
from src.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)


class ContractNotFoundError(NotFoundError):
    def __init__(self, contract_id: uuid.UUID | str):
        super().__init__(
            message="Договор не найден",
            error_code="CONTRACT_NOT_FOUND",
            details={"contract_id": str(contract_id)},
        )


class ContractNotActiveError(BadRequestError):
    """Попытка создать заказ по неактивному договору."""
    def __init__(
        self,
        contract_id: uuid.UUID | str,
        status: str,
    ):
        super().__init__(
            message=(
                f"Договор недоступен для оформления заказов "
                f"(статус: {status})"
            ),
            error_code="CONTRACT_NOT_ACTIVE",
            details={
                "contract_id": str(contract_id),
                "status": status,
            },
        )


class ContractExpiredError(BadRequestError):
    """end_date договора уже прошла."""
    def __init__(self, contract_id: uuid.UUID | str):
        super().__init__(
            message="Срок действия договора истёк",
            error_code="CONTRACT_EXPIRED",
            details={"contract_id": str(contract_id)},
        )


class CreditLimitExceededError(BadRequestError):
    """Заказ превысит кредитный лимит."""
    def __init__(
        self,
        contract_id: uuid.UUID | str,
        credit_limit: int,
        current_exposure: int,
        order_amount: int,
    ):
        super().__init__(
            message=(
                "Кредитный лимит по договору будет превышен. "
                "Погасите задолженность или уменьшите заказ."
            ),
            error_code="CREDIT_LIMIT_EXCEEDED",
            details={
                "contract_id": str(contract_id),
                "credit_limit": credit_limit,
                "current_exposure": current_exposure,
                "order_amount": order_amount,
                "overage": (
                    current_exposure + order_amount - credit_limit
                ),
            },
        )


class ContractAlreadyActiveError(ConflictError):
    """У клиента уже есть ACTIVE договор."""
    def __init__(
        self,
        client_id: uuid.UUID | str,
        existing_contract_id: uuid.UUID | str,
    ):
        super().__init__(
            message=(
                "У клиента уже есть действующий договор. "
                "Расторгните его перед созданием нового."
            ),
            error_code="CONTRACT_ALREADY_ACTIVE",
            details={
                "client_id": str(client_id),
                "existing_contract_id": str(existing_contract_id),
            },
        )


class ContractStatusTransitionError(ConflictError):
    """Недопустимый переход статуса договора."""
    def __init__(
        self,
        contract_id: uuid.UUID | str,
        current: str,
        target: str,
    ):
        super().__init__(
            message=(
                f"Невозможно перевести договор из "
                f"статуса {current} в {target}"
            ),
            error_code="CONTRACT_STATUS_TRANSITION_ERROR",
            details={
                "contract_id": str(contract_id),
                "current_status": current,
                "target_status": target,
            },
        )


class ContractRequiredError(BadRequestError):
    """PaymentMethod=CONTRACT, но contract_id не указан."""
    def __init__(self, client_id: uuid.UUID | str):
        super().__init__(
            message=(
                "Для оплаты по договору необходимо наличие "
                "активного договора. Обратитесь к менеджеру."
            ),
            error_code="CONTRACT_REQUIRED",
            details={"client_id": str(client_id)},
        )


class ContractPriceItemNotFoundError(NotFoundError):
    def __init__(
        self,
        contract_id: uuid.UUID | str,
        product_id: uuid.UUID | str,
    ):
        super().__init__(
            message="Позиция прайс-листа не найдена",
            error_code="CONTRACT_PRICE_ITEM_NOT_FOUND",
            details={
                "contract_id": str(contract_id),
                "product_id": str(product_id),
            },
        )


class ContractAccessDeniedError(ForbiddenError):
    """Клиент пытается просмотреть чужой договор (IDOR)."""
    def __init__(
        self,
        client_id: uuid.UUID | str,
        contract_id: uuid.UUID | str,
    ):
        super().__init__(
            message="У вас нет доступа к этому договору",
            error_code="CONTRACT_ACCESS_DENIED",
            details={
                "client_id": str(client_id),
                "contract_id": str(contract_id),
            },
        )
```

---

## 8. Интеграция в OrderService (самая критичная часть)

### 8.1 Изменения в BaseOrderUnitOfWork

```python
# src/modules/orders/uow.py — добавить ContractRepository

from src.modules.contracts.repositories import ContractRepository

# ⚠️ В orders/uow.py НЕТ интерфейса IBaseOrderUnitOfWork.
# BaseOrderUnitOfWork наследует только от BaseSQLAlchemyUoW.
# class-level аннотации объявлены прямо на конкретном классе.
# Добавить contracts туда же:

class BaseOrderUnitOfWork(BaseSQLAlchemyUoW):
    # существующие аннотации (не менять):
    orders: OrderRepository
    order_items: OrderItemRepository
    users: UserRepository
    inventories: InventoryRepository
    transfers: StockTransferRepository
    transfer_items: StockTransferItemRepository
    transactions: StockTransactionRepository         # ← поле называется 'transactions', не 'stock_transactions'
    accounts: AccountRepository
    financial_transactions: FinancialTransactionRepository
    contracts: ContractRepository  # ← НОВОЕ class-level annotation

    async def __aenter__(self) -> "BaseOrderUnitOfWork":
        await super().__aenter__()
        # существующие (не менять):
        self.orders = OrderRepository(session=self.session)
        self.order_items = OrderItemRepository(session=self.session)
        self.users = UserRepository(session=self.session)
        self.inventories = InventoryRepository(session=self.session)
        self.transfers = StockTransferRepository(session=self.session)
        self.transfer_items = StockTransferItemRepository(session=self.session)
        self.transactions = StockTransactionRepository(session=self.session)
        self.accounts = AccountRepository(session=self.session)
        self.financial_transactions = FinancialTransactionRepository(session=self.session)
        # НОВОЕ:
        self.contracts = ContractRepository(session=self.session)
        return self
```

### 8.2 Изменения в create_order()

Критичные точки интеграции (строки 140–277 в `src/modules/orders/services.py`).

> **⚠️ Ключевое архитектурное решение:** Вся логика Contract — валидация
> статуса, override цен и резервирование кредита — выполняется ВНУТРИ
> `async with self.uow`, после SELECT FOR UPDATE на строку договора.
> Это устраняет TOCTOU-окно и не требует отдельного `contract_service`
> в `BaseOrderService` (у него нет такого поля — только `catalog_service`).

```python
async def create_order(
    self, client_id: uuid.UUID, dto: OrderCreate
) -> Order:
    if not dto.items:
        raise EmptyCartError()

    # 1. Каталожные цены — catalog_service имеет собственный UoW,
    #    запрос идёт вне основной транзакции (существующий код)
    product_ids = [item.product_id for item in dto.items]
    products = await self.catalog_service.get_by_ids(product_ids)
    price_map = {p.id: p.price for p in products}

    missing_ids = [
        pid for pid in product_ids if pid not in price_map
    ]
    if missing_ids:
        raise ProductsUnavailableError(missing_product_ids=missing_ids)

    # 2. Тара (без изменений — только вычисления, без DB)
    exchange_items = [...]

    async with self.uow:
        # --- НОВЫЙ БЛОК A: CONTRACT — валидация + override цен ---
        contract: Contract | None = None
        if dto.payment_method == PaymentMethod.CONTRACT:
            # ① Роль: только CLIENT_B2B. Проверка здесь, а не в роутере,
            #    потому что RBAC-scope ORDERS_CREATE есть и у CLIENT_B2C.
            #    Этот guard предотвращает CONTRACT-заказы от B2C-клиентов.
            client_user = await self.uow.users.get(client_id)
            if not client_user or client_user.role != Role.CLIENT_B2B:
                raise BadRequestError(
                    message=(
                        "Оплата по договору доступна только "
                        "юридическим лицам (B2B)"
                    ),
                    error_code="CONTRACT_PAYMENT_NOT_ALLOWED",
                    details={
                        "role": (
                            str(client_user.role)
                            if client_user
                            else "unknown"
                        )
                    },
                )

            # ② SELECT FOR UPDATE: блокируем строку договора.
            # Это одновременно:
            #   a) сериализует параллельные заказы (credit_used race)
            #   b) устраняет TOCTOU: статус проверяем ПОСЛЕ блокировки
            contract = await self._get_and_validate_contract_locked(
                client_id
            )

            # Override каталожных цен договорными (фолбэк на каталог)
            contract_prices = (
                await self.uow.contracts.get_price_map_for_products(
                    contract.id, product_ids
                )
            )
            price_map.update(contract_prices)
        # --- КОНЕЦ БЛОКА A ---

        # 3. Расчёт суммы — ВНУТРИ UoW с финальными ценами (override применён)
        total_amount = 0
        order_items_data = []
        for item in dto.items:
            current_price = price_map[item.product_id]
            total_amount += current_price * item.quantity
            order_items_data.append({
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": current_price,  # snapshot цены
            })

        # --- НОВЫЙ БЛОК B: Проверка и резервирование кредита ---
        if contract is not None:
            # contract уже заблокирован FOR UPDATE — повторный SELECT
            # не нужен, передаём объект напрямую
            await self._check_and_reserve_credit(
                contract=contract,
                client_id=client_id,
                new_order_amount=total_amount,
            )
        # --- КОНЕЦ БЛОКА B ---

        # 4. Тара (строки 186-252, без изменений)
        capitalization_applied = False
        if exchange_items:
            ...

        # 5. Создание заказа (строка 255, + contract_id)
        new_order = await self.uow.orders.add({
            "client_id": client_id,
            "client_inventory_id": dto.client_inventory_id,
            "payment_method": dto.payment_method,
            "status": OrderStatus.NEW,
            "total_amount": total_amount,
            "capitalization_applied": capitalization_applied,
            "contract_id": contract.id if contract else None,  # НОВОЕ
        })

        for item_data in order_items_data:
            item_data["order_id"] = new_order.id

        await self.uow.order_items.add_many(order_items_data)
        await self.uow.commit()

        return await self.uow.orders.get_with_details(new_order.id)


async def _get_and_validate_contract_locked(
    self, client_id: uuid.UUID
) -> Contract:
    """Получить активный договор клиента с SELECT FOR UPDATE.

    Вызывается ВНУТРИ async with self.uow.
    Использует self.uow.contracts — не требует отдельного сервиса.

    Блокировка строки предотвращает два класса проблем:
    1. Race condition: параллельные заказы не могут одновременно
       пройти credit check и инкрементировать credit_used.
    2. TOCTOU: статус и end_date проверяются ПОСЛЕ блокировки,
       исключая окно между check и reserve.
    """
    contract = await self.uow.contracts.get_active_for_client(
        client_id, with_for_update=True
    )
    if not contract:
        raise ContractRequiredError(client_id=client_id)

    # Статус валидируем ПОСЛЕ FOR UPDATE — нет TOCTOU окна
    if contract.status != ContractStatus.ACTIVE:
        raise ContractNotActiveError(
            contract_id=contract.id,
            status=contract.status,
        )
    today = datetime.now(timezone.utc).date()  # timezone-aware
    if contract.end_date and contract.end_date < today:
        raise ContractExpiredError(contract_id=contract.id)
    return contract


async def _check_and_reserve_credit(
    self,
    contract: Contract,  # уже заблокированный FOR UPDATE объект
    client_id: uuid.UUID,
    new_order_amount: int,
) -> None:
    """Проверка и резервирование кредитного лимита.

    contract передаётся как уже заблокированный объект из
    _get_and_validate_contract_locked() — повторный SELECT не нужен.

    Алгоритм:
    1. Берём уже заблокированный contract (credit_used актуален)
    2. Получаем account.balance (накопленный settled долг)
    3. total_exposure = account.balance + contract.credit_used + new_amount
    4. Если total_exposure > credit_limit → raise CreditLimitExceededError
    5. credit_used += new_order_amount (атомарный UPDATE)

    Блокировка contracts предотвращает race condition при
    параллельных заказах одного клиента.
    """
    # contract уже содержит актуальные данные (заблокирован FOR UPDATE)
    client_account = await self.uow.accounts.get_client_account(
        client_id
    )

    if contract.credit_limit > 0:  # 0 = безлимитный
        current_exposure = (
            client_account.balance + contract.credit_used
        )
        if current_exposure + new_order_amount > contract.credit_limit:
            raise CreditLimitExceededError(
                contract_id=contract.id,
                credit_limit=contract.credit_limit,
                current_exposure=current_exposure,
                order_amount=new_order_amount,
            )

    # Резервируем кредит (in-flight)
    await self.uow.contracts.increment_credit_used(
        contract.id, new_order_amount
    )
```

### 8.3 Изменения в \_process_financial_settlement() и \_process_pickup_settlement()

> **⚠️ Два пути закрытия:** В codebase есть два отдельных метода:
>
> - `_process_financial_settlement()` — для DELIVERED-заказов (доставка на дом)
> - `_process_pickup_settlement()` — для PICKUP_COMPLETED (самовывоз, строки 1157+)
>
> `credit_used` должен освобождаться в **обоих** путях. Иначе credit
> утечёт при самовывозе B2B-клиента.

```python
# ─── Добавить в _process_financial_settlement() ─────────────────
async def _process_financial_settlement(self, order: Order) -> None:
    # ... существующий код ...

    if order.payment_method == PaymentMethod.CONTRACT:
        if order.contract_id:
            # Долг перешёл в account.balance через триггер.
            # Освобождаем in-flight резерв.
            await self.uow.contracts.decrement_credit_used(
                order.contract_id, order.total_amount
            )

    await self.uow.financial_transactions.add_many(financial_txns)


# ─── Добавить в _process_pickup_settlement() ────────────────────
async def _process_pickup_settlement(self, order: Order) -> None:
    # ... существующий код ...

    if order.payment_method == PaymentMethod.CONTRACT:
        if order.contract_id:
            # Самовывоз CONTRACT: тот же механизм освобождения кредита
            await self.uow.contracts.decrement_credit_used(
                order.contract_id, order.total_amount
            )
```

### 8.4 Ограничение create_warehouse_sale()

> **⚠️ Известное ограничение (MVP):** `create_warehouse_sale()` в
> `src/modules/orders/services.py` (строка ~405) жёстко задаёт
> `PaymentMethod.CASH`. B2B-клиент не может сделать складскую продажу
> по договору в текущей реализации.
>
> **Решение для фазы 2:** Параметризовать `payment_method` в
> `create_warehouse_sale()` и добавить ту же логику CONTRACT-хелперов.
> До тех пор складская продажа для B2B — только CASH.
>
> Хелперы `_get_and_validate_contract_locked()` и
> `_check_and_reserve_credit()` уже спроектированы переиспользуемо
> и применятся к warehouse_sale без изменений при параметризации.

---

## 9. Анализ Race Conditions

### 9.1 Проблема: параллельные заказы от одного клиента

```
Транзакция A (заказ 1, 50 000 тийин):     Транзакция B (заказ 2, 60 000 тийин):
  READ credit_limit=100000                   READ credit_limit=100000
  READ credit_used=0                         READ credit_used=0
  READ account.balance=20000                 READ account.balance=20000
  check: 20000+0+50000=70000 ≤ 100000 ✅    check: 20000+0+60000=80000 ≤ 100000 ✅
  INSERT order_1                             INSERT order_2
  UPDATE credit_used=50000                   UPDATE credit_used=60000
  COMMIT                                     COMMIT
  # credit_used = 60000 (B перезатёр A)!
  # Реальный exposure: 20000+50000+60000=130000 > 100000 — превышен!
```

### 9.2 Решение: SELECT FOR UPDATE на строку Contract

```python
# _check_and_reserve_credit() — строка выше:
contract = await self.uow.contracts.get(
    contract_id, with_for_update=True  # ← блокировка строки
)
```

С `FOR UPDATE` на строку `contracts`:

```
Транзакция A:                            Транзакция B (ждёт):
  SELECT ... FOR UPDATE (contract)          SELECT ... FOR UPDATE → WAIT
  check OK                                  ...
  UPDATE credit_used += 50000               ...
  COMMIT → lock released                    ПОЛУЧАЕТ LOCK
                                            credit_used = 50000 (свежее)
                                            check: 20000+50000+60000=130000 > 100000
                                            raise CreditLimitExceededError ✅
```

### 9.3 Почему НЕ блокируем Account

`account.balance` обновляется **триггером** только при DELIVERED (settlement). При `create_order` баланс не меняется. Поэтому блокировать `accounts` при создании заказа не нужно — `credit_used` на `contracts` покрывает in-flight exposure.

### 9.4 credit_used при отмене заказа

Если заказ отменяется (статус CANCELLED) **до** settlement — нужно вернуть credit_used.

> **Примечание:** В codebase нет отдельного метода `cancel_order()`.
> Отмена проходит через `update_status(order_id, new_status=CANCELLED)`.
> Логика освобождения кредита добавляется в `update_status()`.

```python
# src/modules/orders/services.py — метод update_status()
async def update_status(
    self,
    order_id: uuid.UUID,
    new_status: OrderStatus,
    actual_items: list[OrderItemActual] | None = None,
    requesting_user_id: uuid.UUID | None = None,
) -> Order:
    async with self.uow:
        order = await self.uow.orders.get_with_details(
            order_id, with_for_update=True
        )
        # ... существующий код перехода статуса ...

        # НОВОЕ: освободить кредит при отмене CONTRACT-заказа
        if (
            new_status == OrderStatus.CANCELLED
            and order.payment_method == PaymentMethod.CONTRACT
            and order.contract_id is not None
            and order.status not in (
                OrderStatus.DELIVERED,
                OrderStatus.PICKUP_COMPLETED,
            )
        ):
            await self.uow.contracts.decrement_credit_used(
                order.contract_id, order.total_amount
            )

        # ... существующий commit ...
```

---

## 10. RBAC — разрешения и роли

### 10.1 Новые Scopes

```python
# src/core/security/permissions.py — добавить в класс Scope:

    # --- ДОГОВОРЫ (Contracts) ---
    CONTRACTS_READ = "contracts:read"
    # Просмотр списка договоров, деталей, прайс-листов

    CONTRACTS_WRITE = "contracts:write"
    # Создание договора, редактирование условий, управление прайс-листом

    CONTRACTS_MANAGE = "contracts:manage"
    # Активация / приостановка / расторжение (смена статуса)
```

### 10.2 Обновление ROLE_SCOPES

```python
# src/core/security/permissions.py

ROLE_SCOPES: dict[Role, list[str]] = {
    # ...существующее...

    Role.ADMIN: BASE_SCOPES + [
        # ...существующие scopes...
        # ВАЖНО: ADMIN создаёт заказы через backoffice-роут (ORDERS_EDIT),
        # а не через client-роут (ORDERS_CREATE). Добавлять ORDERS_CREATE
        # для ADMIN не нужно — backoffice/orders.py уже охраняется ORDERS_EDIT.
        Scope.CONTRACTS_READ,
        Scope.CONTRACTS_WRITE,
        Scope.CONTRACTS_MANAGE,
    ],

    Role.ACCOUNTANT: BASE_SCOPES + [
        Scope.USERS_READ,
        Scope.FINANCES_READ,
        Scope.FINANCES_WRITE,
        Scope.BILLS_READ,
        Scope.CONTRACTS_READ,     # ← новое: чтение для аудита
    ],

    Role.CLIENT_B2B: BASE_SCOPES + [
        Scope.ORDERS_READ,
        Scope.ORDERS_CREATE,
        Scope.ORDERS_CANCEL,
        Scope.BILLS_READ,
        Scope.CONTRACTS_READ,     # ← новое: просмотр своего договора
        # ВАЖНО: фильтрация по client_id enforced at service layer
    ],
}
```

### 10.3 Полная RBAC матрица

| Действие                       | ADMIN | ACCOUNTANT | CLIENT_B2B | CLIENT_B2C |
| ------------------------------ | ----- | ---------- | ---------- | ---------- |
| Создать договор                | ✅    | ❌         | ❌         | ❌         |
| Просмотр списка всех договоров | ✅    | ✅         | ❌         | ❌         |
| Просмотр своего договора       | ✅    | ✅         | ✅         | ❌         |
| Редактировать условия          | ✅    | ❌         | ❌         | ❌         |
| Управлять прайс-листом         | ✅    | ❌         | ❌         | ❌         |
| Активировать договор           | ✅    | ❌         | ❌         | ❌         |
| Приостановить договор          | ✅    | ❌         | ❌         | ❌         |
| Расторгнуть договор            | ✅    | ❌         | ❌         | ❌         |
| Создать заказ CONTRACT         | ✅ ¹  | ❌         | ✅ ²       | ❌         |
| Выставить Invoice              | ✅    | ✅         | ❌         | ❌         |
| Просмотр Invoice               | ✅    | ✅         | ✅         | ❌         |
| Принять банк. перевод (оплату) | ✅    | ✅         | ❌         | ❌         |

> ¹ ADMIN — через **backoffice**-роут (`POST /backoffice/orders`), охраняемый
> `Scope.ORDERS_EDIT`. `ORDERS_CREATE` ADMIN'у **не нужен**.
>
> ² CLIENT_B2B — через **client**-роут (`POST /client/orders`), охраняемый
> `Scope.ORDERS_CREATE`. Сервисная проверка роли (§10.4) блокирует B2C.

### 10.4 ⚠️ RBAC не блокирует B2C CONTRACT — нужна сервисная проверка

> **Критический gap:** `client/orders.py` проверяет только `Scope.ORDERS_CREATE`.
> Роль `CLIENT_B2C` тоже имеет этот scope. Значит, RBAC **не предотвращает**
> оформление CONTRACT-заказа B2C-клиентом на уровне роутера.
>
> Решение — явная проверка роли в `create_order()`, **уже встроена в §8.2
> Блок A** (первый шаг внутри `if dto.payment_method == PaymentMethod.CONTRACT:`).
> Здесь приведена для ясности:

```python
# ВНУТРИ async with self.uow: (Блок A — см. §8.2 для полного контекста)
if dto.payment_method == PaymentMethod.CONTRACT:
    client_user = await self.uow.users.get(client_id)
    if not client_user or client_user.role != Role.CLIENT_B2B:
        raise BadRequestError(
            message=(
                "Оплата по договору доступна только "
                "юридическим лицам (B2B)"
            ),
            error_code="CONTRACT_PAYMENT_NOT_ALLOWED",
            details={
                "role": (
                    str(client_user.role) if client_user else "unknown"
                )
            },
        )
    # ... далее _get_and_validate_contract_locked() — см. §8.2
```

---

## 11. API Роуты

### 11.1 Backoffice API

```python
# src/api/v1/backoffice/contracts.py

router = APIRouter(prefix="/contracts", tags=["Contracts"])

@router.post("/", status_code=201,
    dependencies=[Security(get_current_user, scopes=[Scope.CONTRACTS_WRITE])])
async def create_contract(
    client_id: uuid.UUID,
    dto: ContractCreate,
    contract_service: ContractService = Depends(get_contract_service),
) -> ContractResponse:
    """Создать договор (DRAFT) для B2B клиента."""
    return await contract_service.create_contract(client_id, dto)


@router.get("/",
    dependencies=[Security(get_current_user, scopes=[Scope.CONTRACTS_READ])])
async def list_contracts(
    status: ContractStatus | None = None,
    client_id: uuid.UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    contract_service: ContractService = Depends(get_contract_service),
) -> PaginatedResponse[ContractResponse]:
    """Список договоров с фильтрацией."""
    ...


@router.get("/{contract_id}",
    dependencies=[Security(get_current_user, scopes=[Scope.CONTRACTS_READ])])
async def get_contract(contract_id: uuid.UUID, ...) -> ContractDetailResponse:
    """Детали договора с прайс-листом."""
    ...


@router.patch("/{contract_id}",
    dependencies=[Security(get_current_user, scopes=[Scope.CONTRACTS_WRITE])])
async def update_contract(
    contract_id: uuid.UUID, dto: ContractUpdate, ...
) -> ContractResponse:
    """Обновить условия (credit_limit, payment_due_days, реквизиты)."""
    ...


@router.post("/{contract_id}/activate",
    dependencies=[Security(get_current_user, scopes=[Scope.CONTRACTS_MANAGE])])
async def activate_contract(
    contract_id: uuid.UUID,
    current_user: User = Security(get_current_user, scopes=[...]),
    ...
) -> ContractResponse:
    ...


@router.post("/{contract_id}/suspend", ...)
@router.post("/{contract_id}/reinstate", ...)
@router.post("/{contract_id}/terminate", ...)


# Прайс-лист
@router.get("/{contract_id}/prices", ...)
@router.put("/{contract_id}/prices/{product_id}", ...)  # PUT = upsert
@router.delete("/{contract_id}/prices/{product_id}", ...)

# Заказы по договору
@router.get("/{contract_id}/orders", ...)

# Счета-фактуры (фаза 2)
@router.get("/{contract_id}/invoices", ...)
@router.post("/{contract_id}/invoices/generate", ...)
```

### 11.2 Client API (B2B самообслуживание)

```python
# src/api/v1/client/contracts.py

@router.get("/my-contract",
    dependencies=[Security(get_current_user, scopes=[Scope.CONTRACTS_READ])])
async def get_my_contract(
    current_user: User = Depends(get_current_user),
    ...
) -> ContractDetailResponse:
    """Просмотр своего активного договора.
    IDOR-защита: client_id берётся из JWT, не из параметра запроса.
    """
    contract = await contract_service.get_active_contract(
        current_user.id
    )
    if not contract:
        raise ContractNotFoundError("not_found")
    # Не нужно проверять client_id == current_user.id:
    # get_active_for_client() уже фильтрует по client_id
    return ContractDetailResponse.model_validate(contract)


@router.get("/my-contract/prices", ...)  # Мой прайс-лист
@router.get("/my-contract/invoices", ...)  # Мои счета (фаза 2)
```

---

## 12. Расширение BillingService.accept_payment()

### 12.1 Текущее ограничение (src/modules/finances/schemas.py:282)

```python
class AcceptPaymentRequest(BaseModel):
    payment_method: str = Field(pattern="^(cash|card)$")  # ← проблема
```

### 12.2 Исправление схемы

```python
# src/modules/finances/schemas.py
class AcceptPaymentRequest(BaseModel):
    client_id: uuid.UUID
    amount: int = Field(gt=0)
    payment_method: str = Field(
        pattern="^(cash|card|bank)$"  # ← добавить bank
    )
    reason: str = Field(min_length=3, max_length=255)
    order_id: uuid.UUID | None = None
```

### 12.3 Исправление сервиса

```python
# src/modules/finances/services.py — метод accept_payment()
# Текущая структура: if cash ... else: card (не elif!)
# Необходимо изменить на: if cash ... elif card ... elif bank

# Шаг 1: Изменить существующий else на elif:
elif payment_method == "card":   # ← было: else:
    target_account = (
        await self.uow.accounts.get_system_card_account()
    )
    txn_status = TransactionStatus.PENDING

# Шаг 2: Добавить новую ветку bank ПОСЛЕ elif card:
elif payment_method == "bank":
    target_account = (
        await self.uow.accounts.get_system_bank_account()
    )
    if not target_account:
        raise NotFoundError(
            message="Системный банковский счёт не найден",
            error_code="BANK_ACCOUNT_NOT_FOUND",
        )
    txn_status = TransactionStatus.COMPLETED
    # Транзакция: Client → Bank (COMPLETED)
    # Триггер автоматически уменьшит client.balance
    # и увеличит bank.balance
```

`get_system_bank_account()` уже реализован в `AccountRepository` (строки 111–114 в `finances/repositories.py`) — ничего нового не нужно.

---

## 13. ClientUnitOfWork — расширение

```python
# src/application/client/uow.py — добавить ContractRepository

from src.modules.contracts.repositories import ContractRepository

class IClientUnitOfWork(IUnitOfWork):
    # ...существующие...
    contracts: ContractRepository  # ← новое

class ClientUnitOfWork(BaseSQLAlchemyUoW, IClientUnitOfWork):
    async def __aenter__(self) -> "ClientUnitOfWork":
        await super().__aenter__()
        # ...существующие...
        self.contracts = ContractRepository(session=self.session)
        return self
```

Это позволяет `ClientService.onboard_client_with_balance()` опционально создавать черновик договора в одной транзакции с регистрацией B2B клиента.

---

## 14. Миграция Alembic

```python
# alembic/versions/XXXX_add_contracts.py

"""Add contracts module.

Revision ID: ...
Depends on: cefde77d7774 (initial tables)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

def upgrade() -> None:
    # 1. Новые ENUM типы
    op.execute("""
        CREATE TYPE contract_status_enum AS ENUM (
            'draft', 'active', 'suspended', 'terminated', 'expired'
        )
    """)
    op.execute("""
        CREATE TYPE invoice_status_enum AS ENUM (
            'draft', 'issued', 'partially_paid',
            'paid', 'overdue', 'cancelled'
        )
    """)

    # 2. Таблица contracts
    op.create_table(
        "contracts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("number", sa.String(50), nullable=False, unique=True),
        sa.Column(
            "client_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "active", "suspended", "terminated", "expired",
                name="contract_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column(
            "credit_limit", sa.BigInteger, nullable=False,
            server_default="0"
        ),
        sa.Column(
            "credit_used", sa.BigInteger, nullable=False,
            server_default="0"
        ),
        sa.Column(
            "payment_due_days", sa.Integer, nullable=False,
            server_default="30"
        ),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("inn", sa.String(14), nullable=False),
        sa.Column("legal_address", sa.Text, nullable=True),
        sa.Column(
            "bank_account_number", sa.String(25), nullable=True
        ),
        sa.Column("bank_name", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "signed_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "signed_by_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "suspended_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "suspension_reason", sa.String(512), nullable=True
        ),
        sa.Column(
            "terminated_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "termination_reason", sa.String(512), nullable=True
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False,
            server_default="true"
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), onupdate=sa.func.now()
        ),
        sa.CheckConstraint(
            "credit_limit >= 0",
            name="ck_contract_credit_limit_non_neg"
        ),
        sa.CheckConstraint(
            "credit_used >= 0",
            name="ck_contract_credit_used_non_neg"
        ),
        sa.CheckConstraint(
            "payment_due_days > 0",
            name="ck_contract_payment_due_days_pos"
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date > start_date",
            name="ck_contract_dates_order"
        ),
    )
    # Индексы
    op.create_index(
        "idx_contract_client_id", "contracts", ["client_id"]
    )
    op.create_index(
        "idx_contract_status", "contracts", ["status"]
    )
    # Partial unique: один активный договор на клиента
    op.execute("""
        CREATE UNIQUE INDEX uq_one_active_contract_per_client
        ON contracts (client_id)
        WHERE status = 'active' AND is_active = true
    """)

    # 3. Таблица contract_price_items
    op.create_table(
        "contract_price_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id", UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id", UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("price", sa.BigInteger, nullable=False),
        sa.Column(
            "is_active", sa.Boolean, nullable=False,
            server_default="true"
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "contract_id", "product_id",
            name="uq_contract_price_item_product"
        ),
        sa.CheckConstraint(
            "price >= 0", name="ck_contract_price_item_price_non_neg"
        ),
    )
    op.create_index(
        "idx_contract_price_items_contract_id",
        "contract_price_items",
        ["contract_id"],
    )

    # 4. Добавить contract_id в orders
    op.add_column(
        "orders",
        sa.Column(
            "contract_id",
            UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.execute("""
        CREATE INDEX idx_orders_contract_id
        ON orders (contract_id)
        WHERE contract_id IS NOT NULL
    """)

    # 5. Таблица invoices (для фазы 2, можно выделить в отдельную миграцию)
    op.create_table(
        "invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id", UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("number", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "issued", "partially_paid",
                "paid", "overdue", "cancelled",
                name="invoice_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("period_from", sa.Date, nullable=False),
        sa.Column("period_to", sa.Date, nullable=False),
        sa.Column(
            "amount", sa.BigInteger, nullable=False,
            server_default="0"
        ),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column(
            "issued_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "paid_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False,
            server_default="true"
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "contract_id", "number",
            name="uq_invoice_contract_number"
        ),
        sa.CheckConstraint(
            "period_to > period_from",
            name="ck_invoice_period_order"
        ),
        sa.CheckConstraint(
            "amount >= 0", name="ck_invoice_amount_non_neg"
        ),
    )


def downgrade() -> None:
    op.drop_table("invoices")
    op.drop_column("orders", "contract_id")
    op.drop_table("contract_price_items")
    op.drop_table("contracts")
    op.execute("DROP TYPE IF EXISTS invoice_status_enum")
    op.execute("DROP TYPE IF EXISTS contract_status_enum")
```

---

## 15. Обновление conftest.py

```python
# tests/conftest.py — добавить contracts в список monkeypatch путей

_SESSION_FACTORY_MODULES = [
    "src.infrastructure.database.session",
    "src.modules.users.dependencies",
    "src.modules.catalog.dependencies",
    "src.modules.orders.dependencies",
    "src.modules.inventory.dependencies",
    "src.modules.finances.dependencies",
    "src.application.client.dependencies",
    "src.application.courier.dependencies",
    "src.application.inventories.dependencies",
    "src.modules.contracts.dependencies",  # ← ДОБАВИТЬ
]
```

---

## 16. Invoice Lifecycle (Счёт-фактура)

### 16.1 State Machine

```
      generate()          issue()          mark_paid()
DRAFT ──────────▶ ISSUED ──────────▶ PAID
                    │
                    │ (due_date < today)
                    ▼
                 OVERDUE ──────────▶ PAID (при оплате)
                    │
                    │ cancel()
                    ▼
                CANCELLED
```

### 16.2 Когда и как генерируется Invoice

**Вариант A (MVP — ручной):** Бухгалтер нажимает "Выставить счёт" в backoffice → `POST /contracts/{id}/invoices/generate` с указанием периода.

**Вариант B (автоматический — фаза 3):** Celery beat каждый день проверяет договоры с `billing_cycle` и генерирует invoices.

**Алгоритм генерации:**

```python
async def generate_invoice(
    self,
    contract_id: uuid.UUID,
    period_from: date,
    period_to: date,
) -> Invoice:
    """Агрегирует заказы по договору за период
    и создаёт счёт-фактуру.
    """
    # 1. Получить все DELIVERED/PICKUP_COMPLETED заказы за период
    orders = await self.uow.orders.get_delivered_by_contract(
        contract_id=contract_id,
        date_from=period_from,
        date_to=period_to,
    )
    total = sum(o.total_amount for o in orders)

    # 2. Получить contract для расчёта due_date
    contract = await self.uow.contracts.get(contract_id)
    due_date = period_to + timedelta(days=contract.payment_due_days)

    # 3. Создать Invoice
    invoice = await self.uow.invoices.add({
        "contract_id": contract_id,
        "number": self._generate_invoice_number(contract),
        "status": InvoiceStatus.DRAFT,
        "period_from": period_from,
        "period_to": period_to,
        "amount": total,
        "due_date": due_date,
    })
    await self.uow.commit()
    return invoice
```

### 16.3 Привязка платежа к Invoice

Когда бухгалтер принимает банковский платёж (`accept_payment(method="bank")`):

- Создаётся транзакция `Client → Bank (COMPLETED)`
- Триггер уменьшает `account.balance`
- Invoice обновляется в PAID (вручную бухгалтером или автоматически при полном погашении)

---

## 17. Акт сверки (Reconciliation)

Акт сверки по договору — это отчёт: «Все наши заказы → Все ваши платежи → Разница».

```
GET /api/v1/backoffice/contracts/{id}/reconciliation?
    date_from=2025-01-01&date_to=2025-01-31
```

**Данные для акта:**

```python
class ReconciliationResponse(BaseModel):
    contract_id: uuid.UUID
    contract_number: str
    client_name: str
    period_from: date
    period_to: date

    # Дебет (наши поставки)
    orders: list[ReconciliationOrderItem]
    total_billed: int

    # Кредит (оплаты клиента)
    payments: list[ReconciliationPaymentItem]
    total_paid: int

    # Итого
    balance: int  # = total_billed - total_paid
```

**Запрос (оптимизированный):**

```sql
-- Поставки по договору
SELECT
    o.id, o.created_at,
    o.total_amount,
    SUM(oi.unit_price * oi.quantity) AS line_total
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE
    o.contract_id = :contract_id
    AND o.status IN ('delivered', 'pickup_completed')
    AND o.created_at BETWEEN :date_from AND :date_to
GROUP BY o.id;

-- Платежи (Client → Bank транзакции)
-- SYSTEM_USER_ID — константа из src/core/constants.py
SELECT t.id, t.created_at, t.amount, t.reason
FROM transactions t
JOIN accounts a ON t.from_id = a.id
WHERE
    a.user_id = :client_id
    AND t.status = 'completed'
    AND t.created_at BETWEEN :date_from AND :date_to
    AND EXISTS (
        SELECT 1 FROM accounts b
        WHERE b.id = t.to_id
          AND b.user_id = :system_user_id  -- SYSTEM_USER_ID из constants.py
          AND b.type = 'bank'
    );
-- В Python: query.bindparams(system_user_id=SYSTEM_USER_ID)
```

---

## 18. Dashboard (Финансовый дашборд)

### 18.1 Новый виджет: Дебиторская задолженность по договорам

```python
# src/modules/finances/services.py — добавить метод:

async def get_b2b_contract_debts(self) -> B2BContractDebtsResponse:
    """Дебиторка по B2B договорам с детализацией.

    JOIN: accounts (CLIENT) → users → contracts
    Показывает: клиент, номер договора, лимит, использовано.
    """
```

```python
class B2BContractDebt(BaseModel):
    client_id: uuid.UUID
    client_name: str
    contract_id: uuid.UUID
    contract_number: str
    credit_limit: int
    credit_used: int        # in-flight
    account_balance: int    # settled debt
    total_exposure: int     # = credit_used + account_balance
    limit_utilization_pct: float  # = total_exposure / credit_limit * 100
    due_date_status: str    # "ok", "overdue", "no_contract"
```

### 18.2 Обновление DashboardTotals

```python
class DashboardTotals(BaseModel):
    total_revenue: int
    total_cash_in_hand: int
    total_card_pending: int
    total_client_debt: int
    total_courier_cash: int
    total_b2b_credit_used: int     # ← новое: in-flight B2B
    total_b2b_settled_debt: int    # ← новое: погашено B2B
```

---

## 19. Полная тест-стратегия

### 19.1 Структура тестов

```
tests/
├── unit/
│   ├── test_contracts.py          # ContractService business logic
│   └── test_orders_contract.py    # create_order + contract integration
└── integration/
    └── test_contracts_api.py      # End-to-end API тесты
```

### 19.2 Тест-кейсы: ContractService

```python
# tests/unit/test_contracts.py

class TestContractLifecycle:

    async def test_create_contract_draft(self, db_session, client):
        """CREATE → статус DRAFT, credit_used=0."""

    async def test_activate_contract(self, db_session, client):
        """DRAFT → ACTIVE, signed_at заполнен."""

    async def test_cannot_activate_non_draft(self, db_session, client):
        """Попытка активировать ACTIVE → ConflictError."""

    async def test_one_active_per_client_unique_index(
        self, db_session, client
    ):
        """Создать два ACTIVE договора → ConflictError (partial unique index)."""

    async def test_suspend_contract(self, db_session, client):
        """ACTIVE → SUSPENDED, причина обязательна."""

    async def test_reinstate_suspended_contract(self, db_session, client):
        """SUSPENDED → ACTIVE."""

    async def test_terminate_contract(self, db_session, client):
        """ACTIVE/SUSPENDED → TERMINATED."""

    async def test_expired_contract_blocks_orders(
        self, db_session, client
    ):
        """Договор с end_date < today → ContractExpiredError при create_order."""


class TestContractPricing:

    async def test_set_price_item(self, db_session, client):
        """Установить цену → price_map override."""

    async def test_price_fallback_to_catalog(self, db_session, client):
        """Товар без contract_price → каталожная цена."""

    async def test_price_override_in_create_order(
        self, db_session, client
    ):
        """create_order с CONTRACT → unit_price = contract_price."""

    async def test_price_snapshot_immutable(self, db_session, client):
        """Изменить contract_price после заказа → старый order не меняется."""

    async def test_remove_price_item_fallback(self, db_session, client):
        """Убрать позицию из прайса → следующий заказ по каталогу."""


class TestCreditLimit:

    async def test_create_order_within_limit(self, db_session, client):
        """Заказ в рамках лимита → success."""

    async def test_credit_limit_exceeded(self, db_session, client):
        """Заказ превышает лимит → CreditLimitExceededError с деталями."""

    async def test_credit_limit_zero_is_unlimited(
        self, db_session, client
    ):
        """credit_limit=0 → заказы без ограничений."""

    async def test_credit_used_increments_on_order(
        self, db_session, client
    ):
        """После create_order → contract.credit_used += order.total_amount."""

    async def test_credit_used_decrements_on_delivery(
        self, db_session, client
    ):
        """После complete_delivery → credit_used уменьшается, balance растёт."""

    async def test_credit_used_decrements_on_cancel(
        self, db_session, client
    ):
        """После cancel_order → credit_used возвращается."""

    async def test_concurrent_orders_race_condition(
        self, db_session
    ):
        """Два параллельных заказа: один проходит, другой получает
        CreditLimitExceededError. Тест через asyncio.gather."""


class TestContractRequired:

    async def test_contract_payment_without_contract(
        self, db_session, client
    ):
        """CONTRACT оплата без договора → ContractRequiredError."""

    async def test_contract_payment_suspended_contract(
        self, db_session, client
    ):
        """CONTRACT оплата с SUSPENDED договором → ContractNotActiveError."""

    async def test_non_contract_order_without_contract(
        self, db_session, client
    ):
        """CASH заказ без договора → success (contract не нужен)."""
```

### 19.3 Тест-кейсы: accept_payment bank

```python
class TestBankPayment:

    async def test_accept_bank_payment(self, db_session, client):
        """method=bank → транзакция Client→Bank COMPLETED."""

    async def test_bank_payment_reduces_debt(self, db_session, client):
        """После bank платежа account.balance уменьшается (триггер)."""

    async def test_invalid_payment_method(self, db_session, client):
        """method=crypto → 422 ValidationError."""
```

### 19.4 Тест-кейсы: RBAC

```python
class TestContractRBAC:

    async def test_admin_can_create_contract(self, db_session, client):
        """ADMIN → POST /contracts → 201."""

    async def test_client_b2c_cannot_create_contract(
        self, db_session, client
    ):
        """CLIENT_B2C → POST /contracts → 403."""

    async def test_client_b2b_can_view_own_contract(
        self, db_session, client
    ):
        """CLIENT_B2B → GET /my-contract → 200."""

    async def test_client_b2b_cannot_view_other_contract(
        self, db_session, client
    ):
        """CLIENT_B2B → GET /contracts/{other_id} → 403."""

    async def test_accountant_cannot_activate_contract(
        self, db_session, client
    ):
        """ACCOUNTANT → POST /activate → 403."""
```

---

## 20. Паттерн Contract Amendment (Дополнительное соглашение)

Для MVP: условия договора изменяются через `PATCH /contracts/{id}` (изменяется `credit_limit`, `payment_due_days`, прайс-лист). Исторические заказы защищены Snapshot Pattern (`order_items.unit_price`).

Для Enterprise (фаза 3): добавить `ContractAmendment`:

```python
class ContractAmendment(BaseModel):
    # __tablename__ = "contract_amendments"
    contract_id: uuid.UUID
    amendment_number: int  # 1, 2, 3...
    effective_date: date   # с какой даты новые условия
    changes: dict          # JSONB: что изменилось
    status: str            # draft/approved/active
    approved_by_id: uuid.UUID | None
```

**Зачем:** Если договор изменяется в середине биллингового периода, нужно знать, какие цены действовали в каждый момент. `ContractAmendment` + `effective_date` позволяет восстановить историческое состояние договора.

**Альтернатива (проще):** Не изменять существующий договор. Расторгнуть и создать новый. Snapshot pricing в `order_items` уже защищает прошлые заказы.

**Рекомендация для HOD MVP:** Использовать `terminate → create new`. Прозрачно, аудитабельно, без сложной логики.

---

## 21. Audit Trail (Аудит договора)

Все изменения статуса договора должны быть трассируемы. Варианты:

**Вариант A (встроенный — MVP):** Поля в `Contract`:

- `signed_at`, `signed_by_id`
- `suspended_at`, `suspension_reason`
- `terminated_at`, `termination_reason`

Плюс `updated_at` (auto-update). Достаточно для базового аудита.

**Вариант B (полный — Enterprise):** Отдельная таблица `contract_status_log`:

```python
class ContractStatusLog(BaseModel):
    # __tablename__ = "contract_status_logs"
    contract_id: uuid.UUID
    from_status: ContractStatus
    to_status: ContractStatus
    changed_by_id: uuid.UUID
    reason: str | None
    changed_at: datetime  # = created_at из BaseModel
```

Создаётся в каждом transition-методе (`activate`, `suspend`, `terminate`). Позволяет восстановить полную историю договора.

---

## 22. Производительность и индексы

### 22.1 Индексная стратегия

```sql
-- Критичные для runtime запросы:

-- 1. Поиск активного договора клиента (в каждом create_order)
CREATE UNIQUE INDEX uq_one_active_contract_per_client
ON contracts (client_id)
WHERE status = 'active' AND is_active = true;
-- Покрывает: GET active_contract + UNIQUE constraint

-- 2. Договорные цены по списку товаров (bulk lookup в price_map)
-- Индекс (contract_id) уже есть (idx_contract_price_items_contract_id)
-- Запрос: WHERE contract_id = X AND product_id IN (...)
-- SQLAlchemy использует IN → PostgreSQL index scan

-- 3. Заказы по договору (для Invoice generation, reconciliation)
CREATE INDEX idx_orders_contract_id
ON orders (contract_id)
WHERE contract_id IS NOT NULL;
-- Partial index: не индексирует NULL (B2C заказы)

-- 4. Заказы по договору + дата + статус (отчёты)
CREATE INDEX idx_orders_contract_status_date
ON orders (contract_id, status, created_at)
WHERE contract_id IS NOT NULL;
```

### 22.2 N+1 Prevention

- `ContractRepository.get_with_price_items()` использует `selectinload(Contract.price_items)` — 2 запроса вместо N+1
- `ContractRepository.get_multi_with_client()` использует `joinedload(Contract.client)` — 1 запрос с JOIN
- `lazy="raise"` на все relationships в `Contract` — принудительная явная загрузка
- `get_price_map_for_products()` — один bulk `SELECT IN` вместо N отдельных запросов

### 22.3 Кэширование (опционально, фаза 3)

`ContractPriceItem` редко меняется (только при ручном обновлении прайса). Можно кэшировать `get_price_map_for_products()` в Redis с инвалидацией при `set_price_item()` / `remove_price_item()`. Для MVP кэш не нужен.

---

## 23. Публичный API модуля

```python
# src/modules/contracts/public.py

"""Contracts module public API.

Other modules MUST import only from this file.
Do not import from contracts.models, contracts.repositories,
contracts.uow, or contracts.exceptions directly.
"""

from src.modules.contracts.dtos import ContractDTO
from src.modules.contracts.enums import ContractStatus, InvoiceStatus
from src.modules.contracts.exceptions import (
    ContractNotActiveError,
    ContractNotFoundError,
    ContractRequiredError,
    CreditLimitExceededError,
)
from src.modules.contracts.services import ContractService

__all__ = [
    "ContractService",
    "ContractDTO",
    "ContractStatus",
    "InvoiceStatus",
    "ContractNotFoundError",
    "ContractNotActiveError",
    "ContractRequiredError",
    "CreditLimitExceededError",
]
```

```python
# src/modules/contracts/dtos.py

from dataclasses import dataclass
from datetime import date, datetime
import uuid
from src.modules.contracts.enums import ContractStatus


@dataclass(frozen=True, slots=True)
class ContractDTO:
    id: uuid.UUID
    client_id: uuid.UUID
    number: str
    status: ContractStatus
    credit_limit: int
    credit_used: int
    payment_due_days: int
    start_date: date
    end_date: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

---

## 24. Обзор всех файлов к изменению / созданию

### Новые файлы (создать)

```
src/modules/contracts/
├── __init__.py
├── enums.py
├── models.py
├── dtos.py
├── schemas.py
├── repositories.py
├── services.py
├── uow.py
├── dependencies.py
├── exceptions.py
└── public.py

src/api/v1/backoffice/contracts.py
src/api/v1/client/contracts.py

alembic/versions/XXXX_add_contracts.py

tests/unit/test_contracts.py
tests/unit/test_orders_contract.py
tests/integration/test_contracts_api.py
```

### Существующие файлы к изменению

| Файл                                    | Что изменить                                                                                                                                                                                                             |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---- | -------- |
| `src/modules/orders/models.py`          | Добавить `contract_id` FK и relationship                                                                                                                                                                                 |
| `src/modules/orders/uow.py`             | Добавить `contracts: ContractRepository`                                                                                                                                                                                 |
| `src/modules/orders/services.py`        | `create_order()`: contract validation + price override + credit check. `_process_financial_settlement()` + `_process_pickup_settlement()`: decrement credit_used. `update_status()`: decrement credit_used при CANCELLED |
| `src/modules/orders/repositories.py`    | `search_orders()`: добавить фильтр по `contract_id`. `get_delivered_by_contract()`: для Invoice генерации                                                                                                                |
| `src/modules/finances/schemas.py`       | `AcceptPaymentRequest.payment_method`: `"^(cash                                                                                                                                                                          | card | bank)$"` |
| `src/modules/finances/services.py`      | `accept_payment()`: добавить `bank` ветку. `get_client_debts()`: overlay contract info                                                                                                                                   |
| `src/core/security/permissions.py`      | Добавить `CONTRACTS_READ/WRITE/MANAGE` в `Scope` и `ROLE_SCOPES`                                                                                                                                                         |
| `src/application/client/uow.py`         | Добавить `contracts: ContractRepository`                                                                                                                                                                                 |
| `src/infrastructure/database/models.py` | Импортировать и регистрировать новые модели (`Contract`, `ContractPriceItem`, `Invoice`)                                                                                                                                 |
| `tests/conftest.py`                     | Добавить `src.modules.contracts.dependencies` в `_SESSION_FACTORY_MODULES`                                                                                                                                               |

---

## 25. Бизнес-кейсы (покрытие)

| Кейс                                                 | Покрытие                                                                                                    |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| B2B создаёт заказ CONTRACT с договорными ценами      | §8 + §4                                                                                                     |
| B2B заказ превышает кредитный лимит                  | §9 + §7                                                                                                     |
| Два параллельных заказа (race condition)             | §9.1-9.2                                                                                                    |
| B2B заказ с тарой (1:1 exchange + CONTRACT)          | без изменений — тара-логика независима                                                                      |
| B2B self-service самовывоз со склада                 | §8.4                                                                                                        |
| Приостановка договора → блокировка новых заказов     | §3 + §7                                                                                                     |
| Расторжение договора при наличии заказов             | `RESTRICT` FK на `orders.contract_id` — не даст удалить                                                     |
| Бухгалтер принимает банковский платёж                | §12                                                                                                         |
| Генерация счёта-фактуры за период                    | §16                                                                                                         |
| Акт сверки за период                                 | §17                                                                                                         |
| Просмотр дебиторки по договорам в дашборде           | §18                                                                                                         |
| B2B видит только свой договор (IDOR)                 | §11.2 + `ContractAccessDeniedError`                                                                         |
| B2C пытается создать CONTRACT заказ                  | Сервисный слой → `BadRequestError` (RBAC-scope недостаточен — нужна явная проверка роли в `create_order()`) |
| Изменение договорных цен не влияет на прошлые заказы | Snapshot Pattern в `order_items.unit_price`                                                                 |
| Аудит изменений статуса договора                     | §21                                                                                                         |
| Дополнительное соглашение                            | §20                                                                                                         |

---

## 26. Ключевые архитектурные решения

| Решение                      | Выбранный подход                                      | Альтернатива                      | Почему                                             |
| ---------------------------- | ----------------------------------------------------- | --------------------------------- | -------------------------------------------------- |
| `credit_used` для in-flight  | Поле на Contract, управляется приложением             | Materialised view                 | Проще, атомарно в транзакции с заказом             |
| Блокировка от race condition | SELECT FOR UPDATE на `contracts`                      | Advisory lock                     | Уже есть `with_for_update` в BaseRepository        |
| Договорные цены              | Отдельная таблица `contract_price_items`              | JSONB на Contract                 | Нормализация, FK на products, индексируемость      |
| Фолбэк на каталог            | `price_map.update(contract_price_map)` в OrderService | CatalogService знает о контрактах | Catalog остаётся чистым (Single Responsibility)    |
| Один активный договор        | Partial UNIQUE INDEX (не CHECK constraint)            | Проверка в сервисе                | DB-уровень → защита от race condition при activate |
| Invoice поколение            | Ручной MVP, cron фаза 3                               | Всегда автомат                    | Прагматично для MVP                                |
| Audit trail                  | Поля на Contract (MVP)                                | Отдельная таблица                 | Расширяемо, не блокирует MVP                       |
| B2B pricing в каталоге       | override в OrderService                               | Отдельный endpoint                | Catalog чистый, override в правильном домене       |
| Отмена + credit_used         | decrement при CANCELLED                               | Не делать ничего                  | Финансовая корректность                            |
| Amendment (Доп. соглашение)  | terminate+create (MVP)                                | ContractAmendment model           | Простота, аудитабельность                          |

---

## 27. Фазы реализации

### Фаза 1 — MVP Договора

**Цель:** Привязка заказов к договору, кредитный лимит, индивидуальный прайс.

1. Создать `src/modules/contracts/` (enums, models, repos, services, uow, deps, exceptions, public)
2. Миграция: contracts, contract_price_items, invoices + `orders.contract_id`
3. Расширить `BaseOrderUnitOfWork` + `ClientUnitOfWork` с `ContractRepository`
4. Интегрировать в `create_order()`: валидация, override цен, кредитный лимит
5. Добавить `decrement_credit_used` в `_process_financial_settlement()`, `_process_pickup_settlement()` и `update_status(CANCELLED)`
6. Добавить Scopes + ROLE_SCOPES
7. Backoffice API: CRUD договоров + прайс-листов + lifecycle endpoints
8. Client API: `GET /my-contract` + `GET /my-contract/prices`
9. Расширить `accept_payment()` для `bank`
10. Обновить `conftest.py`
11. Написать тесты (§19)

### Фаза 2 — Биллинг

1. Invoice lifecycle: `generate_invoice()`, `issue_invoice()`, `mark_paid()`
2. Backoffice API: Invoice CRUD
3. Client API: просмотр счетов
4. Акт сверки: `GET /contracts/{id}/reconciliation`
5. Dashboard виджет: B2B дебиторка

### Фаза 3 — Автоматизация

1. Celery beat: авто-генерация Invoice по `billing_cycle`
2. Авто-OVERDUE при `due_date < today`
3. Авто-EXPIRED при `end_date < today`
4. Уведомления клиенту (Telegram / email)
5. `ContractAmendment` для формальных дополнительных соглашений
6. `ContractStatusLog` для полного аудита
7. Redis кэш для `price_map`

---

## 28. Schemas (src/modules/contracts/schemas.py)

```python
# src/modules/contracts/schemas.py

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from src.modules.contracts.enums import ContractStatus, InvoiceStatus


# ─── CONTRACT SCHEMAS ────────────────────────────────────────────

class ContractCreate(BaseModel):
    number: str = Field(
        min_length=1,
        max_length=50,
        description="Номер договора (HOD-2025-001)",
    )
    start_date: date
    end_date: date | None = None
    credit_limit: int = Field(
        default=0,
        ge=0,
        description="0 = без ограничений",
    )
    payment_due_days: int = Field(
        default=30, gt=0, le=365
    )
    legal_name: str = Field(min_length=1, max_length=255)
    inn: str = Field(min_length=9, max_length=14)
    legal_address: str | None = Field(default=None, max_length=500)
    bank_account_number: str | None = Field(
        default=None, max_length=25
    )
    bank_name: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2000)


class ContractUpdate(BaseModel):
    """Частичное обновление условий договора (только DRAFT/ACTIVE)."""
    credit_limit: int | None = Field(default=None, ge=0)
    payment_due_days: int | None = Field(
        default=None, gt=0, le=365
    )
    end_date: date | None = None
    legal_address: str | None = Field(default=None, max_length=500)
    bank_account_number: str | None = Field(
        default=None, max_length=25
    )
    bank_name: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2000)


class ContractSuspendRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=512)


class ContractTerminateRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=512)


class ContractResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    number: str
    status: ContractStatus
    start_date: date
    end_date: date | None
    credit_limit: int
    credit_used: int
    payment_due_days: int
    legal_name: str
    inn: str
    legal_address: str | None
    bank_account_number: str | None
    bank_name: str | None
    notes: str | None
    signed_at: datetime | None
    signed_by_id: uuid.UUID | None
    suspended_at: datetime | None
    suspension_reason: str | None
    terminated_at: datetime | None
    termination_reason: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContractDetailResponse(ContractResponse):
    """Расширенный ответ с прайс-листом."""
    price_items: list["PriceItemResponse"] = []


# ─── PRICE ITEM SCHEMAS ───────────────────────────────────────────

class PriceItemCreate(BaseModel):
    product_id: uuid.UUID
    price: int = Field(ge=0, description="Договорная цена в тийинах")


class PriceItemResponse(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    product_id: uuid.UUID
    price: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── INVOICE SCHEMAS ─────────────────────────────────────────────

class InvoiceGenerateRequest(BaseModel):
    period_from: date
    period_to: date


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    number: str
    status: InvoiceStatus
    period_from: date
    period_to: date
    amount: int
    due_date: date | None
    issued_at: datetime | None
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

---

## 29. Dependencies (src/modules/contracts/dependencies.py)

```python
# src/modules/contracts/dependencies.py

from fastapi import Depends

from src.infrastructure.database.session import async_session_maker
from src.modules.contracts.services import ContractService
from src.modules.contracts.uow import ContractUnitOfWork


def get_contract_uow() -> ContractUnitOfWork:
    return ContractUnitOfWork(session_factory=async_session_maker)


def get_contract_service(
    uow: ContractUnitOfWork = Depends(get_contract_uow),
) -> ContractService:
    return ContractService(uow=uow)
```

---

## 30. Model Registry (src/infrastructure/database/models.py)

```python
# src/infrastructure/database/models.py — добавить импорты

# Существующие импорты (подтверждены чтением реального файла):
from src.modules.catalog.models import Product
from src.modules.finances.models import Account, Transaction
from src.modules.inventory.models import (
    Balance,             # ← НЕ InventoryBalance — реальное имя класса
    Inventory,
    StockTransaction,
    StockTransfer,
    StockTransferItem,
)
from src.modules.orders.models import Order, OrderItem
from src.modules.users.models import Identity, User  # ← оба из users

# НОВЫЕ ИМПОРТЫ — добавить:
from src.modules.contracts.models import (  # noqa: F401
    Contract,
    ContractPriceItem,
    Invoice,
)
```

> **Зачем это обязательно:** `alembic/env.py` обнаруживает таблицы
> через `BaseModel.metadata`, которая заполняется при импорте классов.
> Если `Contract`, `ContractPriceItem` и `Invoice` не импортированы
> в момент загрузки приложения, `alembic autogenerate` не увидит их
> и не создаст таблицы. Это же касается Alembic downgrade и ANY schema
> inspection at startup.

---

_Версия: 2.3 (Final Corrected Edition)_  
_Статус: Исправлено 3 бага v2.3 (§8.1 удалён несуществующий IBaseOrderUnitOfWork + исправлено имя поля transactions, §8.2 Блок A дополнен проверкой роли B2B, §10.3 уточнена матрица ADMIN-route). Готово к реализации Фазы 1._
