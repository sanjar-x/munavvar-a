from fastapi import APIRouter

from src.api.v1.client.catalog import catalog_router
from src.api.v1.client.profile import profile_router

client_router = APIRouter()
client_router.include_router(
    profile_router, prefix="/profile", tags=["Client | Profile"]
)
client_router.include_router(
    catalog_router, prefix="/catalog", tags=["Client | Catalog"]
)
