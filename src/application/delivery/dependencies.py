# src/use_cases/delivery/dependencies.py
from typing import Annotated

from fastapi import Depends

from src.application.delivery.service import DeliveryService
from src.application.delivery.uow import (
    DeliveryUnitOfWork,
    IDeliveryUnitOfWork,
)
from src.infrastructure.database.session import async_session_maker


def get_delivery_uow() -> IDeliveryUnitOfWork:
    """Фабрика композитного UoW для доставки."""
    return DeliveryUnitOfWork(session_factory=async_session_maker)


def get_delivery_orchestrator(
    uow: Annotated[IDeliveryUnitOfWork, Depends(get_delivery_uow)],
) -> DeliveryService:
    """Провайдер Оркестратора доставки."""
    return DeliveryService(uow=uow)
