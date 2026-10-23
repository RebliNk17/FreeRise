"""home: transaction notes, tracked categories, category budgets

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
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


def _cat() -> sa.Column:
    return sa.Column(
        "category_id",
        sa.Integer(),
        sa.ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.add_column("transactions", sa.Column("note", sa.String(), nullable=True))
    op.create_table(
        "tracked_categories",
        *_base(),
        _cat(),
        sa.Column("mode", sa.String(), server_default="monthly", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.UniqueConstraint("category_id"),
        sa.CheckConstraint("mode IN ('weekly', 'monthly')", name="ck_tracked_categories_mode"),
    )
    op.create_table(
        "category_budgets",
        *_base(),
        sa.Column("cycle_start", sa.Date(), nullable=False),
        _cat(),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.UniqueConstraint("cycle_start", "category_id"),
    )
    op.create_table(
        "category_week_budgets",
        *_base(),
        sa.Column("cycle_start", sa.Date(), nullable=False),
        _cat(),
        sa.Column("week_index", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.UniqueConstraint("cycle_start", "category_id", "week_index"),
    )


def downgrade() -> None:
    op.drop_table("category_week_budgets")
    op.drop_table("category_budgets")
    op.drop_table("tracked_categories")
    op.drop_column("transactions", "note")
