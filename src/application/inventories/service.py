# import uuid
# from typing import Any

# from src.application.inventories.schemas import InventoryCreate
# from src.application.inventories.uow import IInventoryUnitOfWork
# from src.core.exceptions import NotFoundError
# from src.modules.inventory.enums import InventoryType
# from src.modules.users.exceptions import UserNotFoundError


# class InventoryService:
#     def __init__(self, uow: IInventoryUnitOfWork):
#         self.uow = uow

#     async def create_inventory(self, data: InventoryCreate):
#         async with self.uow:
#             if data.user_id:
#                 user = await self.uow.users.get(id=data.user_id)
#                 if not user:
#                     raise UserNotFoundError(data.user_id)

#             inventory = await self.uow.inventories.add({
#                 "name": data.name,
#                 "type": data.type,
#                 "user_id": data.user_id,
#             })
#             await self.uow.commit()
#             return inventory

#     async def get_inventories(
#         self,
#         skip: int,
#         limit: int,
#         search: str | None = None,
#         inv_type: InventoryType | None = None,
#     ) -> dict[str, Any]:
#         """Получает список всех инвентарей с пагинацией и фильтрами."""
#         async with self.uow:
#             total, inventories = await self.uow.inventories.get_inventories_list(
#                 skip=skip, limit=limit, search=search, inv_type=inv_type
#             )
#             return {"total_count": total, "items": inventories}

#     async def get_inventory(self, inventory_id: uuid.UUID):
#         """Получает один инвентарь по ID."""
#         async with self.uow:
#             inventory = await self.uow.inventories.get(id=inventory_id)
#             if not inventory:
#                 raise NotFoundError(
#                     message=f"Инвентарь с ID {inventory_id} не найден.",
#                     error_code="INVENTORY_NOT_FOUND",
#                 )
#             return inventory

#     async def update_inventory(
#         self, inventory_id: uuid.UUID, data: InventoryUpdateDTO
#     ) -> dict[str, Any]:
#         """Обновляет данные инвентаря (название или ответственного пользователя)."""
#         async with self.uow:
#             inventory = await self.uow.inventories.get_for_update(id=inventory_id)
#             if not inventory:
#                 raise NotFoundError(
#                     message=f"Инвентарь с ID {inventory_id} не найден.",
#                     error_code="INVENTORY_NOT_FOUND",
#                 )

#             # Обновляем только те поля, которые были переданы
#             update_data = data.model_dump(exclude_unset=True)

#             # Если меняем ответственного, проверяем его существование
#             if "user_id" in update_data and update_data["user_id"] is not None:
#                 user = await self.uow.users.get(id=update_data["user_id"])
#                 if not user:
#                     raise NotFoundError(
#                         message=f"Пользователь с ID {update_data['user_id']} не найден.",
#                         error_code="USER_NOT_FOUND",
#                     )

#             updated_inventory = await self.uow.inventories.update(
#                 id=inventory_id, data=update_data
#             )
#             await self.uow.commit()

#             return updated_inventory

#     async def delete_inventory(self, inventory_id: uuid.UUID) -> None:
#         """Удаляет инвентарь (только если на нем нет остатков и движений!)."""
#         async with self.uow:
#             inventory = await self.uow.inventories.get(id=inventory_id)
#             if not inventory:
#                 raise NotFoundError(
#                     message=f"Инвентарь с ID {inventory_id} не найден.",
#                     error_code="INVENTORY_NOT_FOUND",
#                 )

#             # ОПЦИОНАЛЬНО: Защита от удаления склада, по которому были движения
#             # Это крайне важно для сохранения финансовой целостности (Леджера).
#             # balances = await self.uow.stock_transactions.get_balances(inventory_id=inventory_id)
#             # if balances:
#             #     raise BadRequestError(
#             #         message="Нельзя удалить склад, на котором есть остатки.",
#             #         error_code="INVENTORY_NOT_EMPTY"
#             #     )

#             await self.uow.inventories.delete(id=inventory_id)
#             await self.uow.commit()

#     # Твой существующий метод:
#     # async def get_inventory_with_balances(self, inventory_id: uuid.UUID) -> dict[str, Any]:
