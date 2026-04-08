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
    payment_due_days: int = Field(default=30, gt=0, le=365)
    legal_name: str = Field(min_length=1, max_length=255)
    inn: str = Field(min_length=9, max_length=14)
    legal_address: str | None = Field(default=None, max_length=500)
    bank_account_number: str | None = Field(default=None, max_length=25)
    bank_name: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2000)


class ContractUpdate(BaseModel):
    """Частичное обновление условий договора (только DRAFT/ACTIVE)."""

    credit_limit: int | None = Field(default=None, ge=0)
    payment_due_days: int | None = Field(default=None, gt=0, le=365)
    end_date: date | None = None
    legal_address: str | None = Field(default=None, max_length=500)
    bank_account_number: str | None = Field(default=None, max_length=25)
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

    price_items: list[PriceItemResponse] = []


# ─── PRICE ITEM SCHEMAS ───────────────────────────────────────────


class PriceItemCreate(BaseModel):
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


# ─── RECONCILIATION SCHEMAS ──────────────────────────────────────


class ReconciliationOrderItem(BaseModel):
    order_id: uuid.UUID
    created_at: datetime
    total_amount: int


class ReconciliationPaymentItem(BaseModel):
    transaction_id: uuid.UUID
    created_at: datetime
    amount: int
    reason: str | None = None


class ReconciliationResponse(BaseModel):
    contract_id: uuid.UUID
    contract_number: str
    client_name: str
    period_from: date
    period_to: date
    orders: list[ReconciliationOrderItem]
    total_billed: int
    payments: list[ReconciliationPaymentItem]
    total_paid: int
    balance: int  # = total_billed - total_paid


# ─── STATUS LOG SCHEMAS ───────────────────────────────────────────


class ContractStatusLogResponse(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    from_status: ContractStatus | None
    to_status: ContractStatus
    changed_by_id: uuid.UUID | None
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── AMENDMENT SCHEMAS ────────────────────────────────────────────


class AmendmentCreate(BaseModel):
    number: str = Field(
        min_length=1,
        max_length=50,
        description="Номер ДС (ДС-001, ДС-002...)",
    )
    description: str = Field(
        min_length=3,
        max_length=2000,
        description="Описание изменений",
    )
    effective_date: date


class AmendmentResponse(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    number: str
    description: str
    effective_date: date
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── JOB RESPONSE ────────────────────────────────────────────────


class JobResponse(BaseModel):
    updated: int
