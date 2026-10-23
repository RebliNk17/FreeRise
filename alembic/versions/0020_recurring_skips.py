"""recurring skips: a confirmed fixed expense marked as not happening in one cycle

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_skips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "recurring_id",
            sa.Integer(),
            sa.ForeignKey("recurring_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cycle_start", sa.Date(), nullable=False),
        sa.UniqueConstraint("recurring_id", "cycle_start"),
    )


def downgrade() -> None:
    op.drop_table("recurring_skips")
