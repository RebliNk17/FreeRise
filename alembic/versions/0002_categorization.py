"""categorization: categories, merchant rules, settings, txn merchant_key

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Frozen copy of the defaults at the time of this migration.
DEFAULT_CATEGORIES = [
    ("משכורת", "income"),
    ("קצבאות", "income"),
    ("הכנסות אחרות", "income"),
    ("זיכויים", "income"),
    ("משכנתא", "fixed"),
    ("הלוואה", "fixed"),
    ("ארנונה", "fixed"),
    ("חשמל", "fixed"),
    ("מים", "fixed"),
    ("תקשורת", "fixed"),
    ("ביטוח", "fixed"),
    ("בריאות", "fixed"),
    ("ביטוח לאומי", "fixed"),
    ("חינוך", "fixed"),
    ("דיור", "fixed"),
    ("דיגיטל", "fixed"),
    ("עמלות", "fixed"),
    ("רכב", "variable"),
    ("כלכלה", "variable"),  # display name "סופר"
    ("אוכל בחוץ", "variable"),
    ("תחבורה ציבורית", "variable"),
    ("פנאי", "variable"),
    ("ספורט", "variable"),
    ("ביגוד והנעלה", "variable"),
    ("קניות", "variable"),
    ("פארמה", "variable"),
    ("תיירות", "variable"),
    ("תשלומים", "variable"),
    ("כללי", "variable"),
    ("השקעה וחיסכון", "savings"),
    ("העברות", "transfer"),
    ("חיוב כרטיס אשראי", "card_bill"),
    ("סליקת אשראי", "fixed"),
    ("RiseUp", "fixed"),
    ("להתעלם", "ignore"),
]

GROUPS = ("income", "fixed", "variable", "savings", "transfer", "card_bill", "ignore")


def _base():
    return [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    ]


def upgrade() -> None:
    categories = op.create_table(
        "categories",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("group", sa.String(), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_base(),
        sa.UniqueConstraint("name"),
        sa.CheckConstraint(
            f'"group" IN ({", ".join(repr(g) for g in GROUPS)})', name="ck_categories_group"
        ),
    )
    op.create_table(
        "merchant_rules",
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column("match", sa.String(), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(), nullable=False),
        *_base(),
        sa.UniqueConstraint("pattern", "match"),
        sa.CheckConstraint("match IN ('exact', 'contains')", name="ck_merchant_rules_match"),
        sa.CheckConstraint(
            "source IN ('user', 'seed', 'ai', 'provider')", name="ck_merchant_rules_source"
        ),
    )
    settings = op.create_table(
        "settings",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        *_base(),
        sa.UniqueConstraint("key"),
    )
    op.add_column(
        "transactions",
        sa.Column("merchant_key", sa.String(), server_default="", nullable=False),
    )
    op.add_column(
        "transactions",
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
    )
    op.add_column("transactions", sa.Column("category_source", sa.String(), nullable=True))
    op.create_index("ix_transactions_merchant_key", "transactions", ["merchant_key"])

    op.bulk_insert(
        categories,
        [{"name": n, "group": g, "sort_order": i} for i, (n, g) in enumerate(DEFAULT_CATEGORIES)],
    )
    op.bulk_insert(
        settings,
        [{"key": "cycle_start_day", "value": 10}, {"key": "month_end_goal_default", "value": 0}],
    )

    # Backfill existing rows. Deliberately imports the live normalizer (see task 11 ruling).
    from freerise.categorize.normalize import normalize_merchant

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, description FROM transactions")).all()
    if rows:
        conn.execute(
            sa.text("UPDATE transactions SET merchant_key = :k WHERE id = :i"),
            [{"i": i, "k": normalize_merchant(d)} for i, d in rows],
        )


def downgrade() -> None:
    op.drop_index("ix_transactions_merchant_key", table_name="transactions")
    op.drop_column("transactions", "category_source")
    op.drop_column("transactions", "category_id")
    op.drop_column("transactions", "merchant_key")
    op.drop_table("settings")
    op.drop_table("merchant_rules")
    op.drop_table("categories")
