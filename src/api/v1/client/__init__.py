from fastapi import APIRouter

from src.api.v1.client.catalog import catalog_router
from src.api.v1.client.contracts import contracts_router
from src.api.v1.client.finances import finances_router
from src.api.v1.client.inventory import inventory_router
from src.api.v1.client.login import login_router
from src.api.v1.client.orders import orders_router
from src.api.v1.client.profile import profile_router

client_router = APIRouter()
client_router.include_router(
    login_router, prefix="/login", tags=["Client | Auth"]
)
client_router.include_router(
    profile_router, prefix="/profile", tags=["Client | Profile"]
)
client_router.include_router(
    catalog_router, prefix="/catalog", tags=["Client | Catalog"]
)
client_router.include_router(
    orders_router, prefix="/orders", tags=["Client | Orders"]
)
client_router.include_router(
    inventory_router, prefix="/inventory", tags=["Client | Inventory"]
)
client_router.include_router(
    finances_router,
    prefix="/finances",
    tags=["Client | Finances"],
)
client_router.include_router(
    contracts_router,
    prefix="",
    tags=["Client | Contracts"],
)
