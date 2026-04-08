# src/application/client/service.py
import uuid
from typing import Any

from src.application.client.exceptions import (
    ClientAlreadyExistsError,
    ClientNotFoundError,
)
from src.application.client.schemas import (
    Account,
    ClientCreate,
    ClientOnboardingRequest,
    ClientResponse,
    ContractSummary,
    InventoryCreate,
    PhoneNumberShort,
)
from src.application.client.uow import ClientUnitOfWork
from src.infrastructure.database.models import User
from src.modules.catalog.public import CatalogService
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.orders.enums import OrderStatus
from src.modules.orders.exceptions import (
    ProductsUnavailableError,
)
from src.modules.users.enums import Role


class ClientService:
    def __init__(self, uow: ClientUnitOfWork, catalog_service: CatalogService):
        self.uow = uow
        self.catalog_service = catalog_service

    async def create_client(self, data: ClientCreate) -> ClientResponse:
        async with self.uow:
            existing_identity = await self.uow.identities.get_local_by_id(
                data.phone
            )
            if existing_identity:
                raise ClientAlreadyExistsError(phone=data.phone)

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
            return await self.get_client(client_id=client.id)

    async def create_client_inventory(
        self, client_id: uuid.UUID, data: InventoryCreate
    ) -> ClientResponse:
        async with self.uow:
            client: User | None = await self.uow.users.get_by_id(id=client_id)
            if not client:
                raise ClientNotFoundError(client_id)

            await self.uow.inventories.add(
                {
                    "name": data.name,
                    "type": InventoryType.CLIENT,
                    "user_id": client.id,
                }
            )
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
                    "role": client.role,
                    "phone": client.identities[0].provider_identity_id
                    if client.identities
                    else None,
                    "additional_phones": [
                        PhoneNumberShort.model_validate(p)
                        for p in (client.phone_numbers or [])
                    ],
                    "is_active": client.is_active,
                    "orders": len(client.client_orders),
                    "created_at": client.created_at,
                }
                for client in clients
            ]

            return {"total_count": total, "clients": clients_data}

    async def get_client(self, client_id: uuid.UUID) -> ClientResponse:
        async with self.uow:
            client = await self.uow.users.get_client_with_details(
                client_id=client_id
            )
            if not client:
                raise ClientNotFoundError(client_id=client_id)
            identity = await self.uow.identities.get_local_by_user(
                user_id=client_id
            )
            account = await self.uow.accounts.get_client_account(
                client_id=client_id
            )
            contracts = await self.uow.contracts.get_multi(client_id=client_id)

            response = ClientResponse.model_validate(client)
            response.account = (
                Account.model_validate(account) if account else None
            )
            response.phone = (
                identity.provider_identity_id if identity else None
            )
            phones = await self.uow.phone_numbers.get_by_user(
                user_id=client_id
            )
            response.additional_phones = [
                PhoneNumberShort.model_validate(p) for p in phones
            ]
            response.contracts = [
                ContractSummary.model_validate(c) for c in contracts
            ]
            return response

    async def onboard_client_with_balance(
        self, data: ClientOnboardingRequest, creator_id: uuid.UUID
    ) -> ClientResponse:
        """
        Единое окно: Создание клиента + Оприходование тары
        + (опционально) Заказ.
        """
        async with self.uow:
            # 1. Проверка дубликата телефона (Identity)
            existing_identity = await self.uow.identities.get_local_by_id(
                data.phone
            )
            if existing_identity:
                raise ClientAlreadyExistsError(phone=data.phone)

            # 2. Создание User (Role: CLIENT)
            user_data = {
                "username": data.username,
                "role": Role(data.role.value),
            }
            client = await self.uow.users.add(user_data)

            # 3. Создание Identity
            await self.uow.identities.add_local(
                user_id=client.id,
                provider_identity_id=data.phone,
            )

            # 4. Создание Финансового счета
            await self.uow.accounts.create_client_account(
                client_id=client.id,
                client_name=data.username,
            )

            # 5. Создание Склада (Inventory)
            client_inventory = (
                await self.uow.inventories.create_client_inventory(
                    user_id=client.id,
                    inventory_name=data.address_name,
                )
            )

            # 6. Оприходование начальных остатков (INITIAL_BALANCE)
            if (
                data.initial_balance_quantity > 0
                and data.initial_balance_product_id
            ):
                vendor_inv = await self.uow.inventories.get_vendor_inventory()

                # Создаем завершенную накладную
                transfer = await self.uow.transfers.add(
                    {
                        "from_id": vendor_inv.id,
                        "to_id": client_inventory.id,
                        "type": TransferType.INITIAL_BALANCE,
                        "status": TransferStatus.COMPLETED,
                        "created_by_id": creator_id,
                        "accepted_by_id": creator_id,
                    }
                )

                # Добавляем строку в накладную
                await self.uow.transfer_items.add(
                    {
                        "transfer_id": transfer.id,
                        "product_id": data.initial_balance_product_id,
                        "quantity": data.initial_balance_quantity,
                    }
                )

                # Генерируем транзакцию для леджера
                await self.uow.stock_transactions.add(
                    {
                        "product_id": data.initial_balance_product_id,
                        "transfer_id": transfer.id,
                        "from_id": vendor_inv.id,
                        "to_id": client_inventory.id,
                        "quantity": data.initial_balance_quantity,
                    }
                )

            # 7. Создание опционального Первого заказа
            if data.order:
                product_ids = [item.product_id for item in data.order.items]
                products = await self.catalog_service.get_by_ids(product_ids)
                price_map = {p.id: p.price for p in products}

                missing_ids = [
                    pid for pid in product_ids if pid not in price_map
                ]
                if missing_ids:
                    raise ProductsUnavailableError(
                        missing_product_ids=missing_ids
                    )

                total_amount = 0
                for item in data.order.items:
                    price = price_map.get(item.product_id, 0)
                    total_amount += price * item.quantity

                order = await self.uow.orders.add(
                    {
                        "client_id": client.id,
                        "client_inventory_id": client_inventory.id,
                        "payment_method": data.order.payment_method,
                        "status": OrderStatus.NEW,
                        "total_amount": total_amount,
                    }
                )

                for item in data.order.items:
                    await self.uow.order_items.add(
                        {
                            "order_id": order.id,
                            "product_id": item.product_id,
                            "quantity": item.quantity,
                            "unit_price": price_map.get(item.product_id, 0),
                        }
                    )

            await self.uow.commit()

        return await self.get_client(client_id=client.id)
