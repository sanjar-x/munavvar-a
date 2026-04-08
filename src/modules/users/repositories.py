import uuid
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, insert, inspect, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.common.repository import BaseRepository
from src.infrastructure.database.models import (
    Balance,
    Identity,
    Inventory,
    Order,
    OrderItem,
    PhoneNumber,
    User,
)
from src.modules.users.enums import AuthProvider, Role
from src.modules.users.exceptions import (
    UserDeleteConflictError,
    UserNotFoundError,
    UserUpdateConflictError,
)


class PhoneNumberRepository(BaseRepository[PhoneNumber]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=PhoneNumber, session=session)

    async def get_by_phone(self, phone: str) -> PhoneNumber | None:
        query = select(self.model).where(self.model.phone == phone)
        return await self.session.scalar(query)

    async def get_by_user(self, user_id: UUID) -> Sequence[PhoneNumber]:
        query = (
            select(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.is_active.is_(True),
            )
            .order_by(self.model.created_at.asc())
        )
        result = await self.session.scalars(query)
        return result.all()

    async def count_by_user(self, user_id: UUID) -> int:
        query = (
            select(func.count())
            .select_from(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.is_active.is_(True),
            )
        )
        return await self.session.scalar(query) or 0


class IdentityRepository(BaseRepository[Identity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Identity, session=session)

    async def add_local(
        self,
        user_id: UUID,
        provider_identity_id: str,
        password_hash: str | None = None,
    ) -> Identity:
        return await self.add(
            {
                "user_id": user_id,
                "provider": AuthProvider.LOCAL,
                "provider_identity_id": provider_identity_id,
                "password_hash": password_hash,
            }
        )

    async def get_by_user_and_provider(
        self, user_id: UUID, provider: AuthProvider
    ) -> Identity:
        query = select(self.model).where(
            self.model.user_id == user_id,
            self.model.provider == provider,
        )
        result = await self.session.execute(query)
        identity = result.scalar_one_or_none()
        if identity is None:
            raise UserNotFoundError(user_id=user_id)
        return identity

    async def get_by_id_and_provider(
        self,
        provider_identity_id: str,
        provider: AuthProvider,
    ) -> Identity | None:
        query = select(self.model).where(
            self.model.provider == provider,
            self.model.provider_identity_id == provider_identity_id,
        )
        return await self.session.scalar(query)

    async def get_local_by_id(
        self, provider_identity_id: str
    ) -> Identity | None:
        return await self.get_by_id_and_provider(
            provider_identity_id=provider_identity_id,
            provider=AuthProvider.LOCAL,
        )

    async def get_local_by_user(self, user_id: UUID) -> Identity:
        return await self.get_by_user_and_provider(user_id, AuthProvider.LOCAL)

    async def get_local_by_user_or_none(
        self, user_id: UUID
    ) -> Identity | None:
        query = select(self.model).where(
            self.model.user_id == user_id,
            self.model.provider == AuthProvider.LOCAL,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class UserRepository(BaseRepository[User]):
    _insertable_keys: frozenset[str] = frozenset()
    _updatable_keys: frozenset[str] = frozenset()

    def __init__(self, session: AsyncSession):
        super().__init__(model=User, session=session)
        self._ensure_insertable_keys()
        self._ensure_updatable_keys()

    @classmethod
    def _ensure_insertable_keys(cls) -> None:
        if not cls._insertable_keys:
            mapper = inspect(subject=User).mapper
            cls._insertable_keys = frozenset(col.key for col in mapper.columns)

    @classmethod
    def _ensure_updatable_keys(cls) -> None:
        if not cls._updatable_keys:
            mapper = inspect(subject=User).mapper
            valid_columns = {col.key for col in mapper.columns}
            restricted_columns = {"id", "created_at", "updated_at"}
            cls._updatable_keys = frozenset(valid_columns - restricted_columns)

    async def add(self, obj_data: dict[str, Any]) -> User:
        insert_data = {
            k: v for k, v in obj_data.items() if k in self._insertable_keys
        }
        statement = (
            insert(self.model).values(insert_data).returning(self.model)
        )
        result = await self.session.execute(statement)
        return result.scalar_one()

    async def add_with_role(self, role: Role, **kwargs: Any) -> User:
        data = {"role": role, **kwargs}
        return await self.add(data)

    async def add_accountant(self, **kwargs: Any) -> User:
        return await self.add_with_role(role=Role.ACCOUNTANT, **kwargs)

    async def add_storekeeper(self, **kwargs: Any) -> User:
        return await self.add_with_role(role=Role.STOREKEEPER, **kwargs)

    async def add_cashier(self, **kwargs: Any) -> User:
        return await self.add_with_role(role=Role.CASHIER, **kwargs)

    async def add_courier(self, **kwargs: Any) -> User:
        return await self.add_with_role(role=Role.COURIER, **kwargs)

    async def get(
        self,
        id: uuid.UUID,
        active_only: bool = True,
        with_for_update: bool = False,
    ) -> User | None:
        query = (
            select(self.model)
            .where(self.model.id == id)
            .options(selectinload(self.model.identities))
        )
        if active_only:
            query = query.where(self.model.is_active.is_(True))
        if with_for_update:
            query = query.with_for_update()

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id(self, id: uuid.UUID) -> User | None:
        query = select(self.model).where(
            self.model.id == id, self.model.is_active.is_(True)
        )
        return await self.session.scalar(query)

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
        return await self.session.scalar(statement)

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
        statement = select(self.model).where(
            self.model.role == Role.SYSTEM, self.model.is_active.is_(True)
        )
        result = await self.session.execute(statement)
        user = result.scalar_one_or_none()
        if user is None:
            from src.core.constants import SYSTEM_USER_ID

            raise UserNotFoundError(user_id=SYSTEM_USER_ID)
        return user

    async def get_courier(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(id, Role.COURIER)

    async def get_cashier(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(id, Role.CASHIER)

    async def get_storekeeper(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(id, Role.STOREKEEPER)

    async def get_accountant(self, id: UUID) -> User | None:
        return await self._get_active_by_role_and_id(id, Role.ACCOUNTANT)

    async def get_staff_with_details(
        self,
        skip: int,
        limit: int,
        roles: Sequence[Role],
        search: str | None = None,
    ) -> tuple[int, Sequence[User]]:
        query = select(self.model).where(
            self.model.is_active.is_(True),
            self.model.role.in_(roles),
        )

        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    self.model.username.ilike(search_pattern),
                    self.model.identities.any(
                        Identity.provider_identity_id.ilike(search_pattern)
                    ),
                    self.model.phone_numbers.any(
                        PhoneNumber.phone.ilike(search_pattern)
                    ),
                )
            )

        count_query = query.with_only_columns(func.count()).order_by(None)
        total_count = await self.session.scalar(count_query) or 0

        if total_count == 0:
            return 0, []

        query = (
            query.options(
                selectinload(self.model.identities),
                selectinload(self.model.phone_numbers),
            )
            .order_by(self.model.created_at.desc(), self.model.id.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.scalars(query)
        return total_count, result.all()

    async def get_couriers_with_details(
        self, skip: int, limit: int, search: str | None = None
    ) -> tuple[int, Sequence[User]]:
        query = select(self.model).where(
            self.model.role == Role.COURIER, self.model.is_active.is_(True)
        )

        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    self.model.username.ilike(search_pattern),
                    self.model.identities.any(
                        Identity.provider_identity_id.ilike(search_pattern)
                    ),
                    self.model.phone_numbers.any(
                        PhoneNumber.phone.ilike(search_pattern)
                    ),
                )
            )
        count_query = query.with_only_columns(func.count()).order_by(None)
        total_count = await self.session.scalar(count_query) or 0

        if total_count == 0:
            return 0, []

        query = (
            query.options(
                selectinload(self.model.identities),
                selectinload(self.model.phone_numbers),
                selectinload(self.model.accounts),
                selectinload(self.model.inventories),
                selectinload(self.model.courier_orders),
            )
            .order_by(self.model.created_at.desc(), self.model.id.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.scalars(query)
        return total_count, result.all()

    async def get_courier_with_details(self, courier_id: UUID) -> User | None:
        query = (
            select(self.model)
            .where(
                self.model.id == courier_id,
                self.model.role == Role.COURIER,
                self.model.is_active.is_(True),
            )
            .options(
                selectinload(self.model.courier_orders).options(
                    joinedload(Order.client_inventory),
                    joinedload(Order.client),
                    selectinload(Order.items).joinedload(OrderItem.product),
                ),
            )
        )
        return await self.session.scalar(query)

    async def get_client_by_id(self, id: UUID) -> User | None:
        statement = select(self.model).where(
            self.model.id == id,
            self.model.role.in_([Role.CLIENT_B2B, Role.CLIENT_B2C]),
            self.model.is_active.is_(True),
        )
        return await self.session.scalar(statement)

    async def get_client_with_details(self, client_id: UUID) -> User | None:
        query = (
            select(self.model)
            .where(
                self.model.id == client_id,
                self.model.is_active.is_(True),
                self.model.role.in_([Role.CLIENT_B2B, Role.CLIENT_B2C]),
            )
            .options(
                selectinload(self.model.identities),
                selectinload(self.model.phone_numbers),
                selectinload(self.model.inventories).options(
                    selectinload(Inventory.balances).joinedload(
                        Balance.product
                    )
                ),
                selectinload(self.model.client_orders).options(
                    joinedload(Order.client_inventory),
                    joinedload(Order.courier),
                    selectinload(Order.items).joinedload(OrderItem.product),
                ),
            )
        )
        return await self.session.scalar(query)

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
                    self.model.phone_numbers.any(
                        PhoneNumber.phone.ilike(search_pattern)
                    ),
                )
            )

        count_query = query.with_only_columns(func.count()).order_by(None)
        total_count = await self.session.scalar(count_query) or 0

        if total_count == 0:
            return 0, []

        query = (
            query.options(
                selectinload(self.model.identities),
                selectinload(self.model.phone_numbers),
                selectinload(self.model.client_orders),
            )
            .order_by(self.model.created_at.desc(), self.model.id.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.scalars(query)
        return total_count, result.all()

    async def update(
        self,
        id: uuid.UUID,
        obj_data: dict[str, Any],
        active_only: bool = True,
    ) -> User:
        update_data = {
            k: v for k, v in obj_data.items() if k in self._updatable_keys
        }

        if not update_data:
            query = select(self.model).where(self.model.id == id)
            if active_only:
                query = query.where(self.model.is_active.is_(True))
            result = await self.session.execute(query)
            user = result.scalar_one_or_none()
            if user is None:
                raise UserNotFoundError(user_id=id)
            return user

        statement = update(self.model).where(self.model.id == id)
        if active_only:
            statement = statement.where(self.model.is_active.is_(True))

        statement = (
            statement.values(update_data)
            .returning(self.model)
            .execution_options(synchronize_session="fetch")
        )

        try:
            result = await self.session.execute(statement)
            return result.scalar_one()
        except IntegrityError as e:
            raise UserUpdateConflictError(
                user_id=id,
                reason="Нарушение уникальности или ограничения базы данных",
            ) from e

    async def archive(self, id: uuid.UUID) -> bool:
        statement = (
            update(self.model)
            .where(self.model.id == id, self.model.is_active.is_(True))
            .values({"is_active": False})
            .execution_options(synchronize_session="fetch")
        )
        result = await self.session.execute(statement)
        return result.rowcount > 0

    async def delete(self, id: uuid.UUID) -> bool:
        statement = (
            delete(self.model)
            .where(self.model.id == id)
            .execution_options(synchronize_session="fetch")
        )
        try:
            result = await self.session.execute(statement)
            return result.rowcount > 0

        except IntegrityError as e:
            raise UserDeleteConflictError(
                user_id=id,
                reason=(
                    "Невозможно удалить пользователя"
                    " из-за связанных финансовых или системных данных"
                ),
            ) from e
