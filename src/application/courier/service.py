# src/application/courier/service.py
from typing import Any

from src.application.courier.schemas import CourierCreate
from src.application.courier.uow import CourierUnitOfWork
from src.modules.finances.enums import AccountType
from src.modules.users.models import Role


class CourierService:
    def __init__(self, uow: CourierUnitOfWork):
        self.uow = uow

    async def create_courier(self, data: CourierCreate) -> dict[str, Any]:
        async with self.uow:
            courier = await self.uow.users.add({
                "username": data.username,
                "role": Role.COURIER,
                "is_active": True,
            })
            await self.uow.session.flush()

            courier_account = await self.uow.accounts.add({
                "type": AccountType.COURIER,
                "user_id": courier.id,
                "name": f"Счет курьера: {courier.username}",
                "balance": 0,
            })

            await self.uow.commit()

            return {
                "id": courier.id,
                "username": courier.username,
                "phone": data.phone,
                "account": courier_account,
            }
