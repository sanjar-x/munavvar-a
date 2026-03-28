import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.modules.catalog.enums import ProductType


@dataclass(frozen=True, slots=True)
class ProductDTO:
    """Frozen data transfer object for Product.

    Field order matches Product model column definitions.
    """

    id: uuid.UUID
    returnable_item_id: uuid.UUID | None
    type: ProductType
    name: str
    price: int
    attributes: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


def product_to_dto(product: Any) -> ProductDTO:
    """Convert ORM Product instance to frozen DTO."""
    return ProductDTO(
        id=product.id,
        returnable_item_id=product.returnable_item_id,
        type=product.type,
        name=product.name,
        price=product.price,
        attributes=dict(product.attributes),
        is_active=product.is_active,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )
