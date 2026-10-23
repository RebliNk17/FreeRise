"""savings plans

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "savings_plans",
        *_base(),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("target_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("saved_amount", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("monthly_override", sa.Numeric(12, 2), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_table(
        "plan_contributions",
        *_base(),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("savings_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cycle_start", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.UniqueConstraint("plan_id", "cycle_start"),
    )


def downgrade() -> None:
    op.drop_table("plan_contributions")
    op.drop_table("savings_plans")
