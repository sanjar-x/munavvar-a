from fastapi import APIRouter

from src.api.v1.backoffice.balances import balances_router
from src.api.v1.backoffice.catalog import catalog_router
from src.api.v1.backoffice.clients import clients_router
from src.api.v1.backoffice.contracts import contracts_router
from src.api.v1.backoffice.couriers import couriers_router
from src.api.v1.backoffice.dashboard import (
    dashboard_router,
)
from src.api.v1.backoffice.finances import finances_router
from src.api.v1.backoffice.inventories import inventories_router
from src.api.v1.backoffice.orders import orders_router
from src.api.v1.backoffice.profile import profile_router
from src.api.v1.backoffice.stock_transactions import (
    stock_transactions_router,
)
from src.api.v1.backoffice.system import system_router
from src.api.v1.backoffice.transfers import transfers_router
from src.api.v1.backoffice.transport import transport_router
from src.api.v1.backoffice.users import users_router
from src.api.v1.backoffice.warehouses import warehouses_router

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
backoffice.include_router(
    users_router, prefix="/users", tags=["Backoffice | Users"]
)

backoffice.include_router(
    catalog_router, prefix="/catalog", tags=["Backoffice | Catalog"]
)
backoffice.include_router(
    transport_router, prefix="/transports", tags=["Backoffice | Transports"]
)
backoffice.include_router(
    warehouses_router, prefix="/warehouses", tags=["Backoffice | Warehouses"]
)
backoffice.include_router(
    inventories_router,
    prefix="/inventories",
    tags=["Backoffice | Inventories"],
)
backoffice.include_router(
    transfers_router, prefix="/transfers", tags=["Backoffice | Transfers"]
)
backoffice.include_router(
    stock_transactions_router,
    prefix="/stock-transactions",
    tags=["Backoffice | Stock Transactions"],
)
backoffice.include_router(
    balances_router,
    prefix="/balances",
    tags=["Backoffice | Balances"],
)
backoffice.include_router(
    orders_router, prefix="/orders", tags=["Backoffice | Orders"]
)
backoffice.include_router(
    finances_router,
    prefix="/finances",
    tags=["Backoffice | Finances"],
)
backoffice.include_router(
    dashboard_router,
    prefix="/dashboard",
    tags=["Backoffice | Dashboard"],
)
backoffice.include_router(
    system_router, prefix="/system", tags=["Backoffice | System"]
)
backoffice.include_router(
    contracts_router,
    prefix="/contracts",
    tags=["Backoffice | Contracts"],
)
