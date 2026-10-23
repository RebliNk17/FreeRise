"""fee seed rules, round 2

Adds the plural "עמלות" and explicit English fee phrases; drops " fee" (too broad),
"דמי טיפול" (too broad) and the patterns already covered by "עמלת".

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

FEES = "עמלות"
# Lowercase (pipeline._match compares contains patterns against the lowercased description).
ADD = (
    "עמלות",
    "annual fee",
    "service fee",
    "late fee",
    "card fee",
    "transaction fee",
    "foreign transaction fee",
    "atm fee",
)
DROP = ("עמלת המרה", "עמלת מט", " fee", "דמי טיפול")
INSERT = sa.text(
    """INSERT INTO merchant_rules (pattern, match, category_id, source)
       SELECT :p, 'contains', id, 'seed' FROM categories WHERE name = :c
       ON CONFLICT (pattern, match) DO NOTHING"""
)


def _delete(patterns: tuple[str, ...]) -> None:
    op.execute(
        sa.text(
            "DELETE FROM merchant_rules WHERE match = 'contains' AND source = 'seed' "
            "AND pattern IN :ps"
        ).bindparams(sa.bindparam("ps", list(patterns), expanding=True))
    )


def upgrade() -> None:
    _delete(DROP)
    for p in ADD:
        op.execute(INSERT.bindparams(p=p, c=FEES))


def downgrade() -> None:
    _delete(ADD)
    for p in DROP:
        op.execute(INSERT.bindparams(p=p, c=FEES))
