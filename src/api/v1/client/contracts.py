# src/api/v1/client/contracts.py
from typing import Annotated

from fastapi import APIRouter, Depends, Security

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.contracts.dependencies import get_contract_service
from src.modules.contracts.exceptions import ContractRequiredError
from src.modules.contracts.schemas import (
    ContractDetailResponse,
    PriceItemResponse,
)
from src.modules.contracts.services import ContractService

contracts_router = APIRouter()


@contracts_router.get(
    "/my-contract",
    response_model=ContractDetailResponse,
    summary="Мой активный договор",
)
async def get_my_contract(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_READ])
    ],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    contract = await service.get_active_contract(current_user.id)
    if contract is None:
        raise ContractRequiredError(client_id=current_user.id)
    return await service.get_contract_with_prices(contract.id)


@contracts_router.get(
    "/my-contract/prices",
    response_model=list[PriceItemResponse],
    summary="Мой прайс-лист по договору",
)
async def get_my_contract_prices(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_READ])
    ],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    contract = await service.get_active_contract(current_user.id)
    if contract is None:
        raise ContractRequiredError(client_id=current_user.id)
    detail = await service.get_contract_with_prices(contract.id)
    return detail.price_items
