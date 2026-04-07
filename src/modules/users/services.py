# src/modules/users/services.py
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError

from src.common.service import BaseService
from src.core.exceptions import BadRequestError
from src.core.security.password import get_password_hash
from src.infrastructure.database.models import User
from src.modules.finances.enums import AccountType
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.users.enums import AuthProvider, Role
from src.modules.users.exceptions import (
    StaffPasswordRequiredError,
    UserAlreadyExistsError,
    UserNotFoundError,
    UserUpdateConflictError,
)
from src.modules.users.repositories import IdentityRepository, UserRepository
from src.modules.users.schemas import (
    UserAdminCreate,
    UserAdminUpdate,
    UserClientCreate,
)
from src.modules.users.uow import UserUnitOfWork

STAFF_ROLES: frozenset[Role] = frozenset(
    {
        Role.ADMIN,
        Role.ACCOUNTANT,
        Role.STOREKEEPER,
        Role.CASHIER,
        Role.COURIER,
    }
)


class UserService(BaseService[User, UserAdminCreate, UserUnitOfWork]):
    def __init__(self, uow: UserUnitOfWork):
        super().__init__(uow=uow)

    @property
    def _repo(self) -> UserRepository:
        return self.uow.users

    @property
    def _identity_repo(self) -> IdentityRepository:
        return self.uow.identities

    async def _ensure_courier_account(self, user: User) -> bool:
        if user.role != Role.COURIER:
            return False

        account = await self.uow.accounts.get_by(
            user_id=user.id,
            type=AccountType.COURIER,
        )
        if account:
            return False

        await self.uow.accounts.create_courier_account(
            courier_id=user.id,
            courier_name=user.username,
        )
        return True

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

    async def get_staff(
        self,
        skip: int,
        limit: int,
        search: str | None = None,
        roles: list[Role] | None = None,
    ) -> dict[str, Any]:
        selected_roles = roles or list(STAFF_ROLES)
        invalid_roles = [
            role.value for role in selected_roles if role not in STAFF_ROLES
        ]
        if invalid_roles:
            raise BadRequestError(
                message="Фильтр roles принимает только роли сотрудников.",
                error_code="INVALID_STAFF_ROLE_FILTER",
                details={"roles": invalid_roles},
            )

        async with self.uow:
            total, users = await self._repo.get_staff_with_details(
                skip=skip,
                limit=limit,
                roles=selected_roles,
                search=search,
            )
            return {"total_count": total, "users": list(users)}

    async def get_user_local_identity(self, identity_id: str):
        async with self.uow:
            return await self.uow.users.get_with_identity(
                provider=AuthProvider.LOCAL,
                provider_identity_id=identity_id,
            )

    async def register_client(self, schema: UserClientCreate) -> User:
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
                        "type": TransferType.INITIAL_BALANCE,
                        "status": TransferStatus.COMPLETED,
                        "created_by_id": user.id,
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
            result = await self._repo.get(user.id, active_only=False)
            if not result:
                raise UserNotFoundError(user_id=user.id)
            return result

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

            await self._ensure_courier_account(user)

            # 4. Фиксируем транзакцию
            await self.uow.commit()

            result = await self._repo.get(user.id, active_only=False)
            if not result:
                raise UserNotFoundError(user_id=user.id)
            return result

    async def update(self, id: uuid.UUID, schema: UserAdminUpdate) -> User:
        data = schema.model_dump(exclude_unset=True)
        user_data = {
            key: value
            for key, value in data.items()
            if key in {"username", "role", "is_active"}
        }
        phone = data.get("phone")
        password = data.get("password")

        async with self.uow:
            user = await self._repo.get(id=id, active_only=False)
            if not user:
                raise UserNotFoundError(user_id=id)

            local_identity = (
                await self._identity_repo.get_local_by_user_or_none(user_id=id)
            )
            next_role = user_data.get("role", user.role)

            if next_role in STAFF_ROLES:
                if local_identity is None and phone is None:
                    raise BadRequestError(
                        message=(
                            "Для локального staff-входа требуется номер телефона."
                        ),
                        error_code="STAFF_PHONE_REQUIRED",
                        details={"user_id": id, "role": next_role.value},
                    )
                if (
                    local_identity is None or not local_identity.password_hash
                ) and not password:
                    raise StaffPasswordRequiredError(
                        user_id=id,
                        role=next_role.value,
                    )

            changed = False

            if user_data:
                user = await self._repo.update(
                    id, user_data, active_only=False
                )
                changed = True

            if phone is not None or password is not None:
                identity_data: dict[str, str] = {}
                if phone is not None:
                    identity_data["provider_identity_id"] = phone
                if password is not None:
                    identity_data["password_hash"] = get_password_hash(
                        password
                    )

                try:
                    if local_identity is None:
                        if phone is None:
                            raise BadRequestError(
                                message=(
                                    "Нельзя создать локальный вход без номера телефона."
                                ),
                                error_code="PHONE_REQUIRED_FOR_LOCAL_IDENTITY",
                                details={"user_id": id},
                            )
                        local_identity = await self._identity_repo.add_local(
                            user_id=id,
                            provider_identity_id=phone,
                            password_hash=identity_data.get("password_hash"),
                        )
                    else:
                        local_identity = await self._identity_repo.update(
                            local_identity.id,
                            identity_data,
                        )
                except IntegrityError as exc:
                    raise UserUpdateConflictError(
                        user_id=id,
                        reason="Номер телефона уже используется другим user'ом.",
                    ) from exc

                changed = True

            changed = await self._ensure_courier_account(user) or changed

            if changed:
                await self.uow.commit()

            result = await self._repo.get(id, active_only=False)
            if not result:
                raise UserNotFoundError(user_id=id)
            return result

    async def delete_staff(self, id: uuid.UUID) -> None:
        async with self.uow:
            user = await self._repo.get(id=id, active_only=False)
            if not user or user.role not in STAFF_ROLES:
                raise UserNotFoundError(user_id=id)

            is_deleted = await self._repo.delete(id)
            if not is_deleted:
                raise UserNotFoundError(user_id=id)

            await self.uow.commit()
