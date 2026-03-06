# src/application/client/service.py
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError

from src.application.client.exceptions import (
    ClientAlreadyExistsError,
    ClientNotFoundError,
)
from src.application.client.schemas import (
    Account,
    ClientCreate,
    ClientResponse,
    InventoryCreate,
)
from src.application.client.uow import ClientUnitOfWork
from src.modules.inventory.enums import InventoryType
from src.modules.users.enums import Role


class ClientService:
    def __init__(self, uow: ClientUnitOfWork):
        self.uow = uow

    async def create_client(self, data: ClientCreate) -> ClientResponse:
        async with self.uow:
            existing_identity = await self.uow.identities.get_local_by_id(data.phone)
            if existing_identity:
                raise ClientAlreadyExistsError(phone=data.phone)

            try:
                client_data = {
                    "username": data.username,
                    "role": Role(data.role.value),
                }
                client = await self.uow.users.add(client_data)

                await self.uow.identities.add_local(
                    user_id=client.id,
                    provider_identity_id=data.phone,
                )

                await self.uow.accounts.create_client_account(
                    client_id=client.id,
                    client_name=data.username,
                )
                if data.address_name:
                    await self.uow.inventories.create_client_inventory(
                        user_id=client.id,
                        inventory_name=data.address_name,
                    )

                await self.uow.commit()
                return await self.get_client(client.id)

            except IntegrityError as e:
                await self.uow.rollback()
                if "uq_identities_provider_identity_id" in str(e.orig):
                    raise ClientAlreadyExistsError(phone=data.phone)
                raise e

    async def create_client_inventory(
        self, client_id: uuid.UUID, data: InventoryCreate
    ) -> ClientResponse:
        async with self.uow:
            user = await self.uow.users.get(id=client_id)
            if not user:
                raise ClientNotFoundError(client_id)

            await self.uow.inventories.add({
                "name": data.name,
                "type": InventoryType.CLIENT,
                "user_id": client_id,
            })
            await self.uow.commit()

        return await self.get_client(client_id)

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

    async def get_client(self, client_id: uuid.UUID) -> ClientResponse:
        async with self.uow:
            client = await self.uow.users.get_client_with_details(client_id=client_id)
            if not client:
                raise ClientNotFoundError(client_id=client_id)
            identity = await self.uow.identities.get_local_by_user(user_id=client_id)
            account = await self.uow.accounts.get_client_account(client_id=client_id)

            response = ClientResponse.model_validate(client)
            response.account = Account.model_validate(account) if account else None
            response.phone = identity.provider_identity_id if identity else None
            return response

    # async def update_client(self, client_id: uuid.UUID, data: ClientUpdate):
    #     async with self.uow:
    #         client = await self.uow.users.get_client_with_details(client_id=client_id)
    #         if not client:
    #             raise ClientNotFoundError(client_id=client_id)

    #         if data.phone:
    #             existing_identity = await self.uow.identities.get_by_provider_and_id(
    #                 provider=AuthProvider.LOCAL, provider_identity_id=data.phone
    #             )
    #             if existing_identity and existing_identity.user_id != client.id:
    #                 raise ClientAlreadyExistsError(phone=data.phone)

    #             local_identity = next(
    #                 i for i in client.identities if i.provider == AuthProvider.LOCAL
    #             )

    #             if local_identity.provider_identity_id != data.phone:
    #                 await self.uow.identities.update(
    #                     id=local_identity.id,
    #                     obj_data={"provider_identity_id": data.phone},
    #                 )

    #         user_update_data = data.model_dump(
    #             exclude_unset=True, exclude_none=True, exclude={"phone"}
    #         )

    #         if user_update_data:
    #             await self.uow.users.update(
    #                 id=client.id,
    #                 obj_data=user_update_data,
    #             )

    #         try:
    #             await self.uow.commit()
    #         except IntegrityError as e:
    #             await self.uow.rollback()
    #             if "uq_identities_provider_identity_id" in str(e.orig):
    #                 raise ClientAlreadyExistsError(phone=data.phone or "Unknown")
    #             raise e

    #     return await self.get_client(client_id=client_id)
