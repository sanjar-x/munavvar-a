# src/modules/users/uow.py

from src.common.uow import IUnitOfWork
from src.infrastructure.database.uow import BaseSQLAlchemyUoW
from src.modules.users.repositories import IdentityRepository, UserRepository


# 1. Доменный интерфейс (Абстракция для сервисов)
class IUserUnitOfWork(IUnitOfWork):
    users: UserRepository
    identity: IdentityRepository


# 2. Доменная реализация (Связывает инфраструктуру и домен)
class UserUnitOfWork(BaseSQLAlchemyUoW, IUserUnitOfWork):
    async def __aenter__(self) -> "UserUnitOfWork":
        await super().__aenter__()

        self.users = UserRepository(session=self.session)
        self.identities = IdentityRepository(session=self.session)

        return self
