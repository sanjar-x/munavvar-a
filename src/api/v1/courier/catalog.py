# src/api/v1/client/catalog.py
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_courier
from src.modules.catalog.dependencies import get_catalog_service
from src.modules.catalog.enums import ProductType
from src.modules.catalog.public import CatalogService
from src.modules.catalog.schemas import ProductResponse

catalog_router = APIRouter()


@catalog_router.get(
    "/",
    response_model=list[ProductResponse],
    summary="Получить список товаров",
)
async def get_catalog(
    current_user: Annotated[
        User, Security(get_current_courier, scopes=[Scope.CATALOG_READ])
    ],
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    product_type: Annotated[
        ProductType | None, Query(description="Фильтр по типу")
    ] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return await catalog_service.get_catalog(
        skip=skip, limit=limit, product_type=product_type
    )
