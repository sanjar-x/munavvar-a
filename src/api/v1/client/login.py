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
    summary="Вход в систему (Получение Access Token)",
)
async def login(
    phone: str,
    # FastAPI сам распарсит x-www-form-urlencoded и достанет username/password
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    # Адаптируем данные из OAuth2 формы под нашу внутреннюю Pydantic-схему

    token_response = await auth_service.client_login(phone)

    return token_response
