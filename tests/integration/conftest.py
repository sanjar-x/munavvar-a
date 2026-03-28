import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import SYSTEM_USER_ID, WALKIN_USER_ID
from src.infrastructure.database.models import (
    Account,
    Identity,
    Inventory,
    Product,
    StockTransaction,
    StockTransfer,
    StockTransferItem,
    Transaction,
    User,
)
from src.modules.catalog.enums import ProductType
from src.modules.finances.enums import (
    AccountType,
    TransactionStatus,
)
from src.modules.inventory.enums import (
    InventoryType,
    TransferStatus,
    TransferType,
)
from src.modules.users.enums import AuthProvider, Role


# ---------------------------------------------------------
# Helper: load stock into an inventory via transfer + txn
# ---------------------------------------------------------
async def load_stock(
    session: AsyncSession,
    from_inv_id: uuid.UUID,
    to_inv_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
    created_by_id: uuid.UUID,
) -> None:
    """Create a completed stock transfer with ledger entry.

    After flush the PG trigger auto-creates / updates
    inventory_balances rows.
    """
    transfer = StockTransfer(
        from_id=from_inv_id,
        to_id=to_inv_id,
        type=TransferType.INITIAL_BALANCE,
        status=TransferStatus.COMPLETED,
        created_by_id=created_by_id,
    )
    session.add(transfer)
    await session.flush()

    item = StockTransferItem(
        transfer_id=transfer.id,
        product_id=product_id,
        quantity=quantity,
    )
    session.add(item)
    await session.flush()

    txn = StockTransaction(
        product_id=product_id,
        transfer_id=transfer.id,
        from_id=from_inv_id,
        to_id=to_inv_id,
        quantity=quantity,
    )
    session.add(txn)
    await session.flush()


# ---------------------------------------------------------
# Helper: credit an account via financial transaction
# ---------------------------------------------------------
async def credit_account(
    session: AsyncSession,
    from_account_id: uuid.UUID,
    to_account_id: uuid.UUID,
    amount: int,
    created_by_id: uuid.UUID,
) -> None:
    """Seed account balance via a completed transaction.

    After flush the PG trigger updates accounts.balance.
    """
    txn = Transaction(
        from_id=from_account_id,
        to_id=to_account_id,
        amount=amount,
        status=TransactionStatus.COMPLETED,
        reason="Test balance seed",
    )
    session.add(txn)
    await session.flush()


# ---------------------------------------------------------
# Fixture: system entities (already exist in dev DB)
# ---------------------------------------------------------
@pytest.fixture
async def system_entities(db_session: AsyncSession):
    """Query pre-existing system entities created by
    init_data(). Do NOT create these.

    Note: system user is looked up by role, not by
    SYSTEM_USER_ID constant, because init_data() uses
    settings.SYSTEM_USER_ID (which may differ).
    """
    system_user = (
        await db_session.execute(
            select(User).where(
                User.role == Role.SYSTEM
            )
        )
    ).scalar_one()
    sys_uid = system_user.id

    walkin_user = (
        await db_session.execute(
            select(User).where(
                User.id == WALKIN_USER_ID
            )
        )
    ).scalar_one()

    revenue_account = (
        await db_session.execute(
            select(Account).where(
                Account.user_id == sys_uid,
                Account.type == AccountType.REVENUE,
            )
        )
    ).scalar_one()

    cash_account = (
        await db_session.execute(
            select(Account).where(
                Account.user_id == sys_uid,
                Account.type == AccountType.CASH,
            )
        )
    ).scalar_one()

    card_account = (
        await db_session.execute(
            select(Account).where(
                Account.user_id == sys_uid,
                Account.type == AccountType.CARD,
            )
        )
    ).scalar_one()

    virtual_vendor = (
        await db_session.execute(
            select(Inventory).where(
                Inventory.user_id == sys_uid,
                Inventory.type
                == InventoryType.VIRTUAL_VENDOR,
            )
        )
    ).scalar_one()

    virtual_loss = (
        await db_session.execute(
            select(Inventory).where(
                Inventory.user_id == sys_uid,
                Inventory.type
                == InventoryType.VIRTUAL_LOSS,
            )
        )
    ).scalar_one()

    walkin_inventory = (
        await db_session.execute(
            select(Inventory).where(
                Inventory.user_id == WALKIN_USER_ID,
                Inventory.type == InventoryType.CLIENT,
            )
        )
    ).scalar_one()

    walkin_account = (
        await db_session.execute(
            select(Account).where(
                Account.user_id == WALKIN_USER_ID,
            )
        )
    ).scalar_one()

    return {
        "system_user": system_user,
        "walkin_user": walkin_user,
        "revenue_account": revenue_account,
        "cash_account": cash_account,
        "card_account": card_account,
        "virtual_vendor": virtual_vendor,
        "virtual_loss": virtual_loss,
        "walkin_inventory": walkin_inventory,
        "walkin_account": walkin_account,
    }


