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
                f"Договор недоступен для оформления заказов (статус: {status})"
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
                "overage": (current_exposure + order_amount - credit_limit),
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
                f"Невозможно перевести договор из статуса {current} в {target}"
            ),
            error_code="CONTRACT_STATUS_TRANSITION_ERROR",
            details={
                "contract_id": str(contract_id),
                "current_status": current,
                "target_status": target,
            },
        )


class ContractRequiredError(BadRequestError):
    """PaymentMethod=CONTRACT, но активный договор не найден."""

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
