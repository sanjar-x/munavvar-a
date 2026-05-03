"""Walk-in client-account dedup: archive duplicate CLIENT accounts of WALKIN_USER_ID.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-03 12:00:00.000000+00:00

Background:
    Production hit MultipleResultsFound when calling
    AccountRepository.get_client_account(WALKIN_USER_ID) — the walk-in
    user has more than one active CLIENT account in the DB. This was
    historically possible because earlier init.py revisions could
    re-create the walk-in account on app startup if the row had been
    soft-deleted between runs.

    The walk-in user is not a real customer and never holds personal
    funds — every settlement creates two cancelling transactions
    (Revenue→Client, Client→Cash) so the net per-account balance is
    expected to be zero. Therefore archiving extra rows is safe iff
    none of them carries a non-zero balance.

What this migration does:
    1. Picks the oldest active CLIENT account of WALKIN_USER_ID as the
       survivor (deterministic, ORDER BY created_at ASC).
    2. If any other active duplicate has balance != 0, raises a SQL
       exception aborting the upgrade — the operator must reconcile
       manually before re-applying.
    3. Otherwise sets is_active = FALSE on every duplicate, keeping
       the survivor.

    Ledger sacredness is preserved: no UPDATE/DELETE on `transactions`
    or `stock_transactions` is performed. Historical entries pointing
    at the archived account_id remain intact.

Downgrade:
    No-op. We cannot reliably reactivate the duplicates because we
    have not recorded which rows we touched, and reactivating them
    would re-introduce the original bug.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


WALKIN_USER_ID = "00000000-0000-0000-0000-000000000002"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        DECLARE
            survivor_id  UUID;
            bad_count    INT;
            archived     INT;
        BEGIN
            SELECT id INTO survivor_id
            FROM accounts
            WHERE user_id = '{WALKIN_USER_ID}'
              AND type = 'client'
              AND is_active = TRUE
            ORDER BY created_at ASC, id ASC
            LIMIT 1;

            IF survivor_id IS NULL THEN
                RAISE NOTICE
                    'walk-in dedup: no active CLIENT account, nothing to do';
                RETURN;
            END IF;

            SELECT COUNT(*) INTO bad_count
            FROM accounts
            WHERE user_id = '{WALKIN_USER_ID}'
              AND type = 'client'
              AND is_active = TRUE
              AND id <> survivor_id
              AND balance <> 0;

            IF bad_count > 0 THEN
                RAISE EXCEPTION
                    'walk-in dedup aborted: % duplicate CLIENT account(s) '
                    'with non-zero balance. Manual reconciliation required '
                    'before re-running the migration.',
                    bad_count;
            END IF;

            UPDATE accounts
               SET is_active = FALSE
             WHERE user_id = '{WALKIN_USER_ID}'
               AND type = 'client'
               AND is_active = TRUE
               AND id <> survivor_id;

            GET DIAGNOSTICS archived = ROW_COUNT;
            RAISE NOTICE
                'walk-in dedup: kept survivor %, archived % duplicate(s)',
                survivor_id, archived;
        END $$;
        """
    )


def downgrade() -> None:
    # Intentionally empty — see module docstring.
    pass
