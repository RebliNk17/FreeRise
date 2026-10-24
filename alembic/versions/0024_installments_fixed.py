"""installments are fixed: category "תשלומים" moves to group fixed, stops being tracked

Installment payments are known in advance (n/N), so like RiseUp they count as fixed, not in
the variable spending or the weekly allowance (cashflow/summary.bucket also buckets any
installment transaction as fixed, whatever its category).

Revision ID: 0024
Revises: 0023
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """UPDATE tracked_categories SET active = false
        WHERE category_id IN (SELECT id FROM categories
                              WHERE name = 'תשלומים' AND "group" = 'variable')"""
    )
    op.execute(
        """UPDATE categories SET "group" = 'fixed'
        WHERE name = 'תשלומים' AND "group" = 'variable'"""
    )


def downgrade() -> None:
    op.execute(
        """UPDATE categories SET "group" = 'variable'
        WHERE name = 'תשלומים' AND "group" = 'fixed'"""
    )
