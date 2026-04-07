# src/modules/contracts/enums.py
import enum


class ContractStatus(enum.StrEnum):
    DRAFT = "draft"  # Создан, условия согласовываются
    ACTIVE = "active"  # Подписан, заказы разрешены
    SUSPENDED = "suspended"  # Приостановлен (просрочка/нарушение)
    TERMINATED = "terminated"  # Расторгнут досрочно
    EXPIRED = "expired"  # Истёк end_date


class InvoiceStatus(enum.StrEnum):
    DRAFT = "draft"  # Формируется автоматически
    ISSUED = "issued"  # Выставлен клиенту
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"  # Полностью погашен
    OVERDUE = "overdue"  # Срок оплаты прошёл
    CANCELLED = "cancelled"  # Аннулирован
