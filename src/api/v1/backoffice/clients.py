import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security, status

from src.application.client.dependencies import get_client_service
from src.application.client.schemas import (
    ClientCreate,
    ClientOnboardingRequest,
    ClientResponse,
    ClientsResponse,
    InventoryCreate,
)
from src.application.client.service import ClientService
from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.inventory.dependencies import get_capitalize_tara_service
from src.modules.inventory.schemas import (
    CapitalizeTaraRequest,
    CapitalizeTaraResponse,
)
from src.modules.inventory.services import CapitalizeTaraService
from src.modules.users.dependencies import get_user_service
from src.modules.users.schemas import UserAdminUpdate, UserResponse
from src.modules.users.services import UserService

clients_router = APIRouter()


@clients_router.post(
    "/onboard",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Единое окно: Быстрый онбординг клиента",
    description=(
        "Создает клиента, оприходует начальную тару"
        " и создает первый заказ за один запрос."
    ),
)
async def onboard_client(
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    data: ClientOnboardingRequest,
    client_service: Annotated[ClientService, Depends(get_client_service)],
):
    return await client_service.onboard_client_with_balance(
        data=data, creator_id=current_admin.id
    )


@clients_router.post(
    "/",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать нового клиента",
    description="Создает профиль клиента.",
)
async def create_client(
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    data: ClientCreate,
    client_service: Annotated[ClientService, Depends(get_client_service)],
):
    return await client_service.create_client(data=data)


@clients_router.post(
    "/{client_id}/inventories",
    status_code=status.HTTP_201_CREATED,
    response_model=ClientResponse,
    summary="Добавить новый адрес (инвентарь) клиенту",
    description=(
        "Создает дополнительный адрес доставки/склад"
        " для указанного клиента"
        " и возвращает обновленную карточку профиля."
    ),
)
async def create_client_inventory(
    client_id: uuid.UUID,
    data: InventoryCreate,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    client_service: Annotated[ClientService, Depends(get_client_service)],
):
    return await client_service.create_client_inventory(
        client_id=client_id, data=data
    )


@clients_router.get(
    "/",
    response_model=ClientsResponse,
    summary="Получить список клиентов",
    description=(
        "Возвращает список клиентов с пагинацией.  Поиск по ФИО/телефон."
    ),
)
async def get_clients(
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_READ])
    ],
    client_service: Annotated[ClientService, Depends(get_client_service)],
    skip: int = Query(0, ge=0, description="Сколько записей пропустить"),
    limit: int = Query(
        50, ge=1, le=100, description="Сколько записей вернуть"
    ),
    search: str | None = Query(None, description="Поиск по ФИО или телефону"),
):
    return await client_service.get_clients(
        skip=skip, limit=limit, search=search
    )


@clients_router.get(
    "/{client_id}",
    response_model=ClientResponse,
    summary="Получить карточку клиента",
    description=(
        "Возвращает полную информацию о клиенте:"
        " профиль, баланс счета, остатки на адресах"
        " и историю заказов."
    ),
)
async def get_client(
    client_id: uuid.UUID,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    client_service: Annotated[ClientService, Depends(get_client_service)],
):
    return await client_service.get_client(client_id=client_id)


@clients_router.patch(
    "/{client_id}",
    response_model=UserResponse,
    summary="Обновить данные Клиента",
)
async def update_client(
    client_id: uuid.UUID,
    schema: UserAdminUpdate,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    updated_user = await user_service.update(client_id, schema)
    return updated_user


@clients_router.post(
    "/{client_id}/inventory/capitalize",
    response_model=CapitalizeTaraResponse,
    summary="Оприходовать тару клиента",
    description=(
        "Фиксирует наличие тары на руках у клиента (начальный остаток). "
        "Без лимитов — диспетчер указывает точное количество."
    ),
)
async def capitalize_client_tara(
    client_id: uuid.UUID,
    data: CapitalizeTaraRequest,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    capitalize_service: Annotated[
        CapitalizeTaraService, Depends(get_capitalize_tara_service)
    ],
):
    return await capitalize_service.capitalize_tara(
        dto=data, created_by_id=current_admin.id
    )


@clients_router.post(
    "/{user_id}/block",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Заблокировать пользователя",
)
async def block_user(
    user_id: uuid.UUID,
    current_admin: Annotated[
        User, Security(get_current_user, scopes=[Scope.USERS_WRITE])
    ],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """
    Мягкое удаление / блокировка пользователя (is_active = False).
    """
    await user_service.archive(user_id)
