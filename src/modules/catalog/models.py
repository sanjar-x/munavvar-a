# src/modules/catalog/models.py
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import BIGINT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel
from src.modules.catalog.enums import ProductType

product_type_enum = Enum(
    ProductType,
    name="product_type_enum",
    native_enum=True,
    create_type=True,
    values_callable=lambda e: [m.value for m in e],
)


class Product(BaseModel):
    __tablename__ = "products"

    returnable_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment=(
            "Ссылка на оборотную тару"
            " (например, пустая бутыль 19л, привязанная к воде)"
        ),
    )

    type: Mapped[ProductType] = mapped_column(
        product_type_enum,
        nullable=False,
        index=True,
        comment="Категория продукта (WATER, EQUIPMENT, CONTAINER)",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Витринное название товара",
    )
    price: Mapped[int] = mapped_column(
        BIGINT,
        nullable=False,
        default=0,
        comment="Базовая стоимость товара",
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Динамические характеристики (объем, бренд, цвет, мощность)",
    )

    returnable_item: Mapped["Product | None"] = relationship(
        remote_side="Product.id",
        back_populates="associated_products",
    )
    associated_products: Mapped[list["Product"]] = relationship(
        back_populates="returnable_item",
    )

    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_product_price_pos"),
        Index(
            "idx_product_attributes_gin", "attributes", postgresql_using="gin"
        ),
        {"comment": "Единый каталог товаров, услуг и оборотной тары"},
    )
