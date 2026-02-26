from fastapi import APIRouter

from src.api.v1.auth import auth_router
from src.api.v1.backoffice import backoffice
from src.api.v1.client import client_router
from src.api.v1.courier import courier_router

api_v1_router = APIRouter()

api_v1_router.include_router(router=auth_router, prefix="/auth")
api_v1_router.include_router(router=backoffice, prefix="/backoffice")
api_v1_router.include_router(router=courier_router, prefix="/courier")
api_v1_router.include_router(router=client_router, prefix="/client")
