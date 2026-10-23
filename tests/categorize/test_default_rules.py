import pytest
from sqlalchemy import func, select

from freerise.categorize.cli import apply_default_rules
from freerise.categorize.default_categories import DEFAULT_CATEGORIES
from freerise.categorize.default_rules import (
    DEFAULT_RULES,
    PAIRS,
    PROVIDER_CATEGORIES,
    apply_defaults,
    coverage,
    match_default,
    provider_category,
)
from freerise.categorize.pipeline import categorize_pending, categorize_transaction
from freerise.models import MerchantRule

SAMPLES = [
    ("שופרסל דיל גבעתיים", "כלכלה"),
    ("SHUFERSAL ONLINE", "כלכלה"),
    ("רמי לוי שיווק השקמה", "כלכלה"),
    ("מ. יוחננוף ובניו-  ר", "כלכלה"),
    ("ויקטורי סניף 12", "כלכלה"),
    ("AM:PM דיזנגוף", "כלכלה"),
    ("חצי חינם חולון", "כלכלה"),
    ("מינימרקט השכונה", "כלכלה"),
    ("Wolt Market", "כלכלה"),
    ("פז YELLOW חיפה", "רכב"),
    ("דלק מנטה הרצליה", "רכב"),
    ("סונול באר שבע", "רכב"),
    ("פנגו -טעינה חשמלית", "רכב"),
    ("PANGO", "רכב"),
    ('כביש 6 חוצה צפון בע"', "רכב"),
    ("חניון קניון עזריאלי", "רכב"),
    ("רב-קו טעינה", "תחבורה ציבורית"),
    ("רכבת ישראל", "תחבורה ציבורית"),
    ("GETT", "תחבורה ציבורית"),
    ("בזק בינלאומי", "תקשורת"),
    ('סלקום ישראל בע"מ', "תקשורת"),
    ("HOT MOBILE", "תקשורת"),
    ("טלזר 019 שירותי תקשו", "תקשורת"),
    ("חברת החשמל לישראל", "חשמל"),
    ("אלקטרה פאוור חשמל", "חשמל"),
    ("פזגז", "חשמל"),  # not fuel: "פז " needs a word end
    ("מי אביבים 2010", "מים"),
    ("עיריית תל אביב ארנונה", "ארנונה"),
    ("מכבי שירותי בריאות", "בריאות"),
    ('קופ"ח מאוחדת-בימ"ק', "בריאות"),
    ("מנורה מבטחים-חיים/בר", "ביטוח"),
    ("ביטוח ישיר-חיים", "ביטוח"),
    ("ביטוח לאומי-י", "ביטוח לאומי"),
    ("ב.לאומי ילדים", "קצבאות"),
    ("סופר-פארם דיזנגוף", "פארמה"),
    ("SUPER-PHARM", "פארמה"),
    ("NETFLIX.COM", "דיגיטל"),
    ("SPOTIFY P420ECF50D", "דיגיטל"),
    ("APPLE.COM/BILL", "דיגיטל"),
    ("GOOGLE *YouTube", "דיגיטל"),
    ("PAYPAL *OPENAI *CHATGP", "דיגיטל"),
    ("CLAUDE.AI SUBSCRIPTION", "דיגיטל"),
    ("AMAZON PRIME", "דיגיטל"),
    ("AMZN Mktp US", "קניות"),
    ("ALIEXPRESS.COM", "קניות"),
    ("איקאה נתניה", "קניות"),
    ("KSP מחשבים", "קניות"),
    ("ZARA HOME", "קניות"),
    ("WOLT", "אוכל בחוץ"),
    ("תן ביס", "אוכל בחוץ"),
    ("מקדונלד'ס", "אוכל בחוץ"),
    ("קפה גרג קניון רמת אביב", "אוכל בחוץ"),
    ("דומינו'ס פיצה", "אוכל בחוץ"),
    ("קסטרו", "ביגוד והנעלה"),
    ("H&M", "ביגוד והנעלה"),
    ("ZARA", "ביגוד והנעלה"),
    ("TERMINAL X", "ביגוד והנעלה"),
    ('הולמס פלייס - הו"ק', "ספורט"),
    ("מגה ספורט קריון", "ספורט"),
    ("סינמה סיטי", "פנאי"),
    ("יס פלאנט", "פנאי"),
    ("מפעל הפיס", "פנאי"),
    ("EL AL", "תיירות"),
    ("BOOKING.COM", "תיירות"),
    ("RYANAIR", "תיירות"),
    ("האוניברסיטה העברית", "חינוך"),
    ("משכורת", "משכורת"),
    ("ביט העברת כסף", "העברות"),
    ("PAYBOX", "העברות"),
    ("לאומי למשכנתאות", "משכנתא"),
    ("הפקדה לקרן השתלמות", "השקעה וחיסכון"),
    ("משיכת מזומן", "כללי"),
]
MISSES = ["דני כהן", "ביטוחניק", "סופרלנד"]  # last two: no false prefix hits below


def test_rules_are_well_formed():
    names = {n for n, _ in DEFAULT_CATEGORIES}
    assert set(DEFAULT_RULES) <= names
    assert set(PROVIDER_CATEGORIES.values()) <= names
    pats = [p for p, _ in PAIRS]
    assert len(pats) >= 400
    assert len(pats) == len(set(pats)), "a pattern is listed twice"
    assert all(p == p.lower() and p.strip() and not p.startswith(" ") for p in pats)


