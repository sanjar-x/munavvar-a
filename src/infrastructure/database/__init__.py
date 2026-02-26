# src/infrastructure/database/__init__.py

from src.infrastructure.database.base import BaseModel
from src.modules.catalog.models import Product
from src.modules.finances.models import Account, Transaction
from src.modules.logistics.inventory.models import Inventory, StockTransaction
from src.modules.logistics.warehouse.models import Transfer, TransferItem
from src.modules.orders.models import Order, OrderItem
from src.modules.users.models import Identity, User

__all__ = (
    "BaseModel",
    "Product",
    "Account",
    "Transaction",
    "Inventory",
    "StockTransaction",
    "Transfer",
    "TransferItem",
    "Order",
    "OrderItem",
    "Identity",
    "User",
)
