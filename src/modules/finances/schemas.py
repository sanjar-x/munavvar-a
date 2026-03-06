# src/modules/finances/schemas.py
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.modules.finances.enums import AccountType


class AccountBase(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        title="Название счета",
        examples=[
            "Личный счет Клиента",
            "Касса Курьера Ивана",
            "Основной Банковский Счет",
        ],
    )
    type: AccountType = Field(
        ...,
        title="Тип счета",
        description="Определяет системное назначение счета",
    )


class AccountCreate(AccountBase):
    """
    Создание нового счета.
    Обрати внимание: поля `balance` здесь НЕТ!
    Все новые счета рождаются с балансом 0.
    """

    user_id: uuid.UUID = Field(..., title="Владелец счета (Пользователь или Система)")


class AccountUpdate(BaseModel):
    """
    Единственное, что можно изменить у существующего счета — это его название.
    Менять владельца или тип счета после создания строго запрещено аудитом.
    """

    name: str = Field(..., min_length=2, max_length=255)


class AccountResponse(AccountBase):
    """Модель ответа для фронтенда и админки."""

    id: uuid.UUID
    user_id: uuid.UUID
    balance: int = Field(
        title="Текущий баланс",
        description="В минимальных единицах (копейки/тиыйны). Может быть отрицательным (долг).",
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =====================================================================
# 2. ТРАНЗАКЦИИ (TRANSACTIONS)
# =====================================================================


class TransactionCreate(BaseModel):
    """
    Схема для ручных проводок (Например: Бухгалтер принимает наличные от курьера).
    Для заказов (Checkout) эта схема не используется, так как UseCase
    будет генерировать проводки автоматически внутри Python-кода.
    """

    from_id: uuid.UUID = Field(
        ..., title="Счет списания (Дебет)", description="Откуда уходят деньги"
    )
    to_id: uuid.UUID = Field(
        ...,
        title="Счет зачисления (Кредит)",
        description="Куда приходят деньги",
    )
    amount: int = Field(
        ...,
        gt=0,
        title="Сумма перевода",
        examples=[150000],
    )
    reason: str = Field(
        ...,
        min_length=3,
        max_length=255,
        title="Основание платежа",
        examples=["Сдача выручки курьером", "Пополнение баланса через Payme"],
    )

    order_id: uuid.UUID | None = Field(default=None)


class TransactionResponse(BaseModel):
    """История операций (Выписка по счету)."""

    id: uuid.UUID
    from_id: uuid.UUID
    to_id: uuid.UUID
    order_id: uuid.UUID | None
    amount: int
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
