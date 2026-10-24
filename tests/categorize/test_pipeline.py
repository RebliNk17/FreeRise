from freerise.categorize.pipeline import categorize_pending, categorize_transaction, set_category
from freerise.models import MerchantRule


def rule(session, pattern, cid, source, match="exact"):
    session.add(MerchantRule(pattern=pattern, match=match, category_id=cid, source=source))
    session.flush()


def test_user_rule_beats_seed(session, cat, mk_txn):
    t = mk_txn("שופרסל דיל")
    rule(session, t.merchant_key, cat("כלכלה").id, "seed")
    rule(session, t.merchant_key, cat("קניות").id, "user", match="contains")
    assert categorize_transaction(session, t) == (cat("קניות").id, "rule")


def test_contains_rule_matches_description(session, cat, mk_txn):
    t = mk_txn("XYZPAY תשלום לדני")
    rule(session, "תשלום לדני", cat("העברות").id, "seed", match="contains")
    assert categorize_transaction(session, t) == (cat("העברות").id, "map")


def test_provider_hint(session, cat, mk_txn):
    t = mk_txn("משהו", provider_category="דלק")
    assert categorize_transaction(session, t) == (cat("רכב").id, "provider")


def test_unknown_stays_uncategorized(session, mk_txn):
    t = mk_txn("???")
    assert categorize_transaction(session, t) == (None, None)
    assert categorize_pending(session) == 0
    assert t.category_id is None


def test_pending_categorizes(session, cat, mk_txn):
    t = mk_txn("שופרסל דיל")
    rule(session, t.merchant_key, cat("כלכלה").id, "seed")
    assert categorize_pending(session) == 1
    assert t.category_id == cat("כלכלה").id


def test_set_category_remember_and_apply_to_past(session, cat, mk_txn):
    a, b, c = (mk_txn("קפה גרג") for _ in range(3))
    c.category_id, c.category_source = cat("פנאי").id, "manual"
    assert set_category(session, a.id, cat("אוכל בחוץ").id, apply_to_past=True) == 2
    session.refresh(b)
    session.refresh(c)
    assert (a.category_source, b.category_id, c.category_id) == (
        "manual",
        cat("אוכל בחוץ").id,
        cat("פנאי").id,
    )
    r = session.query(MerchantRule).filter_by(pattern=a.merchant_key, match="exact").one()
    assert (r.source, r.category_id) == ("user", cat("אוכל בחוץ").id)


def _bank_txn(session, description, amount="-5000", excluded=False):
    from datetime import date
    from decimal import Decimal

    from freerise.categorize.normalize import normalize_merchant
    from freerise.models import Account, Credential, Transaction

    cred = Credential(provider="hapoalim", label="b", owner="s", secret_enc=b"x")
    session.add(cred)
    session.flush()
    acct = Account(
        credential_id=cred.id,
        provider_account_id=f"b{cred.id}",
        kind="bank",
        display_name="b",
        excluded=excluded,
    )
    session.add(acct)
    session.flush()
    t = Transaction(
        account_id=acct.id,
        txn_key=f"bank-{cred.id}",
        date=date(2026, 10, 12),
        processed_date=date(2026, 10, 12),
        raw={},
        amount=Decimal(amount),
        description=description,
        status="completed",
        merchant_key=normalize_merchant(description),
    )
    session.add(t)
    session.flush()
    return t


def test_migration_card_bill_rule_excludes_bank_bill_from_summary(session, cat):
    from freerise.cashflow.cycles import cycle_for, get_start_day
    from freerise.cashflow.summary import cycle_summary

    t = _bank_txn(session, "חיוב מ-ישראכרט בעמ")
    categorize_pending(session)
    assert t.category_id == cat("חיוב כרטיס אשראי").id
    summary = cycle_summary(session, cycle_for(t.date, get_start_day(session)))
    assert summary.spending == 0 and summary.uncategorized_count == 0


def test_contains_pattern_compared_lowercase(session, cat, mk_txn):
    t = mk_txn("ACME MKTPLACE")
    rule(session, "Acme", cat("קניות").id, "seed", match="contains")
    assert categorize_transaction(session, t) == (cat("קניות").id, "map")


def test_uncategorized_merchants_skips_excluded_accounts(session):
    from freerise.categorize.pipeline import uncategorized_merchants

    _bank_txn(session, "חנות מוסתרת", excluded=True)
    _bank_txn(session, "חנות גלויה")
    assert [m["sample_description"] for m in uncategorized_merchants(session)] == ["חנות גלויה"]


