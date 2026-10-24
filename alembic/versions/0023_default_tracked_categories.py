"""default tracked categories on home (RiseUp-like starter set)

Existing installs seeded tracked_categories from their first sync's sparse history, often
leaving home almost empty. Add the starter set (home/builder.DEFAULT_TRACKED) where a
category exists and has no tracked row yet — a row the user removed (active=false) stays.

Revision ID: 0023
Revises: 0022
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

DEFAULTS = (
    ("כלכלה", "weekly"),
    ("אוכל בחוץ", "monthly"),
    ("תחבורה ציבורית", "monthly"),
    ("ביגוד והנעלה", "monthly"),
    ("פנאי", "monthly"),
)


def upgrade() -> None:
    for n, (name, mode) in enumerate(DEFAULTS):
        op.execute(
            f"""INSERT INTO tracked_categories (category_id, mode, sort_order, active)
            SELECT c.id, '{mode}', (SELECT coalesce(max(sort_order), 0) + 1 + {n}
                                    FROM tracked_categories), true
            FROM categories c
            WHERE c.name = '{name}' AND c."group" = 'variable'
              AND NOT EXISTS (SELECT 1 FROM tracked_categories t WHERE t.category_id = c.id)
              -- fresh installs seed the starter set on first home load (builder)
              AND EXISTS (SELECT 1 FROM tracked_categories)"""
        )


def downgrade() -> None:
    pass  # can't tell defaults from rows the user kept on purpose