# ---------------------------------------------------------
# Fixture: products (tara + water)
# ---------------------------------------------------------
@pytest.fixture
async def products(db_session: AsyncSession):
    tara = Product(
        name="Test Tara 19L",
        type=ProductType.CONTAINER,
        price=50_000,
        is_active=True,
    )
    db_session.add(tara)
    await db_session.flush()

    water = Product(
        name="Test Water 19L",
        type=ProductType.WATER,
        price=20_000,
        returnable_item_id=tara.id,
        is_active=True,
    )
    db_session.add(water)
    await db_session.flush()

    return {"water": water, "tara": tara}


# ---------------------------------------------------------
# Fixture: admin user
# ---------------------------------------------------------
@pytest.fixture
async def admin_user(db_session: AsyncSession):
    user = User(
        username="Test Admin",
        role=Role.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    identity = Identity(
        user_id=user.id,
        provider=AuthProvider.LOCAL,
        provider_identity_id="+998901111111",
        password_hash="fakehash",
    )
    db_session.add(identity)
    await db_session.flush()

    return user


# ---------------------------------------------------------
# Fixture: courier user
# ---------------------------------------------------------
@pytest.fixture
async def courier_user(db_session: AsyncSession):
    user = User(
        username="Test Courier",
        role=Role.COURIER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    identity = Identity(
        user_id=user.id,
        provider=AuthProvider.LOCAL,
        provider_identity_id="+998902222222",
        password_hash="fakehash",
    )
    db_session.add(identity)
    await db_session.flush()

    return user


# ---------------------------------------------------------
# Fixture: client user (B2C)
# ---------------------------------------------------------
@pytest.fixture
async def client_user(db_session: AsyncSession):
    user = User(
        username="Test Client B2C",
        role=Role.CLIENT_B2C,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    identity = Identity(
        user_id=user.id,
        provider=AuthProvider.LOCAL,
        provider_identity_id="+998903333333",
        password_hash="fakehash",
    )
    db_session.add(identity)
    await db_session.flush()

    return user


# ---------------------------------------------------------
# Fixture: warehouse inventory
# ---------------------------------------------------------
@pytest.fixture
async def warehouse_inventory(
    db_session: AsyncSession, system_entities
):
    inv = Inventory(
        user_id=system_entities["system_user"].id,
        type=InventoryType.WAREHOUSE,
        name="Test Warehouse",
        is_active=True,
    )
    db_session.add(inv)
    await db_session.flush()
    return inv


# ---------------------------------------------------------
# Fixture: courier inventory
# ---------------------------------------------------------
@pytest.fixture
async def courier_inventory(
    db_session: AsyncSession, courier_user
):
    inv = Inventory(
        user_id=courier_user.id,
        type=InventoryType.COURIER,
        name="Test Courier Van",
        is_active=True,
    )
    db_session.add(inv)
    await db_session.flush()
    return inv


# ---------------------------------------------------------
# Fixture: client inventory
# ---------------------------------------------------------
@pytest.fixture
async def client_inventory(
    db_session: AsyncSession, client_user
):
    inv = Inventory(
        user_id=client_user.id,
        type=InventoryType.CLIENT,
        name="Test Client Address",
        is_active=True,
    )
    db_session.add(inv)
    await db_session.flush()
    return inv


# ---------------------------------------------------------
# Fixture: courier account
# ---------------------------------------------------------
@pytest.fixture
async def courier_account(
    db_session: AsyncSession, courier_user
):
    acc = Account(
        user_id=courier_user.id,
        type=AccountType.COURIER,
        name="Test Courier Account",
        balance=0,
        is_active=True,
    )
    db_session.add(acc)
    await db_session.flush()
    return acc


# ---------------------------------------------------------
# Fixture: client account
# ---------------------------------------------------------
@pytest.fixture
async def client_account(
    db_session: AsyncSession, client_user
):
    acc = Account(
        user_id=client_user.id,
        type=AccountType.CLIENT,
        name="Test Client Account",
        balance=0,
        is_active=True,
    )
    db_session.add(acc)
    await db_session.flush()
    return acc
