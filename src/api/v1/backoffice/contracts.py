# src/api/v1/backoffice/contracts.py
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security, status

from src.core.security.permissions import Scope
from src.infrastructure.database.models import User
from src.modules.auth.dependencies import get_current_user
from src.modules.contracts.dependencies import get_contract_service
from src.modules.contracts.enums import ContractStatus
from src.modules.contracts.schemas import (
    ContractCreate,
    ContractDetailResponse,
    ContractResponse,
    ContractSuspendRequest,
    ContractTerminateRequest,
    ContractUpdate,
    InvoiceGenerateRequest,
    InvoiceResponse,
    PriceItemCreate,
    PriceItemResponse,
    ReconciliationResponse,
)
from src.modules.contracts.services import ContractService
from src.modules.orders.schemas import OrderResponse

contracts_router = APIRouter()


@contracts_router.post(
    "/",
    response_model=ContractResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать черновик договора",
)
async def create_contract(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_WRITE])
    ],
    data: ContractCreate,
    client_id: Annotated[
        uuid.UUID, Query(alias="clientId", description="ID клиента")
    ],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.create_contract(
        client_id=client_id,
        dto=data,
    )


@contracts_router.get(
    "/",
    response_model=list[ContractResponse],
    summary="Список договоров",
)
async def list_contracts(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_READ])
    ],
    service: Annotated[ContractService, Depends(get_contract_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    client_id: Annotated[uuid.UUID | None, Query(alias="clientId")] = None,
    status_filter: Annotated[
        ContractStatus | None, Query(alias="status")
    ] = None,
):
    return await service.list_contracts(
        client_id=client_id,
        status=status_filter,
        skip=skip,
        limit=limit,
    )


@contracts_router.get(
    "/{contract_id}",
    response_model=ContractDetailResponse,
    summary="Детали договора с прайс-листом",
)
async def get_contract(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_READ])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.get_contract_with_prices(contract_id)


@contracts_router.patch(
    "/{contract_id}",
    response_model=ContractResponse,
    summary="Обновить условия договора",
)
async def update_contract(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_WRITE])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    data: ContractUpdate,
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.update_contract(contract_id, data)


@contracts_router.post(
    "/{contract_id}/activate",
    response_model=ContractResponse,
    summary="Активировать договор",
)
async def activate_contract(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_MANAGE])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.activate_contract(
        contract_id=contract_id,
        signed_by_id=current_user.id,
    )


@contracts_router.post(
    "/{contract_id}/suspend",
    response_model=ContractResponse,
    summary="Приостановить договор",
)
async def suspend_contract(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_MANAGE])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    data: ContractSuspendRequest,
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.suspend_contract(
        contract_id=contract_id,
        reason=data.reason,
    )


@contracts_router.post(
    "/{contract_id}/reinstate",
    response_model=ContractResponse,
    summary="Восстановить приостановленный договор",
)
async def reinstate_contract(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_MANAGE])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.reinstate_contract(contract_id=contract_id)


@contracts_router.post(
    "/{contract_id}/terminate",
    response_model=ContractResponse,
    summary="Расторгнуть договор",
)
async def terminate_contract(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_MANAGE])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    data: ContractTerminateRequest,
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.terminate_contract(
        contract_id=contract_id,
        reason=data.reason,
    )


@contracts_router.get(
    "/{contract_id}/prices",
    response_model=list[PriceItemResponse],
    summary="Прайс-лист договора",
)
async def get_contract_prices(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_READ])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    contract = await service.get_contract_with_prices(contract_id)
    return contract.price_items


@contracts_router.put(
    "/{contract_id}/prices/{product_id}",
    response_model=PriceItemResponse,
    summary="Установить / обновить договорную цену товара",
)
async def upsert_price_item(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_WRITE])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    product_id: Annotated[uuid.UUID, Path()],
    data: PriceItemCreate,
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.set_price_item(
        contract_id=contract_id,
        product_id=product_id,
        price=data.price,
    )


@contracts_router.delete(
    "/{contract_id}/prices/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить договорную цену товара",
)
async def delete_price_item(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_WRITE])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    product_id: Annotated[uuid.UUID, Path()],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    await service.remove_price_item(
        contract_id=contract_id,
        product_id=product_id,
    )


@contracts_router.get(
    "/{contract_id}/orders",
    response_model=list[OrderResponse],
    summary="Заказы по договору",
)
async def get_contract_orders(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_READ])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    service: Annotated[ContractService, Depends(get_contract_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return await service.list_contract_orders(
        contract_id=contract_id,
        skip=skip,
        limit=limit,
    )


@contracts_router.post(
    "/{contract_id}/invoices",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Сформировать черновик счёта-фактуры за период",
)
async def generate_invoice(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_MANAGE])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    data: InvoiceGenerateRequest,
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.generate_invoice(
        contract_id=contract_id,
        period_from=data.period_from,
        period_to=data.period_to,
    )


@contracts_router.get(
    "/{contract_id}/invoices",
    response_model=list[InvoiceResponse],
    summary="Список счетов-фактур по договору",
)
async def list_invoices(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_READ])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.list_invoices(contract_id=contract_id)


@contracts_router.get(
    "/{contract_id}/invoices/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Получить счёт-фактуру",
)
async def get_invoice(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_READ])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    invoice_id: Annotated[uuid.UUID, Path()],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.get_invoice(
        contract_id=contract_id,
        invoice_id=invoice_id,
    )


@contracts_router.post(
    "/{contract_id}/invoices/{invoice_id}/issue",
    response_model=InvoiceResponse,
    summary="Выставить счёт-фактуру (DRAFT → ISSUED)",
)
async def issue_invoice(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_MANAGE])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    invoice_id: Annotated[uuid.UUID, Path()],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.issue_invoice(
        contract_id=contract_id,
        invoice_id=invoice_id,
    )


@contracts_router.post(
    "/{contract_id}/invoices/{invoice_id}/mark-paid",
    response_model=InvoiceResponse,
    summary="Отметить счёт-фактуру как оплаченный",
)
async def mark_invoice_paid(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_MANAGE])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    invoice_id: Annotated[uuid.UUID, Path()],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.mark_invoice_paid(
        contract_id=contract_id,
        invoice_id=invoice_id,
    )


@contracts_router.delete(
    "/{contract_id}/invoices/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Аннулировать счёт-фактуру (DRAFT/ISSUED → CANCELLED)",
)
async def cancel_invoice(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_MANAGE])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    invoice_id: Annotated[uuid.UUID, Path()],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.cancel_invoice(
        contract_id=contract_id,
        invoice_id=invoice_id,
    )


@contracts_router.get(
    "/{contract_id}/reconciliation",
    response_model=ReconciliationResponse,
    summary="Акт сверки по договору за период",
)
async def get_reconciliation(
    current_user: Annotated[
        User, Security(get_current_user, scopes=[Scope.CONTRACTS_READ])
    ],
    contract_id: Annotated[uuid.UUID, Path()],
    date_from: Annotated[
        date, Query(alias="dateFrom", description="Начало периода")
    ],
    date_to: Annotated[
        date, Query(alias="dateTo", description="Конец периода")
    ],
    service: Annotated[ContractService, Depends(get_contract_service)],
):
    return await service.get_reconciliation(
        contract_id=contract_id,
        date_from=date_from,
        date_to=date_to,
    )
