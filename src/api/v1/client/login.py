# src/api/v1/auth/login.py

from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.modules.auth.dependencies import get_auth_service
from src.modules.auth.schemas import TokenResponse
from src.modules.auth.services import AuthService

login_router = APIRouter()


@login_router.post(
    "",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Вход клиента (Получение Access Token)",
)
async def login(
    phone: str,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    token_response = await auth_service.client_login(phone)

    return token_response
