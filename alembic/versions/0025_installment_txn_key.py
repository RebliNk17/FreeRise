"""installment txn_key: identifier:number, so a purchase's installments don't overwrite each other

Cal's identifier is the deal number, shared by every installment, so keying on it alone kept
only the latest payment. Hashed (identifier-less) keys already include n/N.

Revision ID: 0025
Revises: 0024
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """UPDATE transactions SET txn_key = identifier || ':' || installment_number::text
        WHERE identifier IS NOT NULL AND installment_number IS NOT NULL
          AND txn_key = identifier"""
    )


def downgrade() -> None:
    # ponytail: lossy if several installments of one deal now exist; keeps the latest.
    op.execute(
        """DELETE FROM transactions t USING transactions n
        WHERE t.account_id = n.account_id AND t.identifier = n.identifier
          AND t.installment_number IS NOT NULL AND t.txn_key = t.identifier || ':' || t.installment_number::text
          AND n.txn_key = n.identifier || ':' || n.installment_number::text
          AND n.installment_number > t.installment_number"""
    )
    op.execute(
        """UPDATE transactions SET txn_key = identifier
        WHERE installment_number IS NOT NULL
          AND txn_key = identifier || ':' || installment_number::text"""
    )
