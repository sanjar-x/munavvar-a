import enum


class InventoryType(enum.StrEnum):
    WAREHOUSE = "WAREHOUSE"  # Главный склад / Завод
    COURIER = "COURIER"  # Машина курьера
    CLIENT = "CLIENT"  # Клиент (у него копятся пустые бутыли!)
    VIRTUAL_LOSS = "VIRTUAL_LOSS"  # Виртуальная яма для потерянных/разбитых бутылей
    VIRTUAL_VENDOR = "VIRTUAL_VENDOR"  # Источник новых бутылей (закупки) и находок


class TransferType(enum.StrEnum):
    FACTORY_RECEIPT = "FACTORY_RECEIPT"
    PURCHASE = "PURCHASE"
    PRODUCTION = "PRODUCTION"

    COURIER_LOAD = "COURIER_LOAD"  # Загрузка
    COURIER_RETURN = "COURIER_RETURN"  # Выгрузка

    CLIENT_DELIVERY = "CLIENT_DELIVERY"  # Передача полной бутыли клиенту
    CLIENT_RETURN = "CLIENT_RETURN"  # Забор пустой бутыли у клиента

    WAREHOUSE_TRANSFER = "WAREHOUSE_TRANSFER"  # Между складами (если их несколько)
    LOSS_WRITE_OFF = "LOSS_WRITE_OFF"  # Списание
    INVENTORY_FINDING = "INVENTORY_FINDING"  # Оприходование
    INITIAL_BALANCE = "INITIAL_BALANCE"  # Ввод начальных остатков


class TransferStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
