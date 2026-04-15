import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.modules.catalog.enums import ProductType


class ProductAttribute(BaseModel):
    """Парная характеристика товара (label → value)."""

    label: str = Field(
        ...,
        min_length=1,
        max_length=255,
        title="Название характеристики",
        examples=["Объём"],
    )
    value: str = Field(
        ...,
        min_length=1,
        max_length=255,
        title="Значение характеристики",
        examples=["19Л"],
    )


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
        description="Цена в сумах (UZS), целое число",
        examples=[20000],
    )
    attributes: list[ProductAttribute] = Field(
        default_factory=list,
        title="Характеристики",
        description=(
            "Список парных характеристик товара"
            " (объём, материал, мощность и т.д.)"
        ),
        examples=[
            [
                {"label": "Объём", "value": "19Л"},
                {"label": "Материал", "value": "ПК"},
            ]
        ],
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
    attributes: list[ProductAttribute] | None = Field(default=None)
    returnable_item_id: uuid.UUID | None = Field(default=None)


# --- СХЕМА ОТВЕТА (GET /products) ---
class ProductResponse(ProductBase):
    id: uuid.UUID
    type: ProductType

    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
