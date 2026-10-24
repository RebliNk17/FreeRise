"""drop ₪0 transactions

Waived fees and CashCal placeholders are charged ₪0 and only clutter lists and the
categorize sheet; sync no longer stores them (service._no_money_moved). Same rule here:
keep a pending foreign charge that may still be converted.

Revision ID: 0022
Revises: 0021
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM transactions WHERE amount = 0 AND (status <> 'pending'"
        " OR coalesce(raw->>'original_currency', 'ILS') IN ('ILS', '₪'))"
    )


def downgrade() -> None:
    pass  # rows return on the next sync only if the scraper stops skipping them
