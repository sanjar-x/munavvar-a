# src/modules/inventory/shift_service.py
from src.core.config import settings
from src.modules.finances.enums import AccountType, TransactionStatus
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.inventory.schemas import CloseShiftRequest
from src.modules.inventory.uow import InventoryUnitOfWork


class ShiftService:
    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    async def close_shift(self, request: CloseShiftRequest) -> bool:
        """
        Вечернее закрытие смены:
        1. Сверка остатков (Inventory Reconciliation)
        2. Перемещение остатков на главный склад (COURIER_RETURN)
        3. Инкассация наличных (Courier Account → System Cash Account)
        4. Закрытие смены (бизнес-флаг)
        """
        async with self.uow:
            # 1. Захватываем блокировку на инвентарь курьера
            inventory = await self.uow.inventories.get_inventory_with_balances(
                request.courier_id,
                inv_type=InventoryType.COURIER,
                with_for_update=True,
            )
            if not inventory:
                # Попробуем найти по courier_id (так как это ID пользователя)
                inventory = await self.uow.inventories.get_courier_inventory(
                    request.courier_id
                )
                if not inventory:
                    raise ValueError(
                        f"Активный инвентарь для курьера {request.courier_id} не найден"
                    )

                # Повторно запрашиваем с блокировкой
                inventory = (
                    await self.uow.inventories.get_inventory_with_balances(
                        inventory.id, with_for_update=True
                    )
                )

            if not inventory:
                raise ValueError("Не удалось заблокировать инвентарь")

            # 2. Сверка остатков
            current_balances = {
                b.product_id: b.quantity for b in inventory.balances
            }
            returned_map = {
                item.product_id: item.quantity
                for item in request.returned_inventory
            }

            # Проверяем, что курьер сдает ровно столько, сколько на нем числится
            all_product_ids = set(current_balances.keys()) | set(
                returned_map.keys()
            )

            for pid in all_product_ids:
                sys_qty = current_balances.get(pid, 0)
                ret_qty = returned_map.get(pid, 0)

                if sys_qty != ret_qty:
                    raise ValueError(
                        f"Рассинхрон остатков по товару {pid}. "
                        f"В системе: {sys_qty}, сдано: {ret_qty}. "
                        "Оформите акт списания перед закрытием смены."
                    )

            # 3. Если сверка прошла успешно — перемещаем всё на главный склад
            if request.returned_inventory:
                # Получаем системный главный склад
                main_warehouse = (
                    await self.uow.inventories.get_system_inventory(
                        InventoryType.WAREHOUSE
                    )
                )

                # Создаем накладную на возврат (COURIER → WAREHOUSE)
                transfer = await self.uow.transfers.add(
                    {
                        "from_id": inventory.id,
                        "to_id": main_warehouse.id,
                        "type": TransferType.COURIER_RETURN,
                        "status": TransferStatus.COMPLETED,
                        "created_by_id": inventory.user_id,
                        "accepted_by_id": settings.SYSTEM_USER_ID,
                    }
                )

                # Создаем строки накладной и проводки в леджере
                for item in request.returned_inventory:
                    await self.uow.transfer_items.add(
                        {
                            "transfer_id": transfer.id,
                            "product_id": item.product_id,
                            "quantity": item.quantity,
                        }
                    )
                    await self.uow.transactions.add(
                        {
                            "product_id": item.product_id,
                            "transfer_id": transfer.id,
                            "from_id": inventory.id,
                            "to_id": main_warehouse.id,
                            "quantity": item.quantity,
                        }
                    )

            # 4. Инкассация: перевод наличных с кассы курьера в центральную кассу
            if request.cash_collected > 0:
                cash_amount = int(request.cash_collected)
                courier_account = (
                    await self.uow.accounts.get_user_account_by_type(
                        inventory.user_id, AccountType.COURIER
                    )
                )
                system_cash_account = (
                    await self.uow.accounts.get_system_cash_account()
                )
                await self.uow.financial_transactions.add(
                    {
                        "from_id": courier_account.id,
                        "to_id": system_cash_account.id,
                        "amount": cash_amount,
                        "status": TransactionStatus.COMPLETED,
                        "reason": "Инкассация при закрытии смены",
                    }
                )

            # 5. Закрытие смены (бизнес-флаг)
            inventory.is_active = False

            await self.uow.commit()
            return True
