# src/modules/contracts/exceptions.py
import uuid
from datetime import date

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


class QuantityLimitExceededError(BadRequestError):
    """Заказ превысит квоту по продукту в договоре."""

    def __init__(
        self,
        contract_id: uuid.UUID | str,
        product_id: uuid.UUID | str,
        quantity_limit: int,
        quantity_used: int,
        requested: int,
    ):
        super().__init__(
            message=(
                "Квота по продукту в договоре будет превышена. "
                "Уменьшите количество или обратитесь к менеджеру."
            ),
            error_code="QUANTITY_LIMIT_EXCEEDED",
            details={
                "contract_id": str(contract_id),
                "product_id": str(product_id),
                "quantity_limit": quantity_limit,
                "quantity_used": quantity_used,
                "requested": requested,
                "available": quantity_limit - quantity_used,
            },
        )


class ProductNotInContractError(BadRequestError):
    """Продукт отсутствует в прайс-листе договора."""

    def __init__(
        self,
        contract_id: uuid.UUID | str,
        product_id: uuid.UUID | str,
    ):
        super().__init__(
            message=(
                "Данный продукт отсутствует в прайс-листе договора. "
                "Заказ по договору возможен только для товаров из "
                "договорного прайс-листа."
            ),
            error_code="PRODUCT_NOT_IN_CONTRACT",
            details={
                "contract_id": str(contract_id),
                "product_id": str(product_id),
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


class PriceItemHasUsageError(ConflictError):
    """Нельзя удалить/уменьшить квоту позиции с использованием."""

    def __init__(
        self,
        contract_id: uuid.UUID | str,
        product_id: uuid.UUID | str,
        quantity_used: int,
    ):
        super().__init__(
            message=(
                "Невозможно удалить позицию прайс-листа: "
                "есть активные заказы с этим продуктом."
            ),
            error_code="PRICE_ITEM_HAS_USAGE",
            details={
                "contract_id": str(contract_id),
                "product_id": str(product_id),
                "quantity_used": quantity_used,
            },
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


class InvoiceNotFoundError(NotFoundError):
    def __init__(self, invoice_id: uuid.UUID | str):
        super().__init__(
            message="Счёт-фактура не найдена",
            error_code="INVOICE_NOT_FOUND",
            details={"invoice_id": str(invoice_id)},
        )


class InvalidInvoiceTransitionError(ConflictError):
    """Недопустимый переход статуса счёт-фактуры."""

    def __init__(
        self,
        invoice_id: uuid.UUID | str,
        current_status: str,
        expected_statuses: list[str],
    ):
        super().__init__(
            message=(
                f"Переход из статуса {current_status} недопустим. "
                f"Ожидаемые статусы: {', '.join(expected_statuses)}"
            ),
            error_code="INVALID_INVOICE_TRANSITION",
            details={
                "invoice_id": str(invoice_id),
                "current_status": current_status,
                "expected_statuses": expected_statuses,
            },
        )


class DuplicateInvoicePeriodError(ConflictError):
    """Инвойс за этот период уже существует (не CANCELLED)."""

    def __init__(
        self,
        contract_id: uuid.UUID | str,
        period_from: date,
        period_to: date,
    ):
        super().__init__(
            message=(
                "Счёт-фактура за этот период уже существует. "
                "Аннулируйте предыдущую, чтобы выставить новую."
            ),
            error_code="DUPLICATE_INVOICE_PERIOD",
            details={
                "contract_id": str(contract_id),
                "period_from": str(period_from),
                "period_to": str(period_to),
            },
        )


class DuplicateAmendmentNumberError(ConflictError):
    """Доп. соглашение с таким номером уже существует для данного договора."""

    def __init__(
        self,
        contract_id: uuid.UUID | str,
        number: str,
    ):
        super().__init__(
            message=(
                f"Доп. соглашение с номером '{number}' "
                "уже существует для данного договора."
            ),
            error_code="DUPLICATE_AMENDMENT_NUMBER",
            details={
                "contract_id": str(contract_id),
                "number": number,
            },
        )