def test_card_bill_rules_skip_card_accounts(session, cat, mk_txn):
    t = mk_txn("דמי כרטיס ישראכרט")  # mk_txn rows live on a card account
    categorize_pending(session)
    assert t.category_id == cat("עמלות").id  # a card fee, not the card's bill


def test_fee_rules(session, cat, mk_txn):
    fees = cat("עמלות").id
    for desc in (
        "עמלת פעולה בערוץ ישיר",
        "דמי כרטיס",
        "עמלת המרת מט״ח",
        "עמלות ערוץ ישיר",
        "ANNUAL FEE",
        "Foreign Transaction Fee",
        "ATM FEE 12.50",
    ):
        assert categorize_transaction(session, mk_txn(desc)) == (fees, "map"), desc
    for desc in ("COFFEE SHOP", "ארומה coffee", "FEE REFUND CENTER", "דמי טיפול רפואי"):
        assert categorize_transaction(session, mk_txn(desc))[0] != fees, desc


def test_fee_rules_do_not_hijack_bank_card_bills(session, cat):
    for desc in ("חיוב מ-ישראכרט", "דמי כרטיס ישראכרט"):
        t = _bank_txn(session, desc)
        categorize_pending(session)
        assert t.category_id == cat("חיוב כרטיס אשראי").id, desc
    t = _bank_txn(session, "עמלת פעולה בערוץ ישיר", amount="-6.90")
    categorize_pending(session)
    assert t.category_id == cat("עמלות").id


def _incoming(session, description, owner="ישראל ישראלי", amount="2500"):
    from datetime import date
    from decimal import Decimal

    from freerise.categorize.normalize import normalize_merchant
    from freerise.models import Account, Credential, Transaction

    cred = Credential(provider="hapoalim", label="b", owner=owner, secret_enc=b"x")
    acct = Account(
        credential=cred, provider_account_id=f"in-{description}", kind="bank", display_name="b"
    )
    session.add(acct)
    session.flush()
    t = Transaction(
        account_id=acct.id,
        txn_key=f"in-{description}",
        date=date(2026, 10, 9),
        processed_date=date(2026, 10, 9),
        raw={},
        amount=Decimal(amount),
        description=description,
        status="completed",
        merchant_key=normalize_merchant(description),
    )
    session.add(t)
    session.flush()
    return t


def test_incoming_transfer_from_someone_else_is_income(session, cat):
    t = _incoming(session, "העברה מהפועלים/לוי דוד")
    categorize_pending(session)
    assert t.category_id == cat("הכנסות אחרות").id


def test_incoming_transfer_from_ourselves_stays_a_transfer(session, cat):
    own = _incoming(session, "העברה מב הפועלים ביט/ישראל ישראלי")
    mine = _incoming(session, "העברה ממפייבוקס שלי", amount="318.30")
    to_us = _incoming(session, "העברה מ- דני כהן ל- ישראל ישראלי", amount="12000")
    categorize_pending(session)
    assert own.category_id == mine.category_id == cat("העברות").id
    assert to_us.category_id == cat("הכנסות אחרות").id  # our name only as the recipient


def test_incoming_transfer_with_outgoing_twin_stays_a_transfer(session, cat):
    t = _incoming(session, "העברה מחשבון אחר", owner="xx", amount="500")
    twin = _incoming(session, "העברה לחשבון שלי", owner="yy", amount="-500")
    categorize_pending(session)
    assert t.category_id == twin.category_id == cat("העברות").id


def test_outgoing_transfer_and_user_rule_untouched(session, cat):
    out = _incoming(session, "העברה לבעל הדירה", amount="-2500")
    mine = _incoming(session, "העברה ממישהו", amount="100")
    rule(session, mine.merchant_key, cat("העברות").id, "user")
    categorize_pending(session)
    assert out.category_id == mine.category_id == cat("העברות").id


def test_reclassify_existing_seed_transfer(session, cat):
    from freerise.categorize.pipeline import reclassify_incoming_transfers

    t = _incoming(session, "העברה מבנק/שירותי השקעות", amount="5000")
    t.category_id, t.category_source = cat("העברות").id, "map"
    session.flush()
    assert reclassify_incoming_transfers(session) == 1
    assert t.category_id == cat("הכנסות אחרות").id
