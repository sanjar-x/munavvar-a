import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.modules.catalog.enums import ProductType
from src.modules.users.models import Role

# ==========================================
# 1. КАСТОМНЫЕ ТИПЫ (Переиспользуемая валидация)
# ==========================================

# Валидация телефона (международный формат, от 8 до 15 цифр, опциональный +)
PhoneStr = Annotated[
    str,
    Field(
        pattern=r"^\+?[1-9]\d{7,14}$",
        json_schema_extra={"example": "+998901234567"},
        description="Номер телефона в международном формате",
    ),
]

FullNameStr = Annotated[
    str,
    Field(
        min_length=2,
        max_length=255,
        strip_whitespace=True,
        json_schema_extra={"example": "Анвар Анваров"},
    ),
]

# Строгая валидация пароля (только для входящих данных)
PasswordStr = Annotated[
    str,
    Field(
        min_length=4,
        max_length=128,
        json_schema_extra={"example": "StrongPass123!"},
        description="Пароль",
    ),
]


# ==========================================
# 2. БАЗОВАЯ СХЕМА (Общие поля)
# ==========================================
class UserBase(BaseModel):
    full_name: FullNameStr


# ==========================================
# 3. СХЕМА СОЗДАНИЯ (Регистрация)
# ==========================================


class UserCreate(UserBase):
    password: PasswordStr
    phone: PhoneStr


# 2. Схема для администратора (Управление доступом)
class UserAdminCreate(UserBase):
    phone: PhoneStr
    password: PasswordStr
    role: Role


# ==========================================
# 4. СХЕМА ОБНОВЛЕНИЯ (PATCH запрос)
# ==========================================
class UserProfileUpdate(BaseModel):
    full_name: FullNameStr | None = None


# 2. Схема для администратора (Управление доступом)
class UserAdminUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


# ==========================================
# 5. СХЕМА ОТВЕТА (Что отдаем клиенту)
# ==========================================
class UserResponse(UserBase):
    """
    Эту схему мы возвращаем из роутера.
    Она включает ID и даты, но НИКОГДА не включает пароль (даже хешированный).
    """

    id: uuid.UUID
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UserResponseList(BaseModel):
    total_count: int
    users: list[UserResponse]


class InventoryProduct(BaseModel):
    type: ProductType = Field(
        ..., title="Тип товара", examples=[ProductType.CONTAINER]
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        title="Название товара",
        examples=["Вода MunavvarA 19Л ПК"],
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        title="Характеристики",
        description="JSON с физическими свойствами (volume, material)",
        examples=[{"volume": 18.9, "material": "PC"}],
    )
    quantity: int = Field(description="Количество")


class UsersDashboard(BaseModel):
    id: uuid.UUID
    role: Literal[Role.CLIENT_B2C, Role.CLIENT_B2B]
    full_name: FullNameStr
    phone: PhoneStr
    model_config = ConfigDict(from_attributes=True)
    inventory: list[InventoryProduct]
    balance: int = Field(description="Задолжность")


class UsersDashboardResponse(BaseModel):
    total_count: int
    users: list[UsersDashboard]
