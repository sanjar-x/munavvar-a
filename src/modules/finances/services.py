import uuid

from src.modules.finances.enums import AccountType
from src.modules.finances.models import Account
from src.modules.finances.uow import FinancesUnitOfWork
from src.modules.users.exceptions import UserNotFoundError
from src.modules.users.models import User
from src.modules.users.services import UserService


class BillingService:
    def __init__(self, uow: FinancesUnitOfWork, user_service: UserService):
        self.uow: FinancesUnitOfWork = uow
        self.user_service: UserService = user_service

    async def get_or_add_client_account(self, client_id: uuid.UUID) -> Account:
        client: User | None = await self.user_service.get_client(id=client_id)
        if not client:
            raise UserNotFoundError(user_id=client_id)

        # Открываем транзакцию
        async with self.uow:
            client_account: Account | None = await self.uow.accounts.get_client_account(
                client_id=client.id
            )

            if not client_account:
                client_account_data = {
                    "type": AccountType.CLIENT,
                    "user_id": client.id,
                    "name": f"Счет клиента: {client.username}",
                }
                client_account = await self.uow.accounts.add(client_account_data)
                await self.uow.commit()

            return client_account

    async def get_or_add_courier_account(self, courier_id: uuid.UUID) -> Account:
        courier: User | None = await self.user_service.get_courier(id=courier_id)
        if not courier:
            raise UserNotFoundError(user_id=courier_id)

        async with self.uow:
            courier_account: (
                Account | None
            ) = await self.uow.accounts.get_courier_account(courier_id=courier.id)

            if not courier_account:
                courier_account_data = {
                    "type": AccountType.COURIER,
                    "user_id": courier.id,
                    "name": f"Счет курьера: {courier.username}",
                }
                courier_account = await self.uow.accounts.add(courier_account_data)
                await self.uow.commit()

            return courier_account
