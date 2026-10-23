"""fee seed rules

Bank and card fees go to "עמלות" so they can be totalled and alerted on.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

FEES = "עמלות"
# Lowercase (pipeline._match compares contains patterns against the lowercased description).
# " fee" keeps its leading space so "coffee" doesn't match.
PATTERNS = (
    "עמלת",
    "עמלה",
    "דמי ניהול חשבון",
    "דמי כרטיס",
    "דמי הנפקה",
    "ריבית חובה",
    "עמלת המרה",
    "עמלת מט",
    "דמי טיפול",
    "commission",
    " fee",
)
INSERT = sa.text(
    """INSERT INTO merchant_rules (pattern, match, category_id, source)
       SELECT :p, 'contains', id, 'seed' FROM categories WHERE name = :c
       ON CONFLICT (pattern, match) DO NOTHING"""
)


def upgrade() -> None:
    for p in PATTERNS:
        op.execute(INSERT.bindparams(p=p, c=FEES))


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM merchant_rules WHERE match = 'contains' AND source = 'seed' "
            "AND pattern IN :ps"
        ).bindparams(sa.bindparam("ps", list(PATTERNS), expanding=True))
    )
