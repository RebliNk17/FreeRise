"""fixed income and cycle attribution; account holder

transactions.cycle_date (+ source): the date used for cycle membership when a late/early
income belongs to a neighbour cycle. recurring_items.user_defined: fixed income marked by
the user. accounts.holder: whose card it is. Automatic attribution is computed at API /
worker startup and after every sync, not here.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("cycle_date", sa.Date(), nullable=True))
    op.add_column("transactions", sa.Column("cycle_date_source", sa.String(), nullable=True))
    op.create_check_constraint(
        "ck_transactions_cycle_date_source",
        "transactions",
        "cycle_date_source IN ('auto', 'manual')",
    )
    op.add_column(
        "recurring_items",
        sa.Column("user_defined", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("recurring_items", sa.Column("expected_day", sa.Integer(), nullable=True))
    op.add_column("accounts", sa.Column("holder", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "holder")
    op.drop_column("recurring_items", "expected_day")
    op.drop_column("recurring_items", "user_defined")
    op.drop_constraint("ck_transactions_cycle_date_source", "transactions")
    op.drop_column("transactions", "cycle_date_source")
    op.drop_column("transactions", "cycle_date")
