import enum


class TransferStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class InventoryType(enum.StrEnum):
    FACTORY = "factory"
    WAREHOUSE = "warehouse"
    COURIER_CAR = "courier_car"
    CLIENT_BALCONY = "client_balcony"
    VIRTUAL = "virtual"
    LOSS = "loss"
