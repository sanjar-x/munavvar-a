# src/modules/users/services.py
import uuid
from typing import Any

from src.common.service import BaseService
from src.core.security.password import get_password_hash
from src.modules.users.exceptions import UserAlreadyExistsError
from src.modules.users.models import AuthProvider, Role, User
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

    async def get_client(self, id: uuid.UUID) -> User | None:
        async with self.uow:
            return await self._repo.get_client(id=id)
            # Или await self.uow.users.get_client(id=id) - это одно и то же

    async def get_courier(self, id: uuid.UUID) -> User | None:
        async with self.uow:
            return await self._repo.get_courier(id=id)

    async def get_users_list(
        self, skip: int, limit: int, role: Role | None, search: str | None
    ) -> dict[str, Any]:
        async with self.uow:
            total, items = await self._repo.get_list(skip, limit, role, search)
            return {"total_count": total, "items": items}

    async def get_user_local_identity(self, identity_id: str):
        async with self.uow:
            return await self.uow.users.get_with_identity(
                provider=AuthProvider.LOCAL,
                provider_identity_id=identity_id,
            )

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
            user_data = {"full_name": schema.full_name, "role": schema.role}

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
