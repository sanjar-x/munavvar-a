# src/application/order/service.py
import uuid
from collections import defaultdict
from typing import Any

from src.application.order.schemas import CartValidationResponse, OrderCreate
from src.application.order.uow import OrderUnitOfWork
from src.core.exceptions import ConflictError
from src.modules.catalog.enums import ProductType
from src.modules.finances.models import TransactionStatus
from src.modules.inventory.enums import TransferStatus, TransferType
from src.modules.orders.enums import OrderStatus, PaymentMethod
from src.modules.orders.exceptions import EmptyCartError
from src.modules.orders.models import Order


class OrderService:
    """
    Оркестратор для кросс-доменных операций по созданию и доставке заказа.
    """

    def __init__(self, uow: OrderUnitOfWork):
        self.uow = uow

    async def validate_cart(
        self, inventory_id: uuid.UUID, items: list[Any]
    ) -> CartValidationResponse:
        """
        Проверяет, достаточно ли у клиента пустой тары на балансе для оформления заказа.
        Ожидает список объектов с product_id и quantity.
        """
        if not items:
            return CartValidationResponse(
                is_valid=False,
                needs_initial_tara=False,
                missing_items=[],
                message="Корзина пуста",
            )

        aggregated_payload = defaultdict(int)
        for item in items:
            # Предполагается, что item - это объект Pydantic. Если словарь, используй item["product_id"]
            aggregated_payload[item.product_id] += item.quantity

        async with self.uow:
            product_ids = list(aggregated_payload.keys())
            products = await self.uow.products.get_multi_by_ids(product_ids)
            product_map = {p.id: p for p in products}

            explicit_items = defaultdict(int)
            required_tara = defaultdict(int)

            for pid, qty in aggregated_payload.items():
                product = product_map.get(pid)
                if not product:
                    continue

                explicit_items[pid] += qty
                if product.type == ProductType.WATER and product.returnable_item_id:
                    required_tara[product.returnable_item_id] += qty

            # Считаем дефицит: (нужно тары) минус (тара, которую клиент явно покупает в корзине)
            tara_deficit = {
                tara_id: req_qty - explicit_items.get(tara_id, 0)
                for tara_id, req_qty in required_tara.items()
                if req_qty - explicit_items.get(tara_id, 0) > 0
            }

            if not tara_deficit:
                return CartValidationResponse(
                    is_valid=True,
                    needs_initial_tara=False,
                    missing_items=[],
                    message="Корзина валидна",
                )

            tara_ids = list(tara_deficit.keys())
            balances_map = await self.uow.stock_transactions.get_balances_for_products(
                inventory_id=inventory_id,
                product_ids=tara_ids,
            )

            missing_items = []
            for tara_id, deficit in tara_deficit.items():
                current_balance = balances_map.get(tara_id, 0)
                if current_balance < deficit:
                    missing_qty = deficit - current_balance
                    tara_product = await self.uow.products.get(id=tara_id)
                    missing_items.append({
                        "product_id": str(tara_id),
                        "name": tara_product.name
                        if tara_product
                        else "Неизвестная тара",
                        "missing_quantity": missing_qty,
                    })

            if missing_items:
                return CartValidationResponse(
                    is_valid=False,
                    needs_initial_tara=True,  # Сигнал для фронтенда показать галочку
                    missing_items=missing_items,
                    message="Недостаточно пустой тары на балансе.",
                )

            return CartValidationResponse(
                is_valid=True,
                needs_initial_tara=False,
                missing_items=[],
                message="Корзина валидна",
            )

    async def create_order(self, client_id: uuid.UUID, dto: OrderCreate) -> Order:
        if not dto.items:
            raise EmptyCartError()

        aggregated_payload = defaultdict(int)
        for item in dto.items:
            aggregated_payload[item.product_id] += item.quantity

        async with self.uow:
            product_ids = list(aggregated_payload.keys())
            products = await self.uow.products.get_multi_by_ids(product_ids)
            product_map = {p.id: p for p in products}

            total_amount = 0
            order_items_data = []
            explicit_items = defaultdict(int)
            required_tara = defaultdict(int)

            for pid, qty in aggregated_payload.items():
                product = product_map.get(pid)
                if not product:
                    raise ConflictError(f"Товар {pid} не найден в каталоге.")

                total_amount += product.price * qty
                order_items_data.append({
                    "product_id": pid,
                    "quantity": qty,
                    "unit_price": product.price,
                })

                explicit_items[pid] += qty
                if product.type == ProductType.WATER and product.returnable_item_id:
                    required_tara[product.returnable_item_id] += qty

            tara_deficit = {
                tara_id: req_qty - explicit_items.get(tara_id, 0)
                for tara_id, req_qty in required_tara.items()
                if req_qty - explicit_items.get(tara_id, 0) > 0
            }

            if tara_deficit:
                tara_ids = list(tara_deficit.keys())
                balances_map = (
                    await self.uow.stock_transactions.get_balances_for_products(
                        inventory_id=dto.inventory_id,
                        product_ids=tara_ids,
                    )
                )

                missing_tara_to_add = []

                for tara_id, deficit in tara_deficit.items():
                    current_balance = balances_map.get(tara_id, 0)
                    if current_balance < deficit:
                        missing_qty = deficit - current_balance

                        if dto.is_initial_tara:
                            missing_tara_to_add.append({
                                "product_id": tara_id,
                                "quantity": missing_qty,
                            })
                        else:
                            raise ConflictError(
                                message=f"Недостаточно пустой тары для обмена. "
                                f"Не хватает {missing_qty} шт. "
                                f"Оприходуйте тару или добавьте пустую тару в корзину."
                            )

                if missing_tara_to_add:
                    init_transfer = await self.uow.stock_transfers.add({
                        "from_id": None,
                        "to_id": dto.inventory_id,
                        "created_by_id": client_id,
                        "type": TransferType.INVENTORY_FINDING,
                        "status": TransferStatus.COMPLETED,
                    })

                    init_transactions = [
                        {
                            "transfer_id": init_transfer.id,
                            "product_id": item["product_id"],
                            "quantity": item["quantity"],
                            "from_id": None,
                            "to_id": dto.inventory_id,
                        }
                        for item in missing_tara_to_add
                    ]
                    await self.uow.stock_transactions.add_many(init_transactions)

                    # Принудительно сбрасываем сессию (flush), чтобы балансы стали актуальными до коммита
                    await self.uow.session.flush()

            new_order = await self.uow.orders.add({
                "client_id": client_id,
                "client_inventory_id": dto.inventory_id,
                "payment_method": dto.payment_method,
                "status": OrderStatus.NEW,
                "total_amount": total_amount,
            })

            for item_data in order_items_data:
                item_data["order_id"] = new_order.id
            await self.uow.order_items.add_many(order_items_data)

            await self.uow.commit()
            return new_order

    async def delivery(
        self,
        order_id: uuid.UUID,
        courier_id: uuid.UUID,
        actual_returned_tara: dict[uuid.UUID, int] | None = None,
    ) -> None:
        actual_returned_tara = actual_returned_tara or {}

        async with self.uow:
            order = await self.uow.orders.get_with_details(
                order_id, with_for_update=True
            )
            if not order or order.status != OrderStatus.ARRIVED:
                raise ConflictError("Заказ не найден или еще не прибыл к клиенту")

            financial_transactions: list[dict[str, Any]] = []

            client_account = await self.uow.accounts.get_client_account(order.client_id)
            if not client_account:
                return
            system_user = await self.uow.users.get_system_user()
            revenue_account = await self.uow.accounts.get_system_revenue_account()

            client_account.balance += order.total_amount

            financial_transactions.append({
                "from_id": revenue_account.id,
                "to_id": client_account.id,
                "amount": order.total_amount,
                "order_id": order.id,
                "status": TransactionStatus.COMPLETED,
                "reason": "Задолженность за заказ",
            })

            if order.payment_method == PaymentMethod.CASH:
                courier_account = await self.uow.accounts.get_courier_account(
                    courier_id
                )
                if not courier_account:
                    return
                client_account.balance -= order.total_amount
                courier_account.balance += order.total_amount

                financial_transactions.append({
                    "from_id": client_account.id,
                    "to_id": courier_account.id,
                    "amount": order.total_amount,
                    "order_id": order.id,
                    "status": TransactionStatus.COMPLETED,
                    "reason": "Оплата наличными курьеру",
                })

            elif order.payment_method == PaymentMethod.CARD:
                card_account = await self.uow.accounts.get_system_card_account()
                financial_transactions.append({
                    "from_id": client_account.id,
                    "to_id": card_account.id,
                    "amount": order.total_amount,
                    "order_id": order.id,
                    "status": TransactionStatus.PENDING,
                    "reason": "Перевод на карту",
                })

            if financial_transactions:
                await self.uow.transactions.add_many(financial_transactions)

            # --- Блок Инвентаря ---
            courier_inv = await self.uow.inventories.get_courier_inventory(courier_id)
            if not courier_inv:
                raise ConflictError("У курьера нет активной машины")

            transfer = await self.uow.stock_transfers.add({
                "from_id": courier_inv.id,
                "to_id": order.client_inventory_id,
                "created_by_id": courier_id,
                "order_id": order.id,
                "type": TransferType.CLIENT_DELIVERY,
                "status": TransferStatus.COMPLETED,
            })

            explicit_items = defaultdict(int)
            required_tara = defaultdict(int)

            for item in order.items:
                explicit_items[item.product_id] += item.quantity
                if (
                    item.product.type == ProductType.WATER
                    and item.product.returnable_item_id
                ):
                    required_tara[item.product.returnable_item_id] += item.quantity

            stock_transactions = []

            # Товары к клиенту
            for pid in explicit_items.keys() | required_tara.keys():
                qty = max(explicit_items[pid], required_tara[pid])
                if qty > 0:
                    stock_transactions.append({
                        "transfer_id": transfer.id,
                        "product_id": pid,
                        "quantity": qty,
                        "from_id": courier_inv.id,
                        "to_id": order.client_inventory_id,
                    })

            # Возврат от клиента
            for pid in required_tara.keys() | actual_returned_tara.keys():
                qty = actual_returned_tara.get(
                    pid, max(0, required_tara[pid] - explicit_items[pid])
                )
                if qty > 0:
                    stock_transactions.append({
                        "transfer_id": transfer.id,
                        "product_id": pid,
                        "quantity": qty,
                        "from_id": order.client_inventory_id,
                        "to_id": courier_inv.id,
                    })

            if stock_transactions:
                await self.uow.stock_transactions.add_many(stock_transactions)

            await self.uow.orders.update_status(order.id, OrderStatus.DELIVERED)
            await self.uow.commit()
