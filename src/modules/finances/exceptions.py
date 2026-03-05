# src/modules/finances/exceptions.py
import uuid
from typing import Any

from src.core.exceptions import BadRequestError, ConflictError, NotFoundError


class AccountNotFoundError(NotFoundError):
    """Выбрасывается, когда финансовый счет не найден в БД."""

    def __init__(
        self, account_id: uuid.UUID | None = None, message: str | None = None
    ):
        msg = message or (
            f"Финансовый счет {account_id} не найден."
            if account_id
            else "Финансовый счет не найден."
        )
        super().__init__(
            message=msg,
            error_code="ACCOUNT_NOT_FOUND",
            details={"account_id": str(account_id)} if account_id else None,
        )


class TransactionNotFoundError(NotFoundError):
    """Выбрасывается, когда транзакция не найдена по ID."""

    def __init__(self, transaction_id: uuid.UUID | None = None):
        msg = (
            f"Транзакция {transaction_id} не найдена."
            if transaction_id
            else "Транзакция не найдена."
        )
        super().__init__(
            message=msg,
            error_code="TRANSACTION_NOT_FOUND",
            details={"transaction_id": str(transaction_id)}
            if transaction_id
            else None,
        )


class InsufficientFundsError(ConflictError):
    """Выбрасывается при попытке списания суммы, превышающей баланс (если мы запрещаем минусовой баланс)."""

    def __init__(
        self, account_id: uuid.UUID, required_amount: int, actual_balance: int
    ):
        super().__init__(
            message="Недостаточно средств на счете для проведения операции.",
            error_code="INSUFFICIENT_FUNDS",
            details={
                "account_id": str(account_id),
                "required_amount": required_amount,
                "actual_balance": actual_balance,
            },
        )


class InvalidTransactionAmountError(BadRequestError):
    """Выбрасывается, если сумма транзакции <= 0."""

    def __init__(self, amount: int):
        super().__init__(
            message=f"Недопустимая сумма транзакции: {amount}. Сумма должна быть больше нуля.",
            error_code="INVALID_TRANSACTION_AMOUNT",
            details={"amount": amount},
        )


class SelfTransferError(ConflictError):
    """Выбрасывается при попытке перевода средств на тот же самый счет."""

    def __init__(self, account_id: uuid.UUID):
        super().__init__(
            message="Нельзя перевести средства на тот же самый счет.",
            error_code="SELF_TRANSFER_NOT_ALLOWED",
            details={"account_id": str(account_id)},
        )


class InvalidTransactionStatusError(ConflictError):
    """Выбрасывается при попытке подтвердить/отменить транзакцию в неверном статусе."""

    def __init__(self, transaction_id: uuid.UUID, current_status: Any):
        super().__init__(
            message=f"Невозможно изменить статус транзакции. Текущий статус: {current_status}.",
            error_code="INVALID_TRANSACTION_STATUS",
            details={
                "transaction_id": str(transaction_id),
                "current_status": str(current_status),
            },
        )
