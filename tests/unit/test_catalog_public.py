"""Unit tests for Catalog public.py facade (ARCH-02)."""

from src.modules.catalog import public


class TestCatalogPublicFacade:
    def test_all_exports_defined(self):
        assert hasattr(public, "__all__")
        assert set(public.__all__) == {
            "CatalogService",
            "ProductDTO",
            "ProductType",
        }

    def test_catalog_service_importable(self):
        from src.modules.catalog.public import CatalogService

        assert CatalogService is not None

    def test_product_dto_importable(self):
        from src.modules.catalog.public import ProductDTO

        assert ProductDTO is not None

    def test_product_type_importable(self):
        from src.modules.catalog.public import ProductType

        assert ProductType is not None

    def test_no_repository_exported(self):
        assert "ProductRepository" not in dir(public)

    def test_no_uow_exported(self):
        assert "CatalogUnitOfWork" not in dir(public)

    def test_no_exceptions_exported(self):
        assert "ProductNotFoundError" not in dir(public)
        assert "InvalidReturnableItemError" not in dir(public)
