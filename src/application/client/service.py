# src/application/client/service.py
import uuid
from typing import Any

from src.application.client.exceptions import ClientNotFoundError
from src.application.client.schemas import ClientCreate
from src.application.client.uow import ClientUnitOfWork
from src.modules.finances.enums import AccountType
from src.modules.inventory.enums import InventoryType
from src.modules.users.models import AuthProvider


class ClientService:
    def __init__(self, uow: ClientUnitOfWork):
        self.uow = uow

    async def create_client(self, data: ClientCreate) -> dict[str, Any]:
        """Оркестрирует создание клиента, его телефона, счета и адреса."""
        async with self.uow:
            client = await self.uow.users.add(
                {
                    "username": data.username,
                    "role": data.role,
                    "is_active": True,
                }
            )
            await self.uow.session.flush()

            await self.uow.identities.add(
                {
                    "user_id": client.id,
                    "provider": AuthProvider.LOCAL,
                    "provider_identity_id": data.phone,
                    "password_hash": None,
                }
            )

            client_account = await self.uow.accounts.add(
                {
                    "type": AccountType.CLIENT,
                    "user_id": client.id,
                    "name": f"Счет клиента: {client.username}",
                    "balance": 0,
                }
            )
            inventory = await self.uow.inventories.add(
                {
                    "user_id": client.id,
                    "type": InventoryType.CLIENT,
                    "name": data.address_name,
                }
            )

            await self.uow.commit()

            return {
                "id": client.id,
                "username": client.username,
                "phone": data.phone,
                "account": client_account,
                "inventory": inventory,
            }

    async def get_clients(
        self, skip: int, limit: int, search: str | None = None
    ) -> dict[str, Any]:

        async with self.uow:
            total, users = await self.uow.users.get_clients_with_details(
                skip=skip, limit=limit, search=search
            )

            items = []
            for user in users:
                items.append(
                    {
                        "id": user.id,
                        "username": user.username,
                        "phone": user.identities[0].provider_identity_id
                        if user.identities
                        else None,
                        "is_active": user.is_active,
                        "orders": len(user.client_orders)
                        if user.client_orders
                        else 0,
                        "created_at": user.created_at,
                    }
                )

            return {"total_count": total, "clients": items}

    async def get_client(self, client_id: uuid.UUID) -> dict[str, Any]:
        async with self.uow:
            client = await self.uow.users.get_client_with_details(
                client_id=client_id
            )
            if not client:
                raise ClientNotFoundError(client_id=client_id)

            inventories = []
            for inventory in client.inventories:
                balances = await self.uow.stock_transactions.get_balances(
                    inventory_id=inventory.id
                )
                inventories.append(
                    {
                        "inventory": inventory,
                        "balances": balances,
                    }
                )

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
