# src/modules/contracts/dependencies.py
from typing import Annotated

from fastapi import Depends

from src.infrastructure.database.session import async_session_maker
from src.modules.contracts.services import ContractService
from src.modules.contracts.uow import ContractUnitOfWork


def get_contract_uow() -> ContractUnitOfWork:
    return ContractUnitOfWork(session_factory=async_session_maker)


def get_contract_service(
    uow: Annotated[ContractUnitOfWork, Depends(get_contract_uow)],
) -> ContractService:
    return ContractService(uow=uow)
