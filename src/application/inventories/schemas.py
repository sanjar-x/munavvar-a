import uuid

from pydantic import BaseModel, Field

from src.modules.inventory.enums import InventoryType


class InventoryCreate(BaseModel):
    name: str = Field(..., description="Название склада/машины")
    type: InventoryType = Field(default=InventoryType.CLIENT)
    user_id: uuid.UUID = Field(description="ID материально ответственного")


class InventoryUpdate(BaseModel):
    name: str | None = None
    user_id: uuid.UUID | None = None
