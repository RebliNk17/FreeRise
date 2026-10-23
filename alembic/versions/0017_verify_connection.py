"""verify a connection before it counts

credentials.verified: false until a verify run logged in and fetched accounts (existing rows
are verified). credentials.pending_secret_enc: new details for an existing connection,
swapped in only once verified. sync_runs: trigger 'verify', progress stage + time (drives the
connecting screen and its no-progress timeout), user_id of whoever started it (only they may
answer its OTP).

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "credentials",
        sa.Column("verified", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column("credentials", sa.Column("pending_secret_enc", sa.LargeBinary(), nullable=True))
    op.drop_constraint("ck_sync_runs_trigger", "sync_runs")
    op.create_check_constraint(
        "ck_sync_runs_trigger", "sync_runs", "trigger IN ('schedule', 'manual', 'verify')"
    )
    op.add_column("sync_runs", sa.Column("progress", sa.String(), nullable=True))
    op.add_column("sync_runs", sa.Column("progress_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "sync_runs",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("sync_runs", "user_id")
    op.drop_column("sync_runs", "progress_at")
    op.drop_column("sync_runs", "progress")
    op.execute("DELETE FROM sync_runs WHERE trigger = 'verify'")
    op.drop_constraint("ck_sync_runs_trigger", "sync_runs")
    op.create_check_constraint(
        "ck_sync_runs_trigger", "sync_runs", "trigger IN ('schedule', 'manual')"
    )
    op.drop_column("credentials", "pending_secret_enc")
    op.drop_column("credentials", "verified")
