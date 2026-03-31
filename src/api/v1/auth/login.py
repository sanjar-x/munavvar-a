# src/api/v1/auth/login.py

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from src.modules.auth.dependencies import get_auth_service
from src.modules.auth.schemas import LocalLogin, TokenResponse
from src.modules.auth.services import AuthService

login_router = APIRouter()


@login_router.post(
    "",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Вход для staff (Получение Access Token)",
)
async def login(
    # Swagger OAuth2 использует поле username,
    # поэтому здесь адаптируем его к phone.
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    login_data = LocalLogin(phone=form_data.username, password=form_data.password)

    token_response = await auth_service.local_login(login_data)

    return token_response
