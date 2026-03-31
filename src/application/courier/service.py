# src/application/courier/service.py
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError

from src.application.courier.exceptions import (
    CourierAlreadyExistsError,
    CourierNotFoundError,
)
from src.application.courier.schemas import CourierCreate
from src.application.courier.uow import CourierUnitOfWork
from src.application.inventories.schemas import InventoryCreate
from src.core.exceptions import ConflictError
from src.core.security.password import get_password_hash
from src.modules.inventory.enums import InventoryType
from src.modules.users.enums import AuthProvider, Role


class CourierService:
    def __init__(self, uow: CourierUnitOfWork):
        self.uow = uow

    async def create_courier(self, data: CourierCreate) -> dict[str, Any]:
        async with self.uow:
            existing_identity = await self.uow.identities.get_local_by_id(
                provider_identity_id=data.phone
            )
            if existing_identity:
                raise CourierAlreadyExistsError(phone=data.phone)

            try:
                courier = await self.uow.users.add(
                    {
                        "username": data.username,
                        "role": Role.COURIER,
                        "is_active": True,
                    }
                )
                await self.uow.session.flush()
                hashed_pwd = get_password_hash(data.password)
                await self.uow.identities.add(
                    {
                        "user_id": courier.id,
                        "provider": AuthProvider.LOCAL,
                        "provider_identity_id": data.phone,
                        "password_hash": hashed_pwd,
                    }
                )

                await self.uow.accounts.create_courier_account(
                    courier_id=courier.id,
                    courier_name=courier.username,
                )

                await self.uow.commit()

                return await self.get_courier(courier_id=courier.id)
            except IntegrityError as e:
                await self.uow.rollback()
                if "uq_identities_provider_identity_id" in str(e.orig):
                    raise CourierAlreadyExistsError(phone=data.phone)
                raise e

    async def create_courier_inventory(
        self, courier_id: uuid.UUID, data: InventoryCreate
    ) -> dict[str, Any]:
        async with self.uow:
            courier = await self.uow.users.get_by_id(id=courier_id)
            if not courier:
                raise CourierNotFoundError(courier_id=courier_id)

            try:
                await self.uow.inventories.add(
                    {
                        "name": data.name,
                        "type": InventoryType.COURIER,
                        "user_id": courier_id,
                    }
                )
                await self.uow.commit()
            except IntegrityError as e:
                await self.uow.rollback()
                if "uq_user_single_courier_inventory" in str(e.orig):
                    raise ConflictError(
                        message="У данного курьера уже зарегистрирована машина.",
                        error_code="COURIER_INVENTORY_ALREADY_EXISTS",
                    )
                raise e

        return await self.get_courier(courier_id=courier_id)

    async def get_couriers(
        self, skip: int, limit: int, search: str | None = None
    ) -> dict[str, Any]:

        async with self.uow:
            total, couriers = await self.uow.users.get_couriers_with_details(
                skip=skip, limit=limit, search=search
            )

            couriers_data = [
                {
                    "id": courier.id,
                    "username": courier.username,
                    "phone": courier.identities[0].provider_identity_id
                    if courier.identities
                    else None,
                    "account": courier.accounts[0]
                    if courier.accounts
                    else None,
                    "inventory": courier.inventories[0]
                    if courier.inventories
                    else None,
                    "is_active": courier.is_active,
                    "orders": len(courier.courier_orders)
                    if hasattr(courier, "courier_orders")
                    else 0,
                    "created_at": courier.created_at,
                }
                for courier in couriers
            ]

            return {"total_count": total, "couriers": couriers_data}

    async def get_courier(self, courier_id: uuid.UUID) -> dict[str, Any]:
        async with self.uow:
            courier = await self.uow.users.get_courier_with_details(
                courier_id=courier_id
            )
            if not courier:
                raise CourierNotFoundError(courier_id=courier_id)

            identity = await self.uow.identities.get_local_by_user(courier.id)
            account = await self.uow.accounts.get_courier_account(courier.id)
            inventory = await self.uow.inventories.get_courier_inventory(
                courier_id
            )

            return {
                "id": courier.id,
                "username": courier.username,
                "phone": identity.provider_identity_id,
                "is_active": courier.is_active,
                "account": account,
                "inventory": inventory,
                "orders": courier.courier_orders,
                "created_at": courier.created_at,
                "updated_at": courier.updated_at,
            }
