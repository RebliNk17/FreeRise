"""pension funds

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _base(*cols, fk="credentials"):
    return (
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            f"{fk[:-1]}_id",
            sa.Integer(),
            sa.ForeignKey(f"{fk}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        *cols,
    )


def upgrade() -> None:
    money, pct = sa.Numeric(12, 2), sa.Numeric(7, 4)
    op.create_table(
        "funds",
        *_base(
            sa.Column("policy_id", sa.String(), nullable=False, unique=True),
            sa.Column("product_type", sa.String(), nullable=False),
            sa.Column("pension_type", sa.String()),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("company", sa.String()),
            sa.Column("liquidity_date", sa.Date()),
            sa.Column("fee_deposit_pct", pct),
            sa.Column("fee_savings_pct", pct),
            sa.Column("tracks", JSONB(), nullable=False, server_default="[]"),
            sa.Column("details", JSONB(), nullable=False, server_default="{}"),
            sa.Column("owner", sa.String(), nullable=False),
        ),
    )
    op.create_table(
        "fund_snapshots",
        *_base(
            sa.Column("as_of", sa.Date(), nullable=False),
            sa.Column("balance", money, nullable=False),
            sa.UniqueConstraint("fund_id", "as_of"),
            fk="funds",
        ),
    )
    op.create_table(
        "fund_deposits",
        *_base(
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("amount", money, nullable=False),
            sa.Column("raw", JSONB(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("fund_id", "date", "amount"),
            fk="funds",
        ),
    )
    op.create_table(
        "clearing_house_reports",
        *_base(
            sa.Column("report_month", sa.Date(), nullable=False),
            sa.Column("data", JSONB(), nullable=False),
            sa.UniqueConstraint("credential_id", "report_month"),
        ),
    )


def downgrade() -> None:
    for t in ("clearing_house_reports", "fund_deposits", "fund_snapshots", "funds"):
        op.drop_table(t)
