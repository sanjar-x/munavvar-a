from src.modules.finances.uow import FinancesUnitOfWork


class BillingService:
    def __init__(self, uow: FinancesUnitOfWork):
        self.uow: FinancesUnitOfWork = uow
