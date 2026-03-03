# src/application/delivery/service.py
import uuid
from collections import defaultdict

from src.application.delivery.uow import IDeliveryUnitOfWork
from src.core.exceptions import ConflictError
from src.modules.catalog.enums import ProductType
from src.modules.finances.models import TransactionStatus
from src.modules.inventory.enums import TransferStatus, TransferType
from src.modules.orders.enums import OrderStatus, PaymentMethod


class DeliveryService:
    """Оркестратор для кросс-доменных операций по доставке."""

    def __init__(self, uow: IDeliveryUnitOfWork):
        self.uow = uow

    async def delivery(
        self,
        order_id: uuid.UUID,
        courier_id: uuid.UUID,
        actual_returned_tara: dict[uuid.UUID, int] | None = None,
    ) -> None:
        """
        Завершение доставки (Шаг 4).
        """
        actual_returned_tara = actual_returned_tara or {}

        async with self.uow:
            order = await self.uow.orders.get_with_details(
                order_id, with_for_update=True
            )
            if not order or order.status != OrderStatus.ARRIVED:
                raise ConflictError(
                    "Заказ не найден или еще не прибыл к клиенту"
                )
            client_account = await self.uow.accounts.get_client_account(
                order.client_id
            )

            system_user = await self.uow.users.get_system_user()
            revenue_account = (
                await self.uow.accounts.get_system_revenue_account(
                    system_user.id
                )
            )
            await self.uow.finances.add(
                {
                    "from_id": revenue_account.id,
                    "to_id": client_account.id,
                    "amount": order.total_amount,
                    "order_id": order.id,
                    "status": TransactionStatus.COMPLETED,
                    "reason": "Задолжность за заказ",
                }
            )
            client_account.balance += order.total_amount

            if order.payment_method == PaymentMethod.CASH:
                courier_account = await self.uow.accounts.get_courier_account(
                    courier_id
                )

                client_account.balance -= order.total_amount
                courier_account.balance += order.total_amount

                await self.uow.finances.add(
                    {
                        "from_id": client_account.id,
                        "to_id": courier_account.id,
                        "amount": order.total_amount,
                        "order_id": order.id,
                        "status": TransactionStatus.COMPLETED,
                        "reason": "Оплата наличными курьеру",
                    }
                )

            elif order.payment_method == PaymentMethod.CARD:
                card_account = await self.uow.accounts.get_system_card_account(
                    system_user.id
                )
                await self.uow.finances.add(
                    {
                        "from_id": client_account.id,
                        "to_id": card_account.id,
                        "amount": order.total_amount,
                        "order_id": order.id,
                        "status": TransactionStatus.PENDING,
                        "reason": "Перевод на карту (ожидает подтверждения)",
                    }
                )

            courier_inv = await self.uow.inventories.get_courier_inventory(
                courier_id
            )
            if not courier_inv:
                raise ConflictError("У курьера нет активной машины")

            client_inv_id = order.client_inventory_id

            transfer = await self.uow.stock_transfers.add(
                {
                    "from_id": courier_inv.id,
                    "to_id": client_inv_id,
                    "created_by_id": courier_id,
                    "order_id": order.id,
                    "type": TransferType.CLIENT_DELIVERY,
                    "status": TransferStatus.COMPLETED,
                }
            )

            explicit_items = defaultdict(int)
            required_tara = defaultdict(int)

            for item in order.items:
                explicit_items[item.product_id] += item.quantity
                if (
                    item.product.type == ProductType.WATER
                    and item.product.returnable_item_id
                ):
                    required_tara[item.product.returnable_item_id] += (
                        item.quantity
                    )

            transactions_data = []

            for pid in explicit_items.keys() | required_tara.keys():
                qty = max(explicit_items[pid], required_tara[pid])
                if qty > 0:
                    transactions_data.append(
                        {
                            "transfer_id": transfer.id,
                            "product_id": pid,
                            "quantity": qty,
                            "from_id": courier_inv.id,
                            "to_id": client_inv_id,
                        }
                    )

            for pid in required_tara.keys() | actual_returned_tara.keys():
                qty = actual_returned_tara.get(
                    pid, max(0, required_tara[pid] - explicit_items[pid])
                )
                if qty > 0:
                    transactions_data.append(
                        {
                            "transfer_id": transfer.id,
                            "product_id": pid,
                            "quantity": qty,
                            "from_id": client_inv_id,
                            "to_id": courier_inv.id,
                        }
                    )

            if transactions_data:
                await self.uow.stock_transactions.add_many(transactions_data)

            await self.uow.orders.update_status(
                order.id, OrderStatus.DELIVERED
            )

            await self.uow.commit()
