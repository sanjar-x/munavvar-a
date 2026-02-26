import uuid

from fastapi import HTTPException

from src.common.uow import IUnitOfWork
from src.modules.finances.enums import TransactionStatus
from src.modules.finances.models import Transaction, TransactionStatus
from src.modules.finances.services import BillingService
from src.modules.logistics.delivery.services import LogisticsService

# from src.modules.orders.exceptions import (
#     OrderNotReadyError,  # Создайте такую доменную ошибку
# )
from src.modules.orders.models import Order, OrderStatus
from src.modules.orders.schemas import OrderCreateRequest
from src.modules.users.exceptions import UserNotFoundError
from src.modules.users.models import User


class CreateOrderUseCase:
    def __init__(self, uow: IUnitOfWork):
        self.uow = uow
        self.billing_service = BillingService(uow)
        self.logistics_service = LogisticsService(uow)

    async def execute(
        self, client_id: uuid.UUID, payload: OrderCreateRequest
    ) -> uuid.UUID:
        async with self.uow:
            client: User | None = await self.uow.users.get_client(id=client_id)
            if not client:
                raise UserNotFoundError(user_id=client_id)

            order = await self.uow.orders.add(
                {
                    "client_id": client.id,
                    "payment_method": payload.payment_method,
                    "status": OrderStatus.NEW,
                    "total_amount": 0,
                }
            )

            total_amount = 0
            for item in payload.items:
                product = await self.uow.products.get_product(item.product_id)
                if not product:
                    raise ValueError(f"Товар с ID {item.product_id} не найден")

                total_amount += product.price * item.quantity

                await self.uow.items.add(
                    {
                        "order_id": order.id,
                        "product_id": product.id,
                        "quantity": item.quantity,
                        "unit_price": product.price,
                    }
                )

            order.total_amount = total_amount

            await self.billing_service.add_debt(
                client_id=client.id,
                amount=order.total_amount,
                order_id=order.id,
                reason=f"Биллинг заказа #{order.id}",
            )

            await self.uow.commit()
            return order.id


class DeliverOrderUseCase:
    def __init__(self, uow: IUnitOfWork):
        self.uow: IUnitOfWork = uow
        self.logistics_service = LogisticsService(uow)
        self.billing_service = BillingService(uow)

    async def execute(self, order_id: uuid.UUID) -> None:
        # Управляем транзакцией БД
        async with self.uow:
            # 1. ЗАЩИТА ОТ ДВОЙНОГО КЛИКА: Блокируем заказ на время выполнения
            order: Order | None = await self.uow.orders.get_with_details(
                order_id
            )

            if not order or order.status != OrderStatus.IN_TRANSIT:
                # Выбрасываем чистую доменную ошибку (без HTTP-статусов)
                raise OrderNotReadyError(  # noqa: F821  # ty:ignore[unresolved-reference]
                    f"Заказ {order_id} не найден или не готов к доставке."
                )

            # 2. ФИНАНСЫ: Проводим оплату (начисляем долг или списываем кэш)
            # Убедитесь, что process_order_payment возвращает объект Transaction
            status: TransactionStatus = (
                await self.billing_service.process_order_payment(order)
            )

            if status != TransactionStatus.PENDING:
                await self.logistics_service.deliver_order_items(
                    order=order,
                    courier_id=order.courier_id,
                    client_id=order.client_id,
                )

            # Курьер едет к следующему клиенту.
            order.status = OrderStatus.DELIVERED

            # 5. Сохраняем все изменения одним махом
            await self.uow.commit()
