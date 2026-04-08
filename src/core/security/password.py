import asyncio
from functools import partial

from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

# Создаем объект для хеширования, используя Bcrypt.
# pwdlib автоматически обрабатывает параметры
# безопасности и генерацию соли (salt).
password_hash = PasswordHash((BcryptHasher(),))


async def get_password_hash(password: str) -> str:
    """
    Превращает открытый пароль в необратимый хеш.
    Именно этот результат мы сохраняем в колонку hashed_password.
    Bcrypt занимает 100-500 мс; выполняется в пуле потоков,
    чтобы не блокировать event loop.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, partial(password_hash.hash, password)
    )


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет, совпадает ли открытый пароль с хешем из базы данных.
    Bcrypt занимает 100-500 мс; выполняется в пуле потоков,
    чтобы не блокировать event loop.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(password_hash.verify, plain_password, hashed_password),
    )
