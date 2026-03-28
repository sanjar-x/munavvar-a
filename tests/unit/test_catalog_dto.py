"""Unit tests for Catalog frozen DTO convention (ARCH-03)."""

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from src.modules.catalog.dtos import ProductDTO, product_to_dto
from src.modules.catalog.enums import ProductType


class TestProductDTO:
    def test_dto_is_frozen(self):
        dto = ProductDTO(
            id=uuid.uuid4(),
            returnable_item_id=None,
            type=ProductType.WATER,
            name="Test Water",
            price=20000,
            attributes={"volume": 18.9},
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        with pytest.raises(FrozenInstanceError):
            dto.name = "Modified"

    def test_dto_has_slots(self):
        assert hasattr(ProductDTO, "__slots__")

    def test_dto_field_count(self):
        """ProductDTO must have exactly 9 fields matching Product model."""
        import dataclasses

        fields = dataclasses.fields(ProductDTO)
        field_names = [f.name for f in fields]
        assert field_names == [
            "id",
            "returnable_item_id",
            "type",
            "name",
            "price",
            "attributes",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def test_converter_copies_attributes_dict(self):
        """Converter must copy mutable dict, not share reference."""
        original_attrs = {"volume": 18.9}

        class FakeProduct:
            id = uuid.uuid4()
            returnable_item_id = None
            type = ProductType.WATER
            name = "Test"
            price = 20000
            attributes = original_attrs
            is_active = True
            created_at = datetime.now(UTC)
            updated_at = datetime.now(UTC)

        dto = product_to_dto(FakeProduct())
        assert dto.attributes == original_attrs
        assert dto.attributes is not original_attrs
