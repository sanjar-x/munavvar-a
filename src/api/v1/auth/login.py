# src/api/v1/auth/login.py

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from src.api.dependencies.services import get_auth_service
from src.modules.auth.schemas import LocalLogin, TokenResponse
from src.modules.auth.services import AuthService

login_router = APIRouter()


@login_router.post(
    "/",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Вход в систему (Получение Access Token)",
)
async def login(
    # FastAPI сам распарсит x-www-form-urlencoded и достанет username/password
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    # Адаптируем данные из OAuth2 формы под нашу внутреннюю Pydantic-схему
    login_data = LocalLogin(
        phone=form_data.username, password=form_data.password
    )

    token_response = await auth_service.local_login(login_data)

    return token_response
