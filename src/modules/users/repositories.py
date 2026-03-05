from uuid import UUID

from sqlalchemy import Sequence, func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from src.common.repository import BaseRepository
from src.infrastructure.database.models import Account, Order, OrderItem
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

        if role:
            statement = statement.where(self.model.role == role)

        if search:
            # Поиск по ФИО без учета регистра (ILIKE)
            statement = statement.where(
                self.model.username.ilike(f"%{search}%")
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

    async def get_cashier(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(id, Role.CASHIER)

    async def get_storekeeper(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(id, Role.STOREKEEPER)

    async def get_accountant(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(id, Role.ACCOUNTANT)

    # --- СПИСКИ ---

    async def get_couriers(self) -> list[User]:
        return await self._get_all_active_by_roles(Role.COURIER)

    async def get_couriers_with_details(
        self, skip: int, limit: int, search: str | None
    ) -> tuple[int, Sequence[User]]:
        """Загружает курьеров вместе с их счетами и инвентарями."""

        query = select(self.model).where(self.model.role == Role.COURIER)

        if search:
            query = query.where(self.model.username.ilike(f"%{search}%"))

        count_query = select(func.count()).select_from(query.subquery())
        total_count = await self.session.scalar(count_query) or 0

        query = query.options(
            selectinload(self.model.identities),
            selectinload(self.model.accounts),
            selectinload(self.model.inventories),
        )
        query = (
            query.order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.scalars(query)
        return total_count, result.all()

    async def add_b2c_client(self, **kwargs) -> User:
        return await self.add_with_role(role=Role.CLIENT_B2C, **kwargs)

    async def add_b2b_client(self, **kwargs) -> User:
        return await self.add_with_role(role=Role.CLIENT_B2B, **kwargs)

    async def get_client(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(
            id, [Role.CLIENT_B2B, Role.CLIENT_B2C]
        )

    async def get_clients(self) -> list[User]:
        return await self._get_all_active_by_roles(
            [Role.CLIENT_B2B, Role.CLIENT_B2C]
        )

    async def get_client_with_details(self, client_id: UUID) -> User | None:
        query = (
            select(self.model)
            .where(self.model.id == client_id, self.model.is_active.is_(True))
            .options(
                selectinload(self.model.identities),
                selectinload(self.model.accounts).selectinload(
                    Account.outgoing_transactions
                ),
                selectinload(self.model.inventories),
                selectinload(self.model.client_orders).options(
                    joinedload(Order.client_inventory),
                    joinedload(Order.courier),
                    selectinload(Order.items).joinedload(OrderItem.product),
                ),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_clients_with_details(
        self, skip: int, limit: int, search: str | None = None
    ) -> tuple[int, Sequence[User]]:
        query = select(self.model).where(
            self.model.is_active.is_(True),
            self.model.role.in_([Role.CLIENT_B2C, Role.CLIENT_B2B]),
        )
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    self.model.username.ilike(search_pattern),
                    self.model.identities.any(
                        Identity.provider_identity_id.ilike(search_pattern)
                    ),
                )
            )

        count_query = select(func.count()).select_from(query.subquery())
        total_count = await self.session.scalar(count_query) or 0

        if total_count == 0:
            return 0, []
        query = (
            query.options(
                selectinload(self.model.identities),
                selectinload(self.model.client_orders),
            )
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.scalars(query)
        return total_count, result.all()

    async def get_all_by_role(self, role: Role) -> list[User]:
        return await self._get_all_active_by_roles(role)
