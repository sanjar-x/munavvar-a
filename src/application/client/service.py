# src/application/client/service.py
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError

from src.application.client.exceptions import (
    ClientAlreadyExistsError,
    ClientNotFoundError,
)
from src.application.client.schemas import ClientCreate, ClientUpdate
from src.application.client.uow import ClientUnitOfWork
from src.modules.finances.enums import AccountType
from src.modules.inventory.enums import InventoryType
from src.modules.users.models import AuthProvider


class ClientService:
    def __init__(self, uow: ClientUnitOfWork):
        self.uow = uow

    async def create_client(self, data: ClientCreate) -> dict[str, Any]:
        async with self.uow:
            existing_identity = await self.uow.identities.get_by_provider_and_id(
                provider=AuthProvider.LOCAL, provider_identity_id=data.phone
            )
            if existing_identity:
                raise ClientAlreadyExistsError(phone=data.phone)

            try:
                client = await self.uow.users.add({
                    "username": data.username,
                    "role": data.role,
                })
                await self.uow.session.flush()

                await self.uow.identities.add({
                    "user_id": client.id,
                    "provider": AuthProvider.LOCAL,
                    "provider_identity_id": data.phone,
                    "password_hash": None,
                })

                client_account = await self.uow.accounts.add({
                    "type": AccountType.CLIENT,
                    "user_id": client.id,
                    "name": f"Счет клиента: {client.username}",
                    "balance": 0,
                })

                client_inventory = await self.uow.inventories.add({
                    "user_id": client.id,
                    "type": InventoryType.CLIENT,
                    "name": data.address_name,
                })

                await self.uow.commit()

                return {
                    "id": client.id,
                    "username": client.username,
                    "phone": data.phone,
                    "account": client_account,
                    "inventory": client_inventory,
                }
            except IntegrityError as e:
                await self.uow.rollback()
                if "uq_identities_provider_identity_id" in str(e.orig):
                    raise ClientAlreadyExistsError(phone=data.phone)
                raise e

    async def get_clients(
        self, skip: int, limit: int, search: str | None = None
    ) -> dict[str, Any]:

        async with self.uow:
            total, clients = await self.uow.users.get_clients_with_details(
                skip=skip, limit=limit, search=search
            )
            clients_data = [
                {
                    "id": client.id,
                    "username": client.username,
                    "phone": client.identities[0].provider_identity_id
                    if client.identities
                    else None,
                    "is_active": client.is_active,
                    "orders": len(client.client_orders),
                    "created_at": client.created_at,
                }
                for client in clients
            ]

            return {"total_count": total, "clients": clients_data}

    async def get_client(self, client_id: uuid.UUID) -> dict[str, Any]:

        async with self.uow:
            client = await self.uow.users.get_client_with_details(client_id=client_id)
            if not client:
                raise ClientNotFoundError(client_id=client_id)

            inventories = []
            for inventory in client.inventories:
                balances = await self.uow.stock_transactions.get_balances(
                    inventory_id=inventory.id
                )
                inventories.append({"inventory": inventory, "balances": balances})

            return {
                "id": client.id,
                "username": client.username,
                "phone": client.identities[0].provider_identity_id
                if client.identities
                else None,
                "account": client.accounts[0] if client.accounts else None,
                "inventories": inventories,
                "orders": sorted(
                    client.client_orders,
                    key=lambda o: o.created_at,
                    reverse=True,
                ),
            }

    async def update_client(self, client_id: uuid.UUID, data: ClientUpdate):
        async with self.uow:
            client = await self.uow.users.get_client_with_details(client_id=client_id)
            if not client:
                raise ClientNotFoundError(client_id=client_id)

            if data.phone:
                existing_identity = await self.uow.identities.get_by_provider_and_id(
                    provider=AuthProvider.LOCAL, provider_identity_id=data.phone
                )
                if existing_identity and existing_identity.user_id != client.id:
                    raise ClientAlreadyExistsError(phone=data.phone)

                local_identity = next(
                    i for i in client.identities if i.provider == AuthProvider.LOCAL
                )

                if local_identity.provider_identity_id != data.phone:
                    await self.uow.identities.update(
                        id=local_identity.id,
                        obj_data={"provider_identity_id": data.phone},
                    )

            user_update_data = data.model_dump(
                exclude_unset=True, exclude_none=True, exclude={"phone"}
            )

            if user_update_data:
                await self.uow.users.update(
                    id=client.id,
                    obj_data=user_update_data,
                )

            try:
                await self.uow.commit()
            except IntegrityError as e:
                await self.uow.rollback()
                if "uq_identities_provider_identity_id" in str(e.orig):
                    raise ClientAlreadyExistsError(phone=data.phone or "Unknown")
                raise e

        return await self.get_client(client_id=client_id)
