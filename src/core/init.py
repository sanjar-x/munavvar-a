# # src/core/init.py
# import asyncio
# import logging
# import os

# from src.core.config import settings
# from src.infrastructure.database.session import async_session_maker
# from src.infrastructure.database.uow import BaseSQLAlchemyUoW
# from src.modules.users.exceptions import UserAlreadyExistsError
# from src.modules.users.models import Role
# from src.modules.users.schemas import UserAdminCreate
# from src.modules.users.services import UserService

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# async def create_initial_data() -> None:
#     logger.info("Начало инициализации базы данных...")

#     async with async_session_maker() as session:
#         uow = BaseSQLAlchemyUoW(session)
#         user_service = UserService()

#         async with uow:
#             existing_system = await uow.users.get(settings.SYSTEM_USER_ID)
#             if not existing_system:
#                 system_user = {
#                     "id": settings.SYSTEM_USER_ID,
#                     "username": "SYSTEM USER",
#                     "role": Role.SYSTEM,
#                 }
#                 await uow.users.add(system_user)
#                 await uow.commit()
#                 logger.info("✅ SYSTEM пользователь успешно создан.")
#             else:
#                 logger.info("ℹ️ SYSTEM пользователь уже существует. Пропуск.")

#         admin_phone = os.getenv("ADMIN_PHONE")
#         admin_password = os.getenv("ADMIN_PASSWORD")

#         if admin_phone and admin_password:
#             super_user = UserAdminCreate(
#                 username="Super Admin",
#                 phone=admin_phone,
#                 password=admin_password,
#                 role=Role.ADMIN,
#             )
#             try:
#                 await user_service.register_local_user(super_user)
#                 logger.info("✅ ADMIN пользователь успешно создан.")
#             except UserAlreadyExistsError:
#                 logger.info("ℹ️ ADMIN пользователь уже существует. Пропуск.")
#         else:
#             logger.warning("⚠️ ADMIN_PHONE или ADMIN_PASSWORD не переданы.")

#     logger.info("Инициализация базы данных завершена.")


# if __name__ == "__main__":
#     asyncio.run(main=create_initial_data())
