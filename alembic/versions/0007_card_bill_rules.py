"""card bill seed rules

Bank-side credit-card bills must be categorized as card_bill even without the RiseUp seed,
otherwise they double count against the card transactions.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

CARD_BILL = "חיוב כרטיס אשראי"
# Copy of freerise.categorize.seed.CARD_BILL_PATTERNS at the time of writing, lowercased
# (pipeline._match compares contains patterns against the lowercased description).
PATTERNS = (
    "חיוב מ-כרטיסי אשראי",
    "מקס איט פיננ",
    "חיוב מ-ישראכרט",
    "חיוב מ-כאל",
    "אמריקן אקספרס",
    "ישראכרט",
)
INSERT = sa.text(
    """INSERT INTO merchant_rules (pattern, match, category_id, source)
       SELECT :p, 'contains', id, 'seed' FROM categories WHERE name = :c
       ON CONFLICT (pattern, match) DO NOTHING"""
)


def upgrade() -> None:
    for p in PATTERNS:
        op.execute(INSERT.bindparams(p=p.lower(), c=CARD_BILL))


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM merchant_rules WHERE match = 'contains' AND source = 'seed' "
            "AND pattern IN :ps"
        ).bindparams(sa.bindparam("ps", [p.lower() for p in PATTERNS], expanding=True))
    )
