"""a recurring item's expected amount for one cycle ("this month only")

Revision ID: 0031
Revises: 0030
"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recurring_skips", sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("recurring_skips", "amount")
