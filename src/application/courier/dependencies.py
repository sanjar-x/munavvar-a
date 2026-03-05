# src/application/courier/dependencies.py
from src.application.courier.service import CourierService
from src.application.courier.uow import CourierUnitOfWork
from src.infrastructure.database.session import async_session_maker


def get_courier_uow() -> CourierUnitOfWork:
    return CourierUnitOfWork(session_factory=async_session_maker)


def get_courier_service() -> CourierService:
    return CourierService(uow=get_courier_uow())
