from fastapi import APIRouter

from src.api.v1.courier.catalog import catalog_router
from src.api.v1.courier.finances import finances_router
from src.api.v1.courier.login import login_router
from src.api.v1.courier.orders import orders_router
from src.api.v1.courier.profile import profile_router

courier_router = APIRouter()
courier_router.include_router(
    login_router, prefix="/login", tags=["Courier | Auth"]
)
courier_router.include_router(
    profile_router, prefix="/profile", tags=["Courier | Profile"]
)
courier_router.include_router(
    catalog_router, prefix="/catalog", tags=["Courier | Catalog"]
)

courier_router.include_router(
    orders_router, prefix="/orders", tags=["Courier | Orders"]
)
courier_router.include_router(
    finances_router,
    prefix="/finances",
    tags=["Courier | Finances"],
)
