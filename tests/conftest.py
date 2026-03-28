import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings
from src.core.security.jwt import create_access_token
from src.core.security.permissions import ROLE_SCOPES
from src.modules.users.enums import Role


def make_auth_headers(
    user_id: uuid.UUID, role: Role
) -> dict[str, str]:
    scopes = ROLE_SCOPES.get(role, [])
    token = create_access_token(
        payload_data={
            "sub": str(user_id),
            "scopes": scopes,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def engine():
    eng = create_async_engine(
        url=settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_connection(engine):
    async with engine.connect() as conn:
        trans = await conn.begin()
        yield conn
        await trans.rollback()


@pytest.fixture
async def session_factory(db_connection):
    factory = async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    return factory


@pytest.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(session_factory):
    from src.api.server import create_app
    from src.infrastructure.database import session as session_module

    original = session_module.async_session_maker
    session_module.async_session_maker = session_factory
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac
    session_module.async_session_maker = original
