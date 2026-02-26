from fastapi import APIRouter

from src.api.v1.auth.login import login_router
from src.api.v1.auth.register import register__router

auth_router = APIRouter()

auth_router.include_router(register__router, prefix="/register", tags=["Auth"])
auth_router.include_router(login_router, prefix="/login", tags=["Auth"])
