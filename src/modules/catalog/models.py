import uuid
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import BaseModel
from src.modules.catalog.enums import ProductType

product_type_enum = Enum(
    ProductType, name="product_type_enum", create_type=True
)


class Product(BaseModel):
    type: Mapped[ProductType] = mapped_column(
        product_type_enum,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, server_default="{}"
    )
    returnable_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(column="products.id", ondelete="RESTRICT"),
        nullable=True,
    )
    returnable_item: Mapped["Product"] = relationship(
        remote_side="Product.id",
        backref="associated_products",
    )
