import sys
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

# All modules that import async_session_maker directly.
_SESSION_FACTORY_MODULES = [
    "src.infrastructure.database.session",
    "src.modules.users.dependencies",
    "src.modules.catalog.dependencies",
    "src.modules.orders.dependencies",
    "src.modules.inventory.dependencies",
    "src.modules.finances.dependencies",
    "src.modules.contracts.dependencies",
    "src.application.client.dependencies",
    "src.application.courier.dependencies",
    "src.application.inventories.dependencies",
]


def make_auth_headers(user_id: uuid.UUID, role: Role) -> dict[str, str]:
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


@pytest.fixture
async def _test_engine():
    """Create a fresh engine per test function to
    avoid event-loop mismatch with the module-level
    engine created at import time.
    """
    eng = create_async_engine(
        url=settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
    )
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_connection(_test_engine):
    """Open a connection with an outer transaction
    that rolls back after the test.
    """
    conn = await _test_engine.connect()
    trans = await conn.begin()
    try:
        yield conn
    finally:
        await trans.rollback()
        await conn.close()


@pytest.fixture
async def session_factory(db_connection):
    """Session factory bound to the test connection."""
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
    """Direct session for fixture data setup and
    balance assertions.
    """
    session = session_factory()
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture
async def client(session_factory):
    """httpx AsyncClient wired to the FastAPI app.

    Monkeypatches async_session_maker on every module
    that imports it so all UoW constructors receive
    the test session factory.
    """
    from src.api.server import create_app

    originals: dict[str, object] = {}
    for mod_path in _SESSION_FACTORY_MODULES:
        mod = sys.modules.get(mod_path)
        if mod and hasattr(mod, "async_session_maker"):
            originals[mod_path] = mod.async_session_maker
            mod.async_session_maker = session_factory  # ty:ignore[invalid-assignment]

    app = create_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    for mod_path, original in originals.items():
        mod = sys.modules.get(mod_path)
        if mod:
            mod.async_session_maker = original  # ty:ignore[invalid-assignment]
