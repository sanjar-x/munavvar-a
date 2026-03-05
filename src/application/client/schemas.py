import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.modules.catalog.enums import ProductType
from src.modules.orders.enums import OrderStatus, PaymentMethod
from src.modules.users.models import Role

# --- 1. КАТАЛОГ И БАЛАНСЫ ---


class ProductDTO(BaseModel):
    id: uuid.UUID
    type: ProductType
    name: str
    price: int
    attributes: dict[str, Any]
    returnable_item_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryResponse(BaseModel):
    id: uuid.UUID
    name: str


class InventoryBalanceDTO(BaseModel):
    quantity: int
    product: ProductDTO


class ClientInventoryAndBalancesDTO(BaseModel):
    inventory: InventoryResponse
    balances: list[InventoryBalanceDTO]

    model_config = ConfigDict(from_attributes=True)


# --- 2. ФИНАНСЫ ---


class AccountDTO(BaseModel):
    id: uuid.UUID
    name: str
    balance: int
    model_config = ConfigDict(from_attributes=True)


# --- 3. ЗАКАЗЫ ---


class OrderCourierShortDTO(BaseModel):
    id: uuid.UUID
    username: str

    model_config = ConfigDict(from_attributes=True)


class OrderInventoryShortDTO(BaseModel):
    id: uuid.UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class OrderItemDTO(BaseModel):
    id: uuid.UUID
    quantity: int
    unit_price: int
    product: ProductDTO

    model_config = ConfigDict(from_attributes=True)


class OrderDTO(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    payment_method: PaymentMethod
    total_amount: int
    created_at: datetime
    updated_at: datetime

    # Вложенные связи заказа
    client_inventory: OrderInventoryShortDTO
    courier: OrderCourierShortDTO | None = None
    items: list[OrderItemDTO]

    model_config = ConfigDict(from_attributes=True)


# --- 4. КОРНЕВАЯ СХЕМА КЛИЕНТА (DASHBOARD 360) ---


class ClientResponse(BaseModel):
    """Полная карточка клиента для возврата из API"""

    id: uuid.UUID
    username: str
    phone: str | None = None
    account: AccountDTO | None = None
    inventories: list[ClientInventoryAndBalancesDTO]
    orders: list[OrderDTO]

    model_config = ConfigDict(from_attributes=True)


class ClientCreate(BaseModel):
    username: str = Field(..., description="ФИО или Название компании")
    phone: str = Field(
        ..., description="Номер телефона клиента (будет Identity)"
    )
    role: Role = Field(default=Role.CLIENT_B2C)
    address_name: str | None = Field(
        default=None, description="Название первого адреса (Инвентаря)"
    )


# --- ГЛАВНАЯ СХЕМА ---


class ClientDTO(BaseModel):
    id: uuid.UUID
    username: str
    phone: str | None = None
    is_active: bool
    orders: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientsResponse(BaseModel):
    total_count: int
    clients: list[ClientDTO]
