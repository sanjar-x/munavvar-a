import enum


class InventoryType(enum.StrEnum):
    FACTORY = "factory"
    WAREHOUSE = "warehouse"
    COURIER_CAR = "courier_car"
    CLIENT_BALCONY = "client_balcony"
    VIRTUAL = "virtual"
    LOSS = "loss"
