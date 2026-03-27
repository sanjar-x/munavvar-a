# src/modules/users/services.py
import uuid
from typing import Any

from src.common.service import BaseService
from src.core.security.password import get_password_hash
from src.infrastructure.database.models import User
from src.modules.finances.enums import AccountType
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.users.enums import AuthProvider, Role
from src.modules.users.exceptions import UserAlreadyExistsError
from src.modules.users.repositories import UserRepository
from src.modules.users.schemas import UserAdminCreate
from src.modules.users.uow import UserUnitOfWork


class UserService(BaseService[User, UserAdminCreate, UserUnitOfWork]):
    def __init__(self, uow: UserUnitOfWork):
        super().__init__(uow=uow)

    @property
    def _repo(self) -> UserRepository:
        return self.uow.users

    async def get_system_user(self) -> User:
        async with self.uow:
            return await self._repo.get_system_user()

    async def get_courier(self, id: uuid.UUID) -> User | None:
        async with self.uow:
            return await self._repo.get_courier(id=id)

    async def get_couriers(
        self, skip: int, limit: int, search: str | None
    ) -> dict[str, Any]:
        async with self.uow:
            total, users = await self._repo.get_couriers_with_details(
                skip, limit, search
            )

            items = []
            for user in users:
                identity = user.identities[0] if user.identities else None
                account = user.accounts[0] if user.accounts else None
                inventory = user.inventories[0] if user.inventories else None

                items.append(
                    {
                        "id": user.id,
                        "username": user.username,
                        "phone": identity.provider_identity_id
                        if identity
                        else None,
                        "is_active": user.is_active,
                        "account": account,
                        "inventory": inventory,
                    }
                )

            return {"total_count": total, "couriers": items}

    async def get_user_local_identity(self, identity_id: str):
        async with self.uow:
            return await self.uow.users.get_with_identity(
                provider=AuthProvider.LOCAL,
                provider_identity_id=identity_id,
            )

    async def register_client(self, schema: UserAdminCreate) -> User:
        """Регистрация клиента с созданием счета, инвентаря и стартовой тары"""
        async with self.uow:
            # 1. Проверяем, нет ли уже такого телефона в базе
            result = await self.uow.users.get_with_identity(
                provider=AuthProvider.LOCAL,
                provider_identity_id=schema.phone,
            )

            if result:
                raise UserAlreadyExistsError(identity_id=schema.phone)

            # 2. Создаем запись User (Role.CLIENT_B2C по умолчанию, если не передано)
            role = schema.role or Role.CLIENT_B2C
            user_data = {"username": schema.username, "role": role}
            user = await self.uow.users.add(user_data)

            # 3. Создаем запись Identity (учетные данные)
            hashed_password = get_password_hash(schema.password)
            identity_data = {
                "user_id": user.id,
                "provider": AuthProvider.LOCAL,
                "provider_identity_id": schema.phone,
                "password_hash": hashed_password,
            }
            await self.uow.identities.add(identity_data)

            # 4. Создаем Счет клиента (Task 5 context)
            await self.uow.accounts.add(
                {
                    "user_id": user.id,
                    "type": AccountType.CLIENT,
                    "name": f"Лицевой счет: {user.username}",
                    "balance": 0,
                }
            )

            # 5. Создаем Инвентарь клиента (Адрес доставки)
            inventory = await self.uow.inventories.add(
                {
                    "user_id": user.id,
                    "type": InventoryType.CLIENT,
                    "name": f"Адрес: {user.username}",
                }
            )

            # 6. Начисляем стартовую тару (Task 4)
            if schema.initial_tare_quantity and schema.tare_product_id:
                # Получаем виртуальный склад поставщика
                vendor_inv = await self.uow.inventories.get_vendor_inventory()

                # Создаем и проводим StockTransfer
                transfer = await self.uow.transfers.add(
                    {
                        "from_id": vendor_inv.id,
                        "to_id": inventory.id,
                        "type": TransferType.FACTORY_RECEIPT,
                        "status": TransferStatus.COMPLETED,
                        "created_by_id": user.id,  # Условно
                        "accepted_by_id": user.id,
                    }
                )

                # Строка накладной
                await self.uow.transfer_items.add(
                    {
                        "transfer_id": transfer.id,
                        "product_id": schema.tare_product_id,
                        "quantity": schema.initial_tare_quantity,
                    }
                )

                # Фиксируем проводку в леджере
                await self.uow.transactions.add(
                    {
                        "product_id": schema.tare_product_id,
                        "transfer_id": transfer.id,
                        "from_id": vendor_inv.id,
                        "to_id": inventory.id,
                        "quantity": schema.initial_tare_quantity,
                    }
                )

            await self.uow.commit()
            return user

    async def register_local_user(self, schema: UserAdminCreate) -> User:
        """Регистрация пользователя по номеру телефона и паролю"""
        async with self.uow:
            # 1. Проверяем, нет ли уже такого телефона в базе
            result = await self.uow.users.get_with_identity(
                provider=AuthProvider.LOCAL,
                provider_identity_id=schema.phone,
            )

            if result:
                raise UserAlreadyExistsError(identity_id=schema.phone)

            # 2. Создаем запись User
            user_data = {"username": schema.username, "role": schema.role}

            # поэтому user.id сразу доступен. Явный uow.flush() здесь не нужен.
            user = await self.uow.users.add(user_data)

            # 3. Создаем запись Identity (учетные данные)
            hashed_password = get_password_hash(schema.password)
            identity_data = {
                "user_id": user.id,
                "provider": AuthProvider.LOCAL,
                "provider_identity_id": schema.phone,
                "password_hash": hashed_password,
            }
            await self.uow.identities.add(identity_data)

            # 4. Фиксируем транзакцию
            await self.uow.commit()

            return user
