# src/modules/auth/services.py
from pwdlib.exceptions import UnknownHashError

from src.core.constants import WALKIN_USER_ID
from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.core.security.jwt import create_access_token
from src.core.security.password import verify_password
from src.core.security.permissions import ROLE_SCOPES
from src.modules.auth.schemas import LocalLogin, TokenResponse
from src.modules.users.enums import Role
from src.modules.users.services import UserService

STAFF_ROLES: frozenset[Role] = frozenset(
    {
        Role.ADMIN,
        Role.ACCOUNTANT,
        Role.STOREKEEPER,
        Role.CASHIER,
        Role.COURIER,
    }
)
CLIENT_ROLES: frozenset[Role] = frozenset({Role.CLIENT_B2B, Role.CLIENT_B2C})


class AuthService:
    def __init__(self, user_service: UserService):
        self.user_service = user_service

    def _build_token_response(self, user) -> TokenResponse:
        user_scopes = ROLE_SCOPES.get(user.role, [])
        payload_data = {
            "sub": str(user.id),
            "scopes": user_scopes,
        }
        access_token = create_access_token(payload_data=payload_data)
        return TokenResponse(access_token=access_token, token_type="bearer")

    async def _authenticate_local_user(self, data: LocalLogin):
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

        try:
            is_valid_password = verify_password(
                data.password, identity.password_hash
            )
        except UnknownHashError as exc:
            raise UnauthorizedError(
                message="Неверный номер телефона или пароль",
                error_code="INVALID_CREDENTIALS",
            ) from exc

        if not is_valid_password:
            raise UnauthorizedError(
                message="Неверный номер телефона или пароль",
                error_code="INVALID_CREDENTIALS",
            )

        return user

    async def local_login(self, data: LocalLogin) -> TokenResponse:
        """Вход для staff-пользователей по телефону и паролю."""
        user = await self._authenticate_local_user(data)

        if user.role not in STAFF_ROLES:
            raise ForbiddenError(
                message="Этот вход доступен только для сотрудников.",
                error_code="STAFF_LOGIN_ONLY",
            )

        return self._build_token_response(user)

    async def courier_login(self, data: LocalLogin) -> TokenResponse:
        """Отдельный вход для курьеров по телефону и паролю."""
        user = await self._authenticate_local_user(data)

        if user.role != Role.COURIER:
            raise ForbiddenError(
                message="Этот вход доступен только для курьеров.",
                error_code="COURIER_LOGIN_ONLY",
            )

        return self._build_token_response(user)

    async def client_login(self, phone: str) -> TokenResponse:
        """Упрощенный вход только для клиентских аккаунтов."""

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

        if user.id == WALKIN_USER_ID:
            raise ForbiddenError(
                message=(
                    "Системный walk-in пользователь"
                    " не может входить в систему."
                ),
                error_code="WALKIN_LOGIN_FORBIDDEN",
            )

        if user.role not in CLIENT_ROLES:
            raise ForbiddenError(
                message="Для сотрудников используйте вход по паролю.",
                error_code="CLIENT_LOGIN_ONLY",
            )

        return self._build_token_response(user)
