# src/modules/contracts/dtos.py
import uuid
from dataclasses import dataclass
from datetime import date, datetime

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
