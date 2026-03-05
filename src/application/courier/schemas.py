# src/application/courier/schemas.py
from pydantic import BaseModel, Field


class CourierCreate(BaseModel):
    username: str = Field(..., description="ФИО курьера")
    phone: str = Field(
        ..., description="Номер телефона курьера (будет Identity)"
    )
    password: str = Field(..., description="Пароль курьера")
