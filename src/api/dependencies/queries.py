# src/api/dependencies/queries.py
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_session
from src.modules.users.queries import UsersDashboardQuery


def get_users_dashboard_query(
    session: Annotated[AsyncSession, Depends(dependency=get_session)],
) -> UsersDashboardQuery:
    return UsersDashboardQuery(session)
