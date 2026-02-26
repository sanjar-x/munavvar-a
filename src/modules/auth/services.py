# src/modules/auth/services.py
from src.common.uow import IUnitOfWork
from src.core.exceptions import UnauthorizedError
from src.core.security.jwt import create_access_token
from src.core.security.password import verify_password
from src.core.security.permissions import ROLE_SCOPES
from src.modules.auth.schemas import LocalLogin, TokenResponse
from src.modules.users.models import AuthProvider


class AuthService:
    def __init__(self, uow: IUnitOfWork):
        self.uow: IUnitOfWork = uow

    async def local_login(
        self, data: LocalLogin
    ):  # -> TokenResponse (добавьте типизацию)
        """Бизнес-процесс входа в систему"""
        async with self.uow:
            result = await self.uow.users.get_with_identity(
                provider=AuthProvider.LOCAL,
                provider_identity_id=data.phone,
            )
            if not result:
                raise UnauthorizedError(
                    message="Неверный номер телефона или пароль",
                    error_code="INVALID_CREDENTIALS",
                )
            user, identity = result
            if not user or not identity.password_hash:
                raise UnauthorizedError(
                    message="Неверный номер телефона или пароль",
                    error_code="INVALID_CREDENTIALS",
                )
            # Строгая проверка валидности
            if not identity.password_hash:
                raise UnauthorizedError(
                    message="Неверный номер телефона или пароль",
                    error_code="INVALID_CREDENTIALS",
                )
            is_valid_password = verify_password(
                data.password, identity.password_hash
            )
            if not is_valid_password:
                raise UnauthorizedError(
                    message="Неверный номер телефона или пароль",
                    error_code="INVALID_CREDENTIALS",
                )
            user_scopes = ROLE_SCOPES.get(user.role, [])
            payload_data = {
                "sub": str(user.id),
                "scopes": user_scopes,
            }

            access_token = create_access_token(payload_data=payload_data)
            return TokenResponse(
                access_token=access_token, token_type="bearer"
            )
