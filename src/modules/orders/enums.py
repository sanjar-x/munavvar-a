import enum


class OrderStatus(enum.StrEnum):
    NEW = "new"  # Создан клиентом
    ASSIGNED = "assigned"  # Админ назначил курьера
    IN_TRANSIT = "in_transit"  # Курьер взял в работу
    ARRIVED = "arrived"  # Курьер у двери
    DELIVERED = "delivered"  # Вода отдана, цикл закрыт
    PICKUP_COMPLETED = "pickup_completed"
    CANCELLED = "cancelled"  # Отмена


class SaleType(enum.StrEnum):
    DELIVERY = "delivery"
    WAREHOUSE_PICKUP = "warehouse_pickup"


class PaymentMethod(enum.StrEnum):
    CASH = "cash"  # Наличные
    CARD = "card"  # Перевод на карту / QR
    CONTRACT = "contract"  # По договору (Перечисление)
