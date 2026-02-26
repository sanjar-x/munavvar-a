import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.modules.catalog.models import ProductType


# --- БАЗОВАЯ СХЕМА ---
# Хранит общие поля, чтобы не дублировать код
class ProductBase(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        title="Название товара",
        examples=["Вода Завод А 19Л ПК"],
    )
    price: int = Field(
        default=0,
        ge=0,  # ge=0 гарантирует, что цена не будет отрицательной
        title="Цена",
        description="Цена в минимальных единицах (копейки/тиыйны)",
        examples=[20000],
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        title="Характеристики",
        description="JSON с физическими свойствами (volume, material)",
        examples=[{"volume": 18.9, "material": "PC"}],
    )
    returnable_item_id: uuid.UUID | None = Field(
        default=None,
        title="ID возвратной тары",
        description="Указывается для воды, требующей обмена пустой бутылки",
    )


# --- СХЕМА ДЛЯ СОЗДАНИЯ (POST /products) ---
class ProductCreate(ProductBase):
    type: ProductType = Field(
        ..., title="Тип товара", examples=[ProductType.WATER]
    )


# --- СХЕМА ДЛЯ ОБНОВЛЕНИЯ (PATCH /products/{id}) ---
class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: ProductType | None = Field(default=None)
    price: int | None = Field(default=None, ge=0)
    attributes: dict[str, Any] | None = Field(default=None)
    returnable_item_id: uuid.UUID | None = Field(default=None)


# --- СХЕМА ОТВЕТА (GET /products) ---
class ProductResponse(ProductBase):
    id: uuid.UUID
    type: ProductType

    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
