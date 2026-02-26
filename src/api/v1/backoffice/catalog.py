# src/api/v1/catalog/products.py
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security, status

from src.api.dependencies.auth import get_current_user
from src.api.dependencies.services import get_catalog_service
from src.core.security.permissions import Scope
from src.modules.catalog.enums import ProductType
from src.modules.catalog.schemas import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from src.modules.catalog.services import CatalogService
from src.modules.users.models import User

catalog_router = APIRouter()


@catalog_router.get(
    "/",
    response_model=list[ProductResponse],
    summary="Получить список товаров",
)
async def get_catalog(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CATALOG_READ])
    ],
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    product_type: Annotated[
        ProductType | None, Query(description="Фильтр по типу")
    ] = None,
):
    return await catalog_service.get_catalog(
        skip=skip, limit=limit, product_type=product_type
    )


@catalog_router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить новый товар",
)
async def create_product(
    schema: ProductCreate,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.CATALOG_WRITE])
    ],
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
):
    """Добавление новой позиции (Вода, Тара, Оборудование)."""
    return await catalog_service.add(schema)


@catalog_router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Редактировать товар",
)
async def update_product(
    product_id: uuid.UUID,
    schema: ProductUpdate,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.CATALOG_WRITE])
    ],
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
):
    return await catalog_service.update(id=product_id, schema=schema)


@catalog_router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить товар (Архивация)",
)
async def archive_product(
    product_id: uuid.UUID,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.CATALOG_WRITE])
    ],
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
):
    """Мягкое удаление товара из каталога (перевод is_active=False)."""
    await catalog_service.archive(id=product_id)
