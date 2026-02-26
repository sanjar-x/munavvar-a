# src/modules/users/services.py
from typing import Any

from src.common.service import BaseService
from src.common.uow import IUnitOfWork
from src.core.security.password import get_password_hash
from src.modules.users.exceptions import UserAlreadyExistsError
from src.modules.users.models import AuthProvider, Role, User
from src.modules.users.repositories import UserRepository
from src.modules.users.schemas import UserAdminCreate


class UserService(BaseService[User, UserAdminCreate]):
    def __init__(self, uow: IUnitOfWork):
        super().__init__(uow=uow, repo_name="users")

    # Переопределяем свойство _repo, сужая тип до UserRepository!
    @property
    def _repo(self) -> UserRepository:
        # У IUnitOfWork должно быть прописано свойство .users: UserRepository
        return self.uow.users

    async def add(self, schema: UserAdminCreate) -> User:
        raise NotImplementedError()

    async def get_users_list(
        self, skip: int, limit: int, role: Role | None, search: str | None
    ) -> dict[str, Any]:
        async with self.uow:
            total, items = await self._repo.get_list(skip, limit, role, search)
            return {"total_count": total, "items": items}

    async def register_local_user(self, schema: UserAdminCreate) -> User:
        """Регистрация пользователя по номеру телефона и паролю"""
        async with self.uow:
            # Ищем, нет ли уже такого телефона в базе
            result = await self.uow.users.get_with_identity(
                provider=AuthProvider.LOCAL,
                provider_identity_id=schema.phone,
            )

            # Если result не None, значит пользователь существует
            if result:
                raise UserAlreadyExistsError(identity_id=schema.phone)

            # --- Продолжение нормального флоу ---
            user_data = {"full_name": schema.full_name, "role": schema.role}

            user = await self.uow.users.add(user_data)
            await self.uow.flush()

            hashed_password = get_password_hash(schema.password)
            identity_data = {
                "user_id": user.id,
                "provider": AuthProvider.LOCAL,
                "provider_identity_id": schema.phone,
                "password_hash": hashed_password,
            }
            await self.uow.identities.add(identity_data)

            await self.uow.commit()

            return user
