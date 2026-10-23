"""sync run failure kind

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# Copy of freerise.models.FAILURE_KINDS at the time of writing.
KINDS = ("auth_failed", "provider_changed", "timeout", "otp_timeout", "other")


def upgrade() -> None:
    op.add_column("sync_runs", sa.Column("failure_kind", sa.String(), nullable=True))
    op.create_check_constraint(
        "ck_sync_runs_failure_kind",
        "sync_runs",
        f"failure_kind IN ({', '.join(repr(k) for k in KINDS)})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_sync_runs_failure_kind", "sync_runs", type_="check")
    op.drop_column("sync_runs", "failure_kind")
