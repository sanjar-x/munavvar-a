from uuid import UUID

from sqlalchemy import func, select

from src.common.repository import BaseRepository
from src.modules.users.models import AuthProvider, Identity, Role, User


class IdentityRepository(BaseRepository[Identity]):
    def __init__(self, session):
        super().__init__(model=Identity, session=session)


class UserRepository(BaseRepository[User]):
    def __init__(self, session):
        super().__init__(model=User, session=session)

    # --- МЕТОДЫ СОЗДАНИЯ (Семантический сахар) ---

    async def add_with_role(self, role: Role, **kwargs) -> User:
        return await self.add({**kwargs, "role": role})

    async def add_accountant(self, **kwargs) -> User:
        return await self.add_with_role(role=Role.ACCOUNTANT, **kwargs)

    async def add_storekeeper(self, **kwargs) -> User:
        return await self.add_with_role(role=Role.STOREKEEPER, **kwargs)

    async def add_cashier(self, **kwargs) -> User:
        return await self.add_with_role(role=Role.CASHIER, **kwargs)

    async def add_courier(self, **kwargs) -> User:
        return await self.add_with_role(role=Role.COURIER, **kwargs)

    async def add_b2c_client(self, **kwargs) -> User:
        return await self.add_with_role(role=Role.CLIENT_B2C, **kwargs)

    async def add_b2b_client(self, **kwargs) -> User:
        return await self.add_with_role(role=Role.CLIENT_B2B, **kwargs)

    # --- ПРИВАТНЫЕ МЕТОДЫ-ПОМОЩНИКИ (Скрывают SQL) ---

    async def _get_active_by_role_and_id(
        self, id: UUID, roles: list[Role] | Role
    ) -> User | None:
        if isinstance(roles, Role):
            roles = [roles]

        statement = select(self.model).where(
            self.model.id == id,
            self.model.role.in_(roles),
            self.model.is_active.is_(True),
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def _get_all_active_by_roles(
        self, roles: list[Role] | Role
    ) -> list[User]:
        if isinstance(roles, Role):
            roles = [roles]

        statement = select(self.model).where(
            self.model.role.in_(roles), self.model.is_active.is_(True)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_list(
        self,
        skip: int,
        limit: int,
        role: Role | None = None,
        search: str | None = None,
    ) -> tuple[int, list[User]]:
        # 1. Базовый запрос
        statement = select(self.model)

        # 2. Динамическая фильтрация
        if role:
            statement = statement.where(self.model.role == role)

        if search:
            # Поиск по ФИО без учета регистра (ILIKE)
            statement = statement.where(
                self.model.full_name.ilike(f"%{search}%")
            )

        count_statement = select(func.count()).select_from(
            statement.subquery()
        )
        total_count = await self.session.scalar(count_statement) or 0

        # 4. Применяем пагинацию и сортировку (свежие сверху)
        statement = (
            statement.order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(statement)
        items = list(result.scalars().all())

        return total_count, items

    async def get_with_identity(
        self, provider: AuthProvider, provider_identity_id: str
    ) -> tuple[User, Identity] | None:

        statement = (
            select(User, Identity)
            .join(Identity, Identity.user_id == User.id)
            .where(
                Identity.provider == provider,
                Identity.provider_identity_id == provider_identity_id,
                User.is_active.is_(True),
            )
        )
        result = await self.session.execute(statement)
        return result.first()

    async def get_system_user(self) -> User:
        statement = select(self.model).where(self.model.role == Role.SYSTEM)
        result = await self.session.execute(statement)
        return result.scalar_one()

    async def get_courier(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(id, Role.COURIER)

    async def get_client(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(
            id, [Role.CLIENT_B2B, Role.CLIENT_B2C]
        )

    async def get_cashier(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(id, Role.CASHIER)

    async def get_storekeeper(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(id, Role.STOREKEEPER)

    async def get_accountant(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(id, Role.ACCOUNTANT)

    # --- СПИСКИ ---

    async def get_couriers(self) -> list[User]:
        return await self._get_all_active_by_roles(Role.COURIER)

    async def get_clients(self) -> list[User]:
        return await self._get_all_active_by_roles(
            [Role.CLIENT_B2B, Role.CLIENT_B2C]
        )

    async def get_all_by_role(self, role: Role) -> list[User]:
        return await self._get_all_active_by_roles(role)
