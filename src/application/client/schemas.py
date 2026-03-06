import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from src.modules.catalog.enums import ProductType
from src.modules.inventory.enums import InventoryType
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


class Account(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    balance: int


class Product(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    type: ProductType
    name: str
    price: int
    attributes: dict[str, Any] = Field(default_factory=dict)


class Balance(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    quantity: int
    product: Product


class Inventory(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    type: InventoryType
    name: str
    balances: list[Balance] = []


class ClientInventory(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    type: InventoryType
    name: str


class Courier(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    username: str


class Item(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    quantity: int
    unit_price: int
    product: Product

    @computed_field
    @property
    def subtotal(self) -> int:
        return self.quantity * self.unit_price


class Order(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    payment_method: PaymentMethod
    status: OrderStatus
    total_amount: int
    client_inventory: ClientInventory
    courier: Courier | None = None
    items: list[Item]
    created_at: datetime


class ClientResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )
    id: uuid.UUID
    username: str
    phone: str | None = None
    account: Account | None = None
    inventories: list[Inventory] = []
    client_orders: list[Order] = []


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


class ClientUpdate(BaseModel):
    username: str | None = Field(default=None, description="ФИО или Название компании")
    phone: str | None = Field(default=None, description="Новый номер телефона")
    role: Literal[Role.CLIENT_B2C, Role.CLIENT_B2B] | None = Field(
        default=None,
        description="Тип клиента: физическое или юридическое лицо",
    )
