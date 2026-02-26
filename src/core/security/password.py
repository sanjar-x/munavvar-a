from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

# Создаем объект для хеширования, используя Bcrypt.
# pwdlib автоматически обрабатывает параметры безопасности и генерацию соли (salt).
password_hash = PasswordHash((BcryptHasher(),))


def get_password_hash(password: str) -> str:
    """
    Превращает открытый пароль в необратимый хеш.
    Именно этот результат мы сохраняем в колонку hashed_password.
    """
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет, совпадает ли открытый пароль с хешем из базы данных.
    """
    return password_hash.verify(plain_password, hashed_password)
