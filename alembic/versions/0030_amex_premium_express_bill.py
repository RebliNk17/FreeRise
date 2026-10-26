"""Amex bill as "חיוב מ-פרימיום אקספרס" is a card bill

Banks can name the Amex debit after its issuer, Premium Express; without a rule it was
filed as spending and double counted against the card's charges.

Revision ID: 0030
Revises: 0029
"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

PATTERN = "פרימיום אקספרס"


def upgrade() -> None:
    op.execute(
        sa.text(
            """INSERT INTO merchant_rules (pattern, match, category_id, source)
               SELECT :p, 'contains', id, 'seed' FROM categories WHERE name = 'חיוב כרטיס אשראי'
               ON CONFLICT (pattern, match) DO NOTHING"""
        ).bindparams(p=PATTERN)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM merchant_rules WHERE pattern = :p AND match = 'contains' AND source = 'seed'"
        ).bindparams(p=PATTERN)
    )
