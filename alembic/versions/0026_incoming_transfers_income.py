"""incoming transfers from other people are income, not hidden transfers

The "העברה" default/seed rules filed every incoming bank transfer under העברות (group
transfer), which is left out of income and spending, so salaries and payments from other
people vanished. Re-runs the pipeline on those rows; only transfers from our own accounts
stay in העברות. User rules and manual choices are untouched.

Revision ID: 0026
Revises: 0025
"""

from alembic import op
from sqlalchemy.orm import Session

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from freerise.categorize.pipeline import reclassify_incoming_transfers

    reclassify_incoming_transfers(Session(bind=op.get_bind()))


def downgrade() -> None:
    pass  # ponytail: the next categorize-defaults/sync re-derives; nothing to restore
