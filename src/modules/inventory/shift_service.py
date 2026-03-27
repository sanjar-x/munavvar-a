# src/modules/inventory/shift_service.py
import uuid

from src.core.config import settings
from src.modules.finances.enums import AccountType, TransactionStatus
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.inventory.exceptions import (
    InventoryNotFoundError,
    InventoryTypeMismatchError,
    InsufficientStockError,
)
from src.modules.inventory.schemas import (
    CloseShiftRequest,
    LoadCourierTruckRequest,
    LossWriteOffRequest,
)
from src.modules.inventory.uow import InventoryUnitOfWork


class ShiftService:
    def __init__(self, uow: InventoryUnitOfWork):
        self.uow = uow

    async def load_courier_truck(
        self,
        request: LoadCourierTruckRequest,
        loaded_by_id: uuid.UUID,
    ) -> bool:
        """
        Утренняя загрузка машины курьера:
        1. Проверка остатков на складе
        2. Перемещение товаров: Склад → Машина курьера (COURIER_LOAD)
        """
        async with self.uow:
            # 1. Захватываем блокировку на склад и получаем остатки
            warehouse = await self.uow.inventories.get_inventory_with_balances(
                request.warehouse_id,
                inv_type=InventoryType.WAREHOUSE,
                with_for_update=True,
            )
            if not warehouse:
                raise InventoryNotFoundError(inventory_id=request.warehouse_id)

            # 2. Проверяем достаточность остатков на складе
            warehouse_balances = {
                b.product_id: b.quantity for b in warehouse.balances
            }
            shortages: dict[uuid.UUID, int] = {}
            for item in request.items:
                available = warehouse_balances.get(item.product_id, 0)
                if available < item.quantity:
                    shortages[item.product_id] = item.quantity - available
            if shortages:
                raise InsufficientStockError(shortages=shortages)

            # 3. Получаем инвентарь (машину) курьера
            courier_inventory = (
                await self.uow.inventories.get_inventory_with_balances(
                    request.courier_inventory_id,
                    inv_type=InventoryType.COURIER,
                )
            )
            if not courier_inventory:
                raise InventoryNotFoundError(
                    inventory_id=request.courier_inventory_id
                )

            # 4. Создаем накладную на загрузку (WAREHOUSE → COURIER)
            transfer = await self.uow.transfers.add(
                {
                    "from_id": warehouse.id,
                    "to_id": courier_inventory.id,
                    "type": TransferType.COURIER_LOAD,
                    "status": TransferStatus.COMPLETED,
                    "created_by_id": loaded_by_id,
                    "accepted_by_id": loaded_by_id,
                }
            )

            # 5. Строки накладной и проводки в леджере
            for item in request.items:
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
                        "from_id": warehouse.id,
                        "to_id": courier_inventory.id,
                        "quantity": item.quantity,
                    }
                )

            await self.uow.commit()
            return True

    async def write_off_loss(
        self,
        request: LossWriteOffRequest,
        created_by_id: uuid.UUID,
    ) -> bool:
        """
        Списание потерянного/разбитого товара (LOSS_WRITE_OFF):
        1. Проверка остатков на инвентаре-отправителе
        2. Перемещение в виртуальный склад потерь: Source → VIRTUAL_LOSS
        """
        async with self.uow:
            # 1. Захватываем блокировку на инвентарь-отправитель
            from_inventory = (
                await self.uow.inventories.get_inventory_with_balances(
                    request.from_inventory_id,
                    with_for_update=True,
                )
            )
            if not from_inventory:
                raise InventoryNotFoundError(
                    inventory_id=request.from_inventory_id
                )

            # Только WAREHOUSE или COURIER могут списывать потери
            if from_inventory.type not in (
                InventoryType.WAREHOUSE,
                InventoryType.COURIER,
            ):
                raise InventoryTypeMismatchError(
                    inventory_id=from_inventory.id,
                    expected_type="WAREHOUSE or COURIER",
                    actual_type=from_inventory.type,
                )

            # 2. Проверяем достаточность остатков
            balances = {
                b.product_id: b.quantity for b in from_inventory.balances
            }
            shortages: dict[uuid.UUID, int] = {}
            for item in request.items:
                available = balances.get(item.product_id, 0)
                if available < item.quantity:
                    shortages[item.product_id] = item.quantity - available
            if shortages:
                raise InsufficientStockError(shortages=shortages)

            # 3. Получаем виртуальный склад потерь
            loss_inventory = await self.uow.inventories.get_system_inventory(
                InventoryType.VIRTUAL_LOSS
            )

            # 4. Создаем накладную на списание
            transfer = await self.uow.transfers.add(
                {
                    "from_id": from_inventory.id,
                    "to_id": loss_inventory.id,
                    "type": TransferType.LOSS_WRITE_OFF,
                    "status": TransferStatus.COMPLETED,
                    "created_by_id": created_by_id,
                    "accepted_by_id": created_by_id,
                }
            )

            # 5. Строки накладной и проводки в леджере
            for item in request.items:
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
                        "from_id": from_inventory.id,
                        "to_id": loss_inventory.id,
                        "quantity": item.quantity,
                    }
                )

            await self.uow.commit()
            return True

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
