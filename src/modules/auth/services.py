# src/modules/auth/services.py
from src.core.exceptions import UnauthorizedError
from src.core.security.jwt import create_access_token
from src.core.security.password import verify_password
from src.core.security.permissions import ROLE_SCOPES
from src.modules.auth.schemas import LocalLogin, TokenResponse
from src.modules.users.services import UserService


class AuthService:
    def __init__(self, user_service: UserService):
        self.user_service = user_service

    async def local_login(self, data: LocalLogin) -> TokenResponse:
        """Бизнес-процесс входа в систему"""

        # 1. Получаем пользователя и его учетные данные для локального входа
        result = await self.user_service.get_user_local_identity(
            identity_id=data.phone,
        )

        if not result:
            raise UnauthorizedError(
                message="Неверный номер телефона или пароль",
                error_code="INVALID_CREDENTIALS",
            )

        user, identity = result

        # 2. Базовые проверки целостности данных
        if not user or not identity.password_hash:
            raise UnauthorizedError(
                message="Неверный номер телефона или пароль",
                error_code="INVALID_CREDENTIALS",
            )

        # 4. Строгая проверка валидности пароля
        is_valid_password = verify_password(data.password, identity.password_hash)
        if not is_valid_password:
            raise UnauthorizedError(
                message="Неверный номер телефона или пароль",
                error_code="INVALID_CREDENTIALS",
            )

        # 5. Подготовка Payload и генерация JWT
        user_scopes = ROLE_SCOPES.get(user.role, [])
        payload_data = {
            "sub": str(user.id),
            "scopes": user_scopes,
        }

        access_token = create_access_token(payload_data=payload_data)

        return TokenResponse(access_token=access_token, token_type="bearer")

    async def client_login(self, phone) -> TokenResponse:
        """Бизнес-процесс входа в систему"""

        result = await self.user_service.get_user_local_identity(
            identity_id=phone,
        )

        if not result:
            raise UnauthorizedError(
                message="Неверный номер телефона или пароль",
                error_code="INVALID_CREDENTIALS",
            )

        user, identity = result

        # 2. Базовые проверки целостности данных
        if not user:
            raise UnauthorizedError(
                message="Неверный номер телефона",
                error_code="INVALID_CREDENTIALS",
            )

        # 5. Подготовка Payload и генерация JWT
        user_scopes = ROLE_SCOPES.get(user.role, [])
        payload_data = {
            "sub": str(user.id),
            "scopes": user_scopes,
        }

        access_token = create_access_token(payload_data=payload_data)

        return TokenResponse(access_token=access_token, token_type="bearer")
