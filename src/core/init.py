# src/core/init.py
from typing import Any

import structlog
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import SYSTEM_USER_ID, WALKIN_USER_ID
from src.core.security.password import get_password_hash
from src.infrastructure.database.models import (
    Account,
    Identity,
    Inventory,
    User,
)
from src.infrastructure.database.session import async_session_maker
from src.modules.finances.enums import AccountType
from src.modules.inventory.enums import InventoryType
from src.modules.users.enums import AuthProvider, Role

logger: Any = structlog.get_logger(__name__)


async def _ensure_account(
    session: Any,
    user_id: Any,
    acc_type: AccountType,
    acc_name: str,
) -> None:
    """Создаёт счёт если он ещё не существует."""
    query = select(Account).where(
        Account.user_id == user_id,
        Account.type == acc_type,
        Account.name == acc_name,
    )
    existing = (await session.execute(query)).scalar_one_or_none()

    if not existing:
        session.add(
            Account(
                user_id=user_id,
                type=acc_type,
                name=acc_name,
            )
        )
        logger.info(f"Счёт '{acc_name}' ({acc_type.name}) создан.")
    else:
        logger.info(f"Счёт '{acc_name}' уже существует.")


async def init_data() -> None:
    logger.info("Начало инициализации базы данных...")

    async with async_session_maker() as session:
        # --- 1. СОЗДАНИЕ СИСТЕМНОГО ПОЛЬЗОВАТЕЛЯ ---
        query_system = select(User).where(User.role == Role.SYSTEM)
        system_user = (
            await session.execute(query_system)
        ).scalar_one_or_none()

        if not system_user:
            system_user = User(
                id=SYSTEM_USER_ID,
                username="Система (Служебный аккаунт)",
                role=Role.SYSTEM,
                is_active=True,
            )
            session.add(system_user)
            await session.flush()
            logger.info("Системный пользователь создан.")
        else:
            logger.info("Системный пользователь уже существует.")

        # --- 2. СОЗДАНИЕ ФИНАНСОВЫХ СЧЕТОВ ---
        required_accounts = [
            (AccountType.REVENUE, "Выручка"),
            (AccountType.CASH, "Кассовый счёт"),
            (AccountType.CARD, "Карта"),
            (AccountType.BANK, "Банковский счёт"),
            (AccountType.EXPENSE, "Расходы (Наличные)"),
            (AccountType.EXPENSE, "Расходы (Карта)"),
            (AccountType.EXPENSE, "Расходы (Банк)"),
        ]

        for acc_type, acc_name in required_accounts:
            await _ensure_account(
                session,
                system_user.id,
                acc_type,
                acc_name,
            )

        # --- 3. СОЗДАНИЕ ВИРТУАЛЬНЫХ СКЛАДОВ ---
        required_inventories = {
            InventoryType.VIRTUAL_VENDOR: "Оприходование",
            InventoryType.VIRTUAL_LOSS: "Списание (Брак и Потери)",
        }

        for inv_type, inv_name in required_inventories.items():
            query_inv = select(Inventory).where(
                Inventory.user_id == system_user.id,
                Inventory.type == inv_type,
            )
            existing_inv = (
                await session.execute(query_inv)
            ).scalar_one_or_none()

            if not existing_inv:
                new_inv = Inventory(
                    user_id=system_user.id,
                    type=inv_type,
                    name=inv_name,
                )
                session.add(new_inv)
                logger.info(
                    f"Виртуальный склад '{inv_name}' ({inv_type.name}) создан."
                )
            else:
                logger.info(f"Виртуальный склад '{inv_name}' уже существует.")

        # --- 3.5 СОЗДАНИЕ WALK-IN ПОЛЬЗОВАТЕЛЯ ---
        # (АНОНИМНЫЕ ПРОДАЖИ СО СКЛАДА)
        query_walkin = select(User).where(User.id == WALKIN_USER_ID)
        walkin_user = (
            await session.execute(query_walkin)
        ).scalar_one_or_none()

        if not walkin_user:
            walkin_user = User(
                id=WALKIN_USER_ID,
                username="Покупатель со склада (Walk-in)",
                role=Role.CLIENT_B2C,
                is_active=True,
            )
            session.add(walkin_user)
            await session.flush()

            # Identity для Walk-in
            walkin_identity = Identity(
                user_id=walkin_user.id,
                provider=AuthProvider.LOCAL,
                provider_identity_id="00000000002",
                password_hash="!disabled",
            )
            session.add(walkin_identity)

            # Inventory для Walk-in
            walkin_inventory = Inventory(
                user_id=walkin_user.id,
                type=InventoryType.CLIENT,
                name="Самовывоз",
            )
            session.add(walkin_inventory)

            # Финансовый счет Walk-in
            walkin_account = Account(
                user_id=walkin_user.id,
                type=AccountType.CLIENT,
                name="Счёт анонимных покупок",
            )
            session.add(walkin_account)
            await session.flush()

            logger.info("Walk-in пользователь и связанные сущности созданы.")
        else:
            logger.info("Walk-in пользователь уже существует.")

        # --- 4. СОЗДАНИЕ ГЛАВНОГО АДМИНИСТРАТОРА ---
        admin_phone = settings.ADMIN_PHONE
        admin_password = (
            settings.ADMIN_PASSWORD.get_secret_value()
            if settings.ADMIN_PASSWORD
            else None
        )

        if not admin_phone or not admin_password:
            logger.warning(
                "ADMIN_PHONE или ADMIN_PASSWORD не заданы"
                " в переменных окружения."
                " Пропуск создания стартового администратора."
            )
        else:
            query_admin_identity = select(Identity).where(
                Identity.provider == AuthProvider.LOCAL,
                Identity.provider_identity_id == admin_phone,
            )
            existing_admin_identity = (
                await session.execute(query_admin_identity)
            ).scalar_one_or_none()

            if not existing_admin_identity:
                admin_user = User(
                    username="Главный Администратор",
                    role=Role.ADMIN,
                    is_active=True,
                )
                session.add(admin_user)
                await session.flush()

                hashed_password = await get_password_hash(admin_password)
                admin_identity = Identity(
                    user_id=admin_user.id,
                    provider=AuthProvider.LOCAL,
                    provider_identity_id=admin_phone,
                    password_hash=hashed_password,
                )
                session.add(admin_identity)

                await _ensure_account(
                    session,
                    admin_user.id,
                    AccountType.ADMIN,
                    "Счёт администратора",
                )

                logger.info(
                    f"Администратор с номером {admin_phone} успешно создан."
                )
            else:
                await _ensure_account(
                    session,
                    existing_admin_identity.user_id,
                    AccountType.ADMIN,
                    "Счёт администратора",
                )
                logger.info(
                    f"Администратор с номером {admin_phone} уже существует."
                )

        await session.commit()
        logger.info("Инициализация успешно завершена!")


if __name__ == "__main__":
    import asyncio

    asyncio.run(init_data())
