from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.categorize.normalize import normalize_merchant
from freerise.models import Category, MerchantRule

CARD_BILL = "חיוב כרטיס אשראי"
# Bare "cal" is deliberately absent (too broad); Cal only counts with the bank-side prefix.
CARD_BILL_PATTERNS = (
    "חיוב מ-כרטיסי אשראי",
    "מקס איט פיננ",
    "חיוב מ-ישראכרט",
    "חיוב מ-כאל",
    "אמריקן אקספרס",
    "פרימיום אקספרס",  # Amex's bank-side name
    "ישראכרט",
)
# RiseUp lists bank-side card bills under these categories.
_BILL_CATEGORIES = ("העברות", "כללי")


def seed_from_riseup(session: Session, path: Path) -> int:
    """Create seed MerchantRules from a RiseUp psv. Idempotent; returns rules created."""
    cats = {c.name: c.id for c in session.scalars(select(Category))}
    have = set(
        session.execute(select(MerchantRule.pattern).where(MerchantRule.match == "exact")).scalars()
    )
    created = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, _, rest = line.partition("|")
        cat = rest.split("|")[0].split("/")[0].strip()
        if cat in _BILL_CATEGORIES and any(p in name for p in CARD_BILL_PATTERNS):
            cat = CARD_BILL
        pattern = normalize_merchant(name)
        if not pattern or not cat or pattern in have:
            continue
        if cat not in cats:
            c = Category(name=cat, group="variable")
            session.add(c)
            session.flush()
            cats[cat] = c.id
        session.add(
            MerchantRule(pattern=pattern, match="exact", category_id=cats[cat], source="seed")
        )
        have.add(pattern)
        created += 1
    session.flush()
    return created
