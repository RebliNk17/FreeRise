"""recurring item charge account

Which account a recurring item was last charged from, and the one before a switch.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

COLS = ("account_id", "previous_account_id")


def upgrade() -> None:
    for c in COLS:
        op.add_column(
            "recurring_items",
            sa.Column(c, sa.Integer(), sa.ForeignKey("accounts.id", ondelete="SET NULL")),
        )
    op.add_column("recurring_items", sa.Column("account_changed_on", sa.Date()))


def downgrade() -> None:
    op.drop_column("recurring_items", "account_changed_on")
    for c in COLS:
        op.drop_column("recurring_items", c)
