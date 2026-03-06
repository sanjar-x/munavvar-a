import enum


class Role(enum.StrEnum):
    SYSTEM = "system"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    STOREKEEPER = "storekeeper"
    CASHIER = "cashier"
    COURIER = "courier"
    CLIENT_B2C = "client_b2c"
    CLIENT_B2B = "client_b2b"


class AuthProvider(enum.StrEnum):
    LOCAL = "local"
    GOOGLE = "google"
    TELEGRAM = "telegram"
    APPLE = "apple"
