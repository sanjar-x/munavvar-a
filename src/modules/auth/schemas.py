from pydantic import BaseModel, Field

from src.modules.users.schemas import PhoneStr


class LocalLogin(BaseModel):
    phone: PhoneStr
    password: str = Field(..., min_length=1, description="Пароль пользователя")


class TokenResponse(BaseModel):
    """
    Стандартная схема ответа при успешной авторизации.
    Поля access_token и token_type обязательны по спецификации OAuth2.
    """

    access_token: str
    token_type: str = "bearer"
