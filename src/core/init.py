# src/core/init.py
import logging
import os

from sqlalchemy import select

from src.core.config import settings
from src.core.security.password import get_password_hash
from src.infrastructure.database.models import Account, Identity, Inventory, User
from src.infrastructure.database.session import async_session_maker
from src.modules.finances.enums import AccountType
from src.modules.inventory.enums import InventoryType
from src.modules.users.enums import AuthProvider, Role

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_initial_data() -> None:
    logger.info("Начало инициализации базы данных...")

    async with async_session_maker() as session:
        # --- 1. СОЗДАНИЕ СИСТЕМНОГО ПОЛЬЗОВАТЕЛЯ ---
        query_system = select(User).where(User.role == Role.SYSTEM)
        system_user = (await session.execute(query_system)).scalar_one_or_none()

        if not system_user:
            system_user = User(
                id=settings.SYSTEM_USER_ID,
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
        required_accounts = {
            AccountType.REVENUE: "Выручка",
            AccountType.CASH: "Кассовый счёт",
            AccountType.CARD: "Карта",
            AccountType.BANK: "Банковский счёт",
        }

        for acc_type, acc_name in required_accounts.items():
            query_acc = select(Account).where(
                Account.user_id == system_user.id,
                Account.type == acc_type,
            )
            existing_acc = (await session.execute(query_acc)).scalar_one_or_none()

            if not existing_acc:
                new_acc = Account(
                    user_id=system_user.id,
                    type=acc_type,
                    name=acc_name,
                )
                session.add(new_acc)
                logger.info(f"Счёт '{acc_name}' ({acc_type.name}) создан.")
            else:
                logger.info(f"Счёт '{acc_name}' уже существует.")

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
            existing_inv = (await session.execute(query_inv)).scalar_one_or_none()

            if not existing_inv:
                new_inv = Inventory(
                    user_id=system_user.id,
                    type=inv_type,
                    name=inv_name,
                )
                session.add(new_inv)
                logger.info(f"Виртуальный склад '{inv_name}' ({inv_type.name}) создан.")
            else:
                logger.info(f"Виртуальный склад '{inv_name}' уже существует.")

        # --- 4. СОЗДАНИЕ ГЛАВНОГО АДМИНИСТРАТОРА ---
        admin_phone = os.getenv("ADMIN_PHONE")
        admin_password = os.getenv("ADMIN_PASSWORD")

        if not admin_phone or not admin_password:
            logger.warning(
                "ADMIN_PHONE или ADMIN_PASSWORD не заданы в переменных окружения. "
                "Пропуск создания стартового администратора."
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

                hashed_password = get_password_hash(admin_password)
                admin_identity = Identity(
                    user_id=admin_user.id,
                    provider=AuthProvider.LOCAL,
                    provider_identity_id=admin_phone,
                    password_hash=hashed_password,
                )
                session.add(admin_identity)
                logger.info(f"Администратор с номером {admin_phone} успешно создан.")
            else:
                logger.info(f"Администратор с номером {admin_phone} уже существует.")

        await session.commit()
        logger.info("Инициализация успешно завершена!")


# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(create_initial_data())
