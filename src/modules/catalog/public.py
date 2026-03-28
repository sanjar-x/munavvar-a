"""Catalog module public API.

Other modules MUST import only from this file.
Do not import from catalog.models, catalog.repositories,
catalog.uow, or catalog.exceptions directly.
"""

from src.modules.catalog.dtos import ProductDTO
from src.modules.catalog.enums import ProductType
from src.modules.catalog.services import CatalogService

__all__ = [
    "CatalogService",
    "ProductDTO",
    "ProductType",
]
