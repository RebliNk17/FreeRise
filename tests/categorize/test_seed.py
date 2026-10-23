from pathlib import Path

from sqlalchemy import select

from freerise.categorize.seed import seed_from_riseup
from freerise.models import Category, MerchantRule

PSV = Path(__file__).parent / "riseup_fixture.psv"


def test_seed_from_riseup_creates_rules(session):
    assert seed_from_riseup(session, PSV) == 3
    cats = {c.id: c.name for c in session.scalars(select(Category))}
    rules = {r.pattern: cats[r.category_id] for r in session.scalars(select(MerchantRule))}
    assert rules["חברה חדשה"] == "מסעדות חדשות"
    assert rules["שופרסל דיל"] == "כלכלה"
    assert seed_from_riseup(session, PSV) == 0  # idempotent


def test_seed_card_bill_mapped(session):
    seed_from_riseup(session, PSV)
    r = session.scalar(select(MerchantRule).where(MerchantRule.pattern.like("חיוב מ%")))
    assert session.get(Category, r.category_id).name == "חיוב כרטיס אשראי"
