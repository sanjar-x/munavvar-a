import enum


class AccountType(enum.StrEnum):
    REVENUE = "revenue"
    CASH = "cash"
    CARD = "card"
    BANK = "bank"
    DISCOUNT = "discount"
    CLIENT = "client"
    COURIER = "courier"
    EXPENSE = "expense"
    ADMIN = "admin"


class TransactionStatus(enum.StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    REJECTED = "rejected"
