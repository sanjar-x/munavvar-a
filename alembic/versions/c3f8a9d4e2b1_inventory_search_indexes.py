"""inventory_search_indexes

Индексы под расширенные фильтры/поиск на страницах склада
(transfers, stock ledger, warehouses, balances, inventories/search).

Источник: research/INVENTORY_SEARCH_FILTERS_FRD.md §10.3.

Revision ID: c3f8a9d4e2b1
Revises: b2c4e8f1a7d3
Create Date: 2026-04-18 17:55:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f8a9d4e2b1"
down_revision: str | Sequence[str] | None = "b2c4e8f1a7d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# NOTE: CREATE INDEX CONCURRENTLY нельзя в транзакции — autocommit_block().
# pg_trgm уже включён finances-миграцией (b2c4e8f1a7d3), но IF NOT EXISTS
# делает команду идемпотентной.


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    statements = [
        # TRANSFERS: основной sort/cursor key
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_stock_transfer_created_at_id "
        "ON stock_transfers (created_at DESC, id DESC) "
        "WHERE is_active = true",
        # TRANSFERS: создатель (нет колоночного индекса)
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_stock_transfer_created_by "
        "ON stock_transfers (created_by_id, created_at DESC) "
        "WHERE is_active = true",
        # TRANSFERS: приёмщик (nullable)
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_stock_transfer_accepted_by "
        "ON stock_transfers (accepted_by_id, created_at DESC) "
        "WHERE accepted_by_id IS NOT NULL AND is_active = true",
        # TRANSFERS: trigram на reason (reason_search / q-text)
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_stock_transfer_reason_trgm "
        "ON stock_transfers USING gin (reason gin_trgm_ops) "
        "WHERE reason IS NOT NULL",
        # STOCK_TRANSACTIONS: главный ключ пагинации леджера
        # (is_active не применяем — append-only, отсутствует как концепт)
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_stock_transaction_created_at_id "
        "ON stock_transactions (created_at DESC, id DESC)",
        # STOCK_TRANSACTIONS: product + date для журналов «товар за период»
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_stock_transaction_product_created_at "
        "ON stock_transactions (product_id, created_at DESC)",
        # INVENTORIES: trigram на name (q-text и /inventories/search)
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_inventory_name_trgm "
        "ON inventories USING gin (name gin_trgm_ops) "
        "WHERE is_active = true",
        # PRODUCTS: trigram на name (JOIN-поиск со stock-ledger/transfers)
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_product_name_trgm "
        "ON products USING gin (name gin_trgm_ops) "
        "WHERE is_active = true",
        # USERS: trigram на username (контрагент-поиск).
        # Идемпотентно — уже создан finances-миграцией.
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_user_username_trgm "
        "ON users USING gin (username gin_trgm_ops) "
        "WHERE is_active = true",
        # IDENTITIES: поиск по цифрам телефона (local-provider)
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_identity_local_phone_digits_trgm "
        "ON identities USING gin "
        "((regexp_replace(provider_identity_id, '\\D', '', 'g')) "
        "gin_trgm_ops) "
        "WHERE provider = 'local'::auth_provider_enum",
        # PHONE_NUMBERS: поиск по цифрам дополнительных телефонов
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_phone_numbers_digits_trgm "
        "ON phone_numbers USING gin "
        "((regexp_replace(phone, '\\D', '', 'g')) gin_trgm_ops)",
    ]

    with op.get_context().autocommit_block():
        for stmt in statements:
            op.execute(stmt)


def downgrade() -> None:
    statements = [
        "DROP INDEX CONCURRENTLY IF EXISTS ix_phone_numbers_digits_trgm",
        "DROP INDEX CONCURRENTLY IF EXISTS "
        "ix_identity_local_phone_digits_trgm",
        # ix_user_username_trgm НЕ дропаем — создан finances-миграцией.
        "DROP INDEX CONCURRENTLY IF EXISTS ix_product_name_trgm",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_inventory_name_trgm",
        "DROP INDEX CONCURRENTLY IF EXISTS "
        "ix_stock_transaction_product_created_at",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_stock_transaction_created_at_id",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_stock_transfer_reason_trgm",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_stock_transfer_accepted_by",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_stock_transfer_created_by",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_stock_transfer_created_at_id",
    ]
    with op.get_context().autocommit_block():
        for stmt in statements:
            op.execute(stmt)
