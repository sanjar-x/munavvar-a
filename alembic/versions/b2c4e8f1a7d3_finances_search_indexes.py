"""finances_search_indexes

Включить pg_trgm и создать индексы под расширенные фильтры/поиск
на страницах финансов (транзакции/счета).

Revision ID: b2c4e8f1a7d3
Revises: 1d156127d709
Create Date: 2026-04-16 15:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c4e8f1a7d3"
down_revision: str | Sequence[str] | None = "1d156127d709"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# NOTE: CREATE INDEX CONCURRENTLY нельзя в транзакции. Используем
# autocommit_block(), чтобы выполнить DDL вне транзакции миграции.


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    statements = [
        # Sort/pagination по (created_at, id)
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_transaction_created_at_id "
        "ON transactions (created_at DESC, id DESC) "
        "WHERE is_active = true",
        # Trigram-search по reason
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_transaction_reason_trgm "
        "ON transactions USING gin (reason gin_trgm_ops) "
        "WHERE is_active = true",
        # Trigram-search по account name
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_account_name_trgm "
        "ON accounts USING gin (name gin_trgm_ops) "
        "WHERE is_active = true",
        # Trigram-search по user username
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_user_username_trgm "
        "ON users USING gin (username gin_trgm_ops) "
        "WHERE is_active = true",
        # Быстрый фильтр PENDING-транзакций (частый кейс)
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_transaction_pending "
        "ON transactions (created_at DESC) "
        "WHERE is_active = true AND status = 'pending'",
        # Счета по типу + балансу (сортировка «должники сверху»)
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_account_type_balance "
        "ON accounts (type, balance DESC) "
        "WHERE is_active = true",
        # Orders по способу оплаты (для transactions → orders JOIN-фильтра)
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_order_payment_method "
        "ON orders (payment_method) "
        "WHERE is_active = true",
        # Пошаговый префикс/подстрочный поиск по contract.number
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_contract_number_trgm "
        "ON contracts USING gin (number gin_trgm_ops) "
        "WHERE is_active = true",
    ]

    with op.get_context().autocommit_block():
        for stmt in statements:
            op.execute(stmt)


def downgrade() -> None:
    statements = [
        "DROP INDEX CONCURRENTLY IF EXISTS ix_contract_number_trgm",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_order_payment_method",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_account_type_balance",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_transaction_pending",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_user_username_trgm",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_account_name_trgm",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_transaction_reason_trgm",
        "DROP INDEX CONCURRENTLY IF EXISTS ix_transaction_created_at_id",
    ]
    with op.get_context().autocommit_block():
        for stmt in statements:
            op.execute(stmt)
