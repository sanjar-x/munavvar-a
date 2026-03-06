from fastapi import APIRouter

from src.api.v1.backoffice.catalog import catalog_router
from src.api.v1.backoffice.clients import clients_router
from src.api.v1.backoffice.couriers import couriers_router
from src.api.v1.backoffice.orders import orders_router
from src.api.v1.backoffice.profile import profile_router
from src.api.v1.backoffice.users import users_router

backoffice = APIRouter()
backoffice.include_router(
    profile_router, prefix="/profile", tags=["Backoffice | Profile"]
)
backoffice.include_router(
    couriers_router, prefix="/couriers", tags=["Backoffice | Couriers"]
)
backoffice.include_router(
    clients_router, prefix="/clients", tags=["Backoffice | Clients"]
)
backoffice.include_router(users_router, prefix="/users", tags=["Backoffice | Users"])

backoffice.include_router(
    catalog_router, prefix="/catalog", tags=["Backoffice | Catalog"]
)
backoffice.include_router(orders_router, prefix="/orders", tags=["Backoffice | Orders"])
