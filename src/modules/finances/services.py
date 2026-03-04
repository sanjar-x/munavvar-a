import uuid

from src.modules.finances.models import (
    Account,
    AccountType,
    Transaction,
    TransactionStatus,
)
from src.modules.finances.uow import FinancesUnitOfWork
from src.modules.orders.models import Order, PaymentMethod
from src.modules.users.exceptions import UserNotFoundError
from src.modules.users.models import User
from src.modules.users.services import UserService


class BillingService:
    def __init__(self, uow: FinancesUnitOfWork, user_service: UserService):
        self.uow: FinancesUnitOfWork = uow
        self.user_service: UserService = user_service

    async def get_or_add_client_account(self, client_id: uuid.UUID) -> Account:
        client: User | None = await self.user_service.get_client(id=client_id)
        if not client:
            raise UserNotFoundError(user_id=client_id)

        client_account: (
            Account | None
        ) = await self.uow.accounts.get_client_account(client_id=client.id)

        if not client_account:
            client_account_data = {
                "type": AccountType.CLIENT,
                "user_id": client.id,
                "name": f"Счет клиента: {client.username}",
            }
            client_account = await self.uow.accounts.add(client_account_data)

        return client_account

    async def get_or_add_courier_account(
        self, courier_id: uuid.UUID
    ) -> Account:
        courier: User | None = await self.user_service.get_courier(
            id=courier_id
        )
        if not courier:
            raise UserNotFoundError(user_id=courier_id)

        courier_account: (
            Account | None
        ) = await self.uow.accounts.get_courier_account(courier_id=courier.id)

        if not courier_account:
            courier_account_data = {
                "type": AccountType.COURIER,
                "user_id": courier.id,
                "name": f"Счет курьера: {courier.username}",
            }
            courier_account = await self.uow.accounts.add(courier_account_data)

        return courier_account

    async def transfer(
        self,
        from_account_id: uuid.UUID,
        to_account_id: uuid.UUID,
        amount: int,
        order_id: uuid.UUID | None = None,
        reason: str = "Перевод средств",
        status: TransactionStatus = TransactionStatus.COMPLETED,
    ) -> Transaction:
        if amount <= 0:
            raise ValueError("Сумма перевода должна быть больше нуля.")
        if from_account_id == to_account_id:
            raise ValueError("Нельзя перевести средства на тот же самый счет.")

        accounts = await self.uow.accounts.get_many_for_update(
            [from_account_id, to_account_id]
        )

        if len(accounts) != 2:
            raise ValueError("Один или оба счета не найдены.")

        if accounts[0].id == from_account_id:
            from_account, to_account = accounts[0], accounts[1]
        else:
            from_account, to_account = accounts[1], accounts[0]

        if status == TransactionStatus.COMPLETED:
            from_account.balance -= amount
            to_account.balance += amount

        transaction_data = {
            "from_id": from_account.id,
            "to_id": to_account.id,
            "amount": amount,
            "order_id": order_id,
            "reason": reason,
            "status": status,
        }
        return await self.uow.transactions.add(transaction_data)

    async def confirm_transaction(self, transaction_id: uuid.UUID) -> None:
        transaction = await self.uow.transactions.get_for_update(
            transaction_id
        )
        if not transaction:
            raise ValueError(f"Транзакция {transaction_id} не найдена.")

        if transaction.status == TransactionStatus.COMPLETED:
            return

        if transaction.status != TransactionStatus.PENDING:
            raise ValueError(
                f"Невозможно подтвердить транзакцию  статусе {transaction.status}."
            )

        # Получаем и блокируем оба счета за 1 запрос (они уже отсортированы БД)
        accounts = await self.uow.accounts.get_many_for_update(
            [transaction.from_id, transaction.to_id]
        )

        if len(accounts) != 2:
            raise ValueError("Один или оба счета не найдены.")

        # Определяем кто отправитель, а кто получатель
        if accounts[0].id == transaction.from_id:
            from_account, to_account = accounts[0], accounts[1]
        else:
            from_account, to_account = accounts[1], accounts[0]

        from_account.balance -= transaction.amount
        to_account.balance += transaction.amount
        transaction.status = TransactionStatus.COMPLETED

    async def add_debt(
        self,
        client_id: uuid.UUID,
        amount: int,
        order_id: uuid.UUID | None = None,
        reason: str = "Начисление задолженности",
    ) -> None:

        client_account: Account = await self.get_or_add_client_account(
            client_id
        )

        system_user: User = await self.user_service.get_system_user()
        revenue_account: Account = (
            await self.uow.accounts.get_system_revenue_account(system_user.id)
        )
        await self.transfer(
            from_account_id=revenue_account.id,
            to_account_id=client_account.id,
            amount=amount,
            order_id=order_id,
            reason=reason,
        )

    async def process_order_payment(
        self,
        order: Order,
    ) -> TransactionStatus:
        client_account: Account = await self.get_or_add_client_account(
            order.client_id
        )

        reason = f"Оплата заказа #{order.id}"

        if order.payment_method == PaymentMethod.CASH:
            courier_account: Account = await self.get_or_add_courier_account(
                order.courier_id
            )
            await self.transfer(
                from_account_id=client_account.id,
                to_account_id=courier_account.id,
                amount=order.total_amount,
                order_id=order.id,
                reason=reason,
                status=TransactionStatus.COMPLETED,
            )
            return TransactionStatus.COMPLETED
        elif order.payment_method == PaymentMethod.CARD:
            system_user = await self.user_service.get_system_user()
            card_account = await self.uow.accounts.get_system_card_account(
                system_user.id
            )
            await self.transfer(
                from_account_id=client_account.id,
                to_account_id=card_account.id,
                amount=order.total_amount,
                order_id=order.id,
                reason=reason,
                status=TransactionStatus.PENDING,
            )
            return TransactionStatus.PENDING
        else:
            return TransactionStatus.COMPLETED
