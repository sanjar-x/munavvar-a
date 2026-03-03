# src/api/v1/client/catalog.py
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security

from src.core.security.permissions import Scope
from src.modules.auth.dependencies import get_current_user
from src.modules.catalog.dependencies import get_catalog_service
from src.modules.catalog.enums import ProductType
from src.modules.catalog.schemas import ProductResponse
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
    product_type: Annotated[
        ProductType | None, Query(description="Фильтр по типу")
    ] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return await catalog_service.get_catalog(
        skip=skip, limit=limit, product_type=product_type
    )
