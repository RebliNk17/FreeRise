"""sync alerts open the failing connection's edit sheet

Stored sync_failed / sync_paused alerts linked to the connections page (or the old
/settings/credentials). Point them at /accounts?edit=<credential id>, taken from the
dedup key "<kind>:<credential id>:<n>". Older sync_failed keys were "sync_failed:<run id>":
those take the run's credential; when the run is gone the link stays as it was.

Revision ID: 0027
Revises: 0026
"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """UPDATE notifications SET link = '/accounts?edit=' || split_part(dedup_key, ':', 2)
           WHERE kind IN ('sync_failed', 'sync_paused') AND dedup_key LIKE '%:%:%'"""
    )
    op.execute(
        """UPDATE notifications n SET link = '/accounts?edit=' || r.credential_id
           FROM sync_runs r WHERE n.kind = 'sync_failed' AND n.dedup_key = 'sync_failed:' || r.id"""
    )


def downgrade() -> None:
    pass  # ponytail: the old links still work (they land on /accounts)
