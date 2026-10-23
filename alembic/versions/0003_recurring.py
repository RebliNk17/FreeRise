"""recurring items

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _in(col: str, vals: tuple[str, ...], name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{col} IN ({', '.join(repr(v) for v in vals)})", name=name)


def upgrade() -> None:
    op.create_table(
        "recurring_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("merchant_key", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("cadence", sa.String(), nullable=False),
        sa.Column("amount_kind", sa.String(), nullable=False),
        sa.Column("expected_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("last_date", sa.Date(), nullable=False),
        sa.Column("next_expected_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("basis", sa.String(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("merchant_key", "direction"),
        _in("direction", ("expense", "income"), "ck_recurring_items_direction"),
        _in(
            "cadence",
            ("monthly", "bimonthly", "quarterly", "semiannual", "annual"),
            "ck_recurring_items_cadence",
        ),
        _in("amount_kind", ("fixed", "variable"), "ck_recurring_items_amount_kind"),
        _in("status", ("pending", "confirmed", "dismissed"), "ck_recurring_items_status"),
    )


def downgrade() -> None:
    op.drop_table("recurring_items")
