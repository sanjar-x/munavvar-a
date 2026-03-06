import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.modules.catalog.enums import ProductType
from src.modules.orders.enums import OrderStatus, PaymentMethod
from src.modules.users.models import Role


# --- CREATE CLIENT ---
class ClientCreate(BaseModel):
    username: str = Field(..., description="ФИО или Название компании")
    phone: str = Field(..., description="Номер телефона клиента (будет Identity)")
    role: Role = Field(
        default=Role.CLIENT_B2C,
        description="Тип клиента: физическое (client_b2c) или юридическое лицо (client_b2b)",
    )
    address_name: str | None = Field(
        default=None, description="Название первого адреса (Инвентаря)"
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Role) -> Role:
        if v not in (Role.CLIENT_B2C, Role.CLIENT_B2B):
            raise ValueError(
                "Разрешено создавать только роли client_b2c или client_b2b"
            )
        return v


class InventoryCreate(BaseModel):
    name: str = Field(..., description="Название склада/машины")


class InventoryUpdate(BaseModel):
    name: str | None = None


# --- CLIENTS LIST ---
class Client(BaseModel):
    id: uuid.UUID
    username: str
    phone: str | None = None
    is_active: bool
    orders: int
    created_at: datetime


class ClientsResponse(BaseModel):
    total_count: int
    clients: list[Client]


# --- CLIENT DETAIL ---


class Product(BaseModel):
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


class Inventory(BaseModel):
    id: uuid.UUID
    name: str


class InventoryBalance(BaseModel):
    quantity: int
    product: Product


class InventoryAndBalances(BaseModel):
    inventory: Inventory
    balances: list[InventoryBalance]

    model_config = ConfigDict(from_attributes=True)


class Account(BaseModel):
    id: uuid.UUID
    name: str
    balance: int
    model_config = ConfigDict(from_attributes=True)


class OrderCourierShortDTO(BaseModel):
    id: uuid.UUID
    username: str

    model_config = ConfigDict(from_attributes=True)


class OrderInventoryShortDTO(BaseModel):
    id: uuid.UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class OrderItem(BaseModel):
    id: uuid.UUID
    quantity: int
    unit_price: int
    product: Product
    model_config = ConfigDict(from_attributes=True)


class Order(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    payment_method: PaymentMethod
    total_amount: int
    created_at: datetime
    updated_at: datetime

    # Вложенные связи заказа
    client_inventory: OrderInventoryShortDTO
    courier: OrderCourierShortDTO | None = None
    items: list[OrderItem]

    model_config = ConfigDict(from_attributes=True)


class FullClientResponse(BaseModel):
    id: uuid.UUID
    username: str
    phone: str | None = None
    account: Account | None = None
    inventories: list[InventoryAndBalances]
    orders: list[Order]

    model_config = ConfigDict(from_attributes=True)


class ClientUpdate(BaseModel):
    username: str | None = Field(default=None, description="ФИО или Название компании")
    phone: str | None = Field(default=None, description="Новый номер телефона")
    role: Literal[Role.CLIENT_B2C, Role.CLIENT_B2B] | None = Field(
        default=None,
        description="Тип клиента: физическое или юридическое лицо",
    )