@pytest.mark.parametrize(("pattern", "category"), PAIRS)
def test_every_pattern_hits_its_category(pattern, category):
    """A description that is exactly the pattern is not shadowed by another pattern."""
    assert match_default(pattern) == category


@pytest.mark.parametrize(("desc", "category"), SAMPLES)
def test_real_world_samples(session, cat, mk_txn, desc, category):
    assert categorize_transaction(session, mk_txn(desc)) == (cat(category).id, "default")


def test_word_boundaries():
    assert match_default("ביטוחניק") == "ביטוח"  # prefix hits are intended...
    assert match_default("סופרלנד") == "פנאי"
    assert match_default("קביט") is None  # ...but only at a word start
    assert match_default("בגט") is None  # short patterns take no attached prefix letter
    assert match_default("הפקדה לקופת גמל") == "השקעה וחיסכון"
    assert match_default("ביטוח רכב") == "ביטוח"  # "ביט " needs a word end
    assert match_default("דני כהן") is None


def test_coverage_helper():
    hits, missed = coverage([d for d, _ in SAMPLES] + ["דני כהן"])
    assert sum(hits.values()) == len(SAMPLES) and missed == ["דני כהן"]


def test_provider_fallback(session, cat, mk_txn):
    t = mk_txn("חנות קטנה", provider_category="מסעדות")
    assert categorize_transaction(session, t) == (cat("אוכל בחוץ").id, "provider")
    t = mk_txn("חנות קטנה", provider_category=" פנאי,  בידור וספורט ")
    assert categorize_transaction(session, t) == (cat("פנאי").id, "provider")
    for hint in ("שונות", "מוסדות", None, ""):
        assert categorize_transaction(session, mk_txn("חנות קטנה", provider_category=hint)) == (
            None,
            None,
        )
    assert provider_category("דלק, חשמל וגז") == "רכב"


def test_precedence(session, cat, mk_txn):
    def rule(pattern, name, source, match="exact"):
        session.add(
            MerchantRule(pattern=pattern, match=match, category_id=cat(name).id, source=source)
        )
        session.flush()

    # default beats the card company's category
    t = mk_txn("שופרסל דיל", provider_category="מסעדות")
    assert categorize_transaction(session, t) == (cat("כלכלה").id, "default")
    # seed/ai exact beats default contains
    rule("שופרסל דיל", "קניות", "seed")
    assert categorize_transaction(session, t) == (cat("קניות").id, "map")
    # user rule beats everything
    rule("שופרסל דיל", "פנאי", "user", match="contains")
    assert categorize_transaction(session, t) == (cat("פנאי").id, "rule")


def test_user_choices_never_overwritten(session, cat, mk_txn):
    manual = mk_txn("שופרסל דיל")
    manual.category_id, manual.category_source = cat("פנאי").id, "manual"
    by_rule = mk_txn("NETFLIX.COM")
    by_rule.category_id, by_rule.category_source = cat("חינוך").id, "rule"
    by_provider = mk_txn("WOLT")
    by_provider.category_id, by_provider.category_source = cat("קניות").id, "provider"
    pending = mk_txn("סונול")
    session.flush()
    r = apply_default_rules(session)
    assert (r["recategorized"], r["categorized"]) == (1, 1)
    assert (manual.category_id, manual.category_source) == (cat("פנאי").id, "manual")
    assert (by_rule.category_id, by_rule.category_source) == (cat("חינוך").id, "rule")
    assert (by_provider.category_id, by_provider.category_source) == (
        cat("אוכל בחוץ").id,
        "default",
    )
    assert pending.category_id == cat("רכב").id
    assert categorize_pending(session) == 0


def _defaults(session):
    return dict(
        session.execute(
            select(MerchantRule.pattern, MerchantRule.category_id).where(
                MerchantRule.source == "default"
            )
        ).all()
    )


def test_migration_installed_defaults_idempotently(session):
    assert len(_defaults(session)) == len(PAIRS)
    assert apply_defaults(session) == (0, 0, 0)


def test_apply_defaults_syncs_only_default_rules(session, cat):
    def get(p):
        return session.scalar(
            select(MerchantRule).where(MerchantRule.pattern == p, MerchantRule.match == "contains")
        )

    session.delete(get("netflix"))
    get("wolt").category_id = cat("קניות").id
    mine = get("spotify")
    mine.source, mine.category_id = "user", cat("חינוך").id
    session.add(
        MerchantRule(
            pattern="retired", match="contains", category_id=cat("כללי").id, source="default"
        )
    )
    session.flush()
    assert apply_defaults(session) == (1, 1, 1)
    session.expire_all()
    assert get("netflix").category_id == cat("דיגיטל").id
    assert get("wolt").category_id == cat("אוכל בחוץ").id
    assert (get("spotify").source, get("spotify").category_id) == ("user", cat("חינוך").id)
    assert get("retired") is None
    assert apply_defaults(session) == (0, 0, 0)
    n = session.scalar(
        select(func.count()).select_from(MerchantRule).where(MerchantRule.source == "default")
    )
    assert n == len(PAIRS) - 1  # spotify is the user's now
