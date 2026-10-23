"""default merchant rules (source='default')

Ships freerise.categorize.default_rules so fresh and existing installs categorize common
Israeli merchants without a RiseUp export. Idempotent; patterns already present (any source)
are skipped and user/seed rules are never touched. Deliberately uses the live rule list (like
0002 uses the live normalizer): `freerise categorize-defaults` re-syncs later changes.
Pending transactions are categorized by the next sync (or `freerise categorize-defaults`).

Revision ID: 0021
Revises: 0020
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def _sources(*s: str) -> None:
    op.drop_constraint("ck_merchant_rules_source", "merchant_rules", type_="check")
    op.create_check_constraint(
        "ck_merchant_rules_source", "merchant_rules", f"source IN ({', '.join(map(repr, s))})"
    )


def upgrade() -> None:
    from freerise.categorize.default_rules import apply_defaults

    _sources("user", "seed", "ai", "provider", "default")
    apply_defaults(op.get_bind())


def downgrade() -> None:
    op.execute("DELETE FROM merchant_rules WHERE source = 'default'")
    _sources("user", "seed", "ai", "provider")
