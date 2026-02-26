# src/modules/orders/repository.py
import uuid
from typing import Any

from sqlalchemy import Result, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.common.repository import BaseRepository
from src.modules.logistics.warehouse.models import Transfer, TransferItem


class TransferRepository(BaseRepository[Transfer]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Transfer, session=session)

    async def get_with_items(self, transfer_id: uuid.UUID) -> Transfer | None:
        statement = (
            select(Transfer)
            .where(Transfer.id == transfer_id, Transfer.is_active.is_(True))
            .options(
                selectinload(Transfer.items).joinedload(TransferItem.product)
            )
        )
        result: Result = await self.session.execute(statement=statement)
        return result.scalar_one_or_none()


class TransferItemRepository(BaseRepository[TransferItem]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=TransferItem, session=session)

    async def add_multi(self, items_data: list[dict[str, Any]]) -> None:
        """BULK INSERT: Вставляет все позиции корзины одним SQL-запросом"""
        if not items_data:
            return
        await self.session.execute(insert(self.model).values(items_data))
