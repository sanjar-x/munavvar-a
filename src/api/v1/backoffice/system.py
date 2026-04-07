# src/api/v1/backoffice/system.py
from typing import Annotated

from fastapi import APIRouter, Security, status

from src.core.security.permissions import Scope
from src.core.seeder import Seeder
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user

system_router = APIRouter()


@system_router.post(
    "/seed",
    status_code=status.HTTP_200_OK,
    summary="Заполнить базу Mock-данными",
    tags=["Backoffice | System"],
)
async def seed_database(
    current_admin: Annotated[
        User,
        Security(get_current_user, scopes=[Scope.USERS_WRITE]),
    ],
):
    """
    Запускает генератор тестовых данных
    (Товары, Склады, Курьеры, Клиенты, Заказы).
    Доступно только администраторам.
    """
    seeder = Seeder()
    await seeder.seed_all()
    return {"message": "Database seeded successfully!"}
