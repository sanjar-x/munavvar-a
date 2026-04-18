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
    """Выбрасывается при попытке списания суммы,
    превышающей баланс (если мы запрещаем минусовой баланс)."""

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
            message=(
                f"Недопустимая сумма транзакции: {amount}."
                " Сумма должна быть больше нуля."
            ),
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


class SearchTooShortError(BadRequestError):
    """`q` короче минимальной длины (2)."""

    def __init__(self, length: int):
        super().__init__(
            message=(
                "Поисковый запрос слишком короткий. "
                "Минимальная длина — 2 символа."
            ),
            error_code="SEARCH_TOO_SHORT",
            details={"length": length, "min_length": 2},
        )


class SearchTooLongError(BadRequestError):
    """`q` длиннее максимальной длины (100)."""

    def __init__(self, length: int):
        super().__init__(
            message=(
                "Поисковый запрос слишком длинный. "
                "Максимальная длина — 100 символов."
            ),
            error_code="SEARCH_TOO_LONG",
            details={"length": length, "max_length": 100},
        )


class SearchUuidNotAllowedError(BadRequestError):
    """В `q` передан UUID / длинный hex — искать по id нужно явно."""

    def __init__(self) -> None:
        super().__init__(
            message=(
                "В поиске запрещён UUID. Используйте прямые фильтры "
                "(account_id, order_id, client_id и т.д.)."
            ),
            error_code="SEARCH_UUID_NOT_ALLOWED",
        )


class DateRangeInvalidError(BadRequestError):
    """`date_from > date_to`."""

    def __init__(self) -> None:
        super().__init__(
            message="Некорректный диапазон дат: date_from позже date_to.",
            error_code="DATE_RANGE_INVALID",
        )


class AmountRangeInvalidError(BadRequestError):
    """`amount_from > amount_to`."""

    def __init__(self) -> None:
        super().__init__(
            message=(
                "Некорректный диапазон суммы: amount_from больше amount_to."
            ),
            error_code="AMOUNT_RANGE_INVALID",
        )


class AmountConflictError(BadRequestError):
    """Одновременно `amount_eq` и `amount_from/to`."""

    def __init__(self) -> None:
        super().__init__(
            message=(
                "Параметр amount_eq нельзя сочетать с amount_from / amount_to."
            ),
            error_code="AMOUNT_CONFLICT",
        )


class DatePresetConflictError(BadRequestError):
    """Одновременно `date_preset` и `date_from/to`."""

    def __init__(self) -> None:
        super().__init__(
            message=(
                "Параметр date_preset нельзя сочетать с date_from / date_to."
            ),
            error_code="DATE_PRESET_CONFLICT",
        )


class PaginationTooDeepError(BadRequestError):
    """`page * size > 10_000` — требуется cursor (v2)."""

    def __init__(self, page: int, size: int):
        super().__init__(
            message=(
                "Слишком глубокая пагинация. "
                "Уточните фильтры или дождитесь cursor-пагинации."
            ),
            error_code="PAGINATION_TOO_DEEP",
            details={"page": page, "size": size, "limit": 10_000},
        )


class InvalidTransactionStatusError(ConflictError):
    """Выбрасывается при попытке подтвердить/отменить
    транзакцию в неверном статусе."""

    def __init__(self, transaction_id: uuid.UUID, current_status: Any):
        super().__init__(
            message=(
                "Невозможно изменить статус транзакции."
                f" Текущий статус: {current_status}."
            ),
            error_code="INVALID_TRANSACTION_STATUS",
            details={
                "transaction_id": str(transaction_id),
                "current_status": str(current_status),
            },
        )
