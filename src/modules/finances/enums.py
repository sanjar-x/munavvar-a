import enum


class AccountType(enum.StrEnum):
    REVENUE = "revenue"
    CASH = "cash"
    CARD = "card"
    BANK = "bank"
    DISCOUNT = "discount"
    CLIENT = "client"
    COURIER = "courier"


class TransactionStatus(enum.StrEnum):
    PENDING = "pending"  # Ждет проверки бухгалтером (скриншот загружен)
    COMPLETED = "completed"  # Деньги реально на счету (влияет на баланс)
    REJECTED = "rejected"  # Фейковый скриншот или отмена
