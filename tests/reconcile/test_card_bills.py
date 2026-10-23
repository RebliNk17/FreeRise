from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from freerise.cashflow.cycles import cycle_for, get_start_day
from freerise.models import Account, Category, Credential, Notification, Transaction
from freerise.notify.rules import generate_notifications
from freerise.reconcile.card_bills import issuer_of, reconcile_bill, reconcile_cycle

TODAY = date(2026, 10, 23)
BILL = date(2026, 10, 15)
_n = 0


def _acct(s, provider, kind="card", excluded=False, name="a"):
    cred = Credential(provider=provider, label="l", owner="o", secret_enc=b"s")
    a = Account(
        credential=cred, provider_account_id=name, kind=kind, display_name=name, excluded=excluded
    )
    s.add(a)
    s.flush()
    return a


def _tx(s, a, amount, processed, desc="m", status="completed", cat=None, d=None):
    global _n
    _n += 1
    t = Transaction(
        account_id=a.id,
        txn_key=f"r{_n}",
        date=d or processed - timedelta(days=20),
        processed_date=processed,
        amount=Decimal(str(amount)),
        description=desc,
        merchant_key=desc,
        status=status,
        raw={},
        category_id=cat,
    )
    s.add(t)
    s.flush()
    return t


def _bill(s, bank, amount, desc="חיוב מ-ישראכרט", d=BILL):
    cat = s.scalar(select(Category.id).where(Category.group == "card_bill"))
    return _tx(s, bank, -amount, d, desc=desc, cat=cat, d=d)


def test_issuer_of():
    assert issuer_of("חיוב מ-ישראכרט") == "isracard"
    assert issuer_of("AMEX פיננסים") == "amex"
    assert issuer_of("מקס איט פיננסים") == "max"
    assert issuer_of("חיוב מ-כאל") == "visa cal"
    assert issuer_of("VISA CAL") == "visa cal"
    assert issuer_of("חיוב מ-כרטיסי אשראי לי") == "visa cal"
    assert issuer_of("כאל חיוב") == "visa cal"
    assert issuer_of("העברה למיכאל") is None
    assert issuer_of("דיינרס קלוב") == "diners"
    assert issuer_of("חיוב כרטיס פרימיום") is None


def test_exact_match_one_account(session):
    bank, card = _acct(session, "x", "bank"), _acct(session, "isracard")
    _tx(session, card, -100, BILL + timedelta(days=2))
    _tx(session, card, -50.5, BILL)
    _tx(session, card, 10, BILL)  # refund
    _tx(session, card, -999, BILL + timedelta(days=30))  # next bill
    r = reconcile_bill(session, _bill(session, bank, Decimal("140.5")).id)
    assert r.status == "matched" and r.matched_account_ids == [card.id]
    assert r.card_total == Decimal("140.5") and r.gap == 0 and r.suggestions == []


def test_two_cards_subset_match(session):
    bank = _acct(session, "x", "bank")
    c1, c2, c3 = (_acct(session, "max", name=n) for n in ("c1", "c2", "c3"))
    _tx(session, c1, -300, BILL)
    _tx(session, c2, -200, BILL)
    _tx(session, c3, -77, BILL)
    r = reconcile_bill(session, _bill(session, bank, 500, "מקס איט פיננסים").id)
    assert r.status == "matched" and sorted(r.matched_account_ids) == sorted([c1.id, c2.id])


def test_mismatch_suggests_purchase_in_next_bill(session):
    bank, card = _acct(session, "x", "bank"), _acct(session, "isracard")
    _tx(session, card, -400, BILL)
    late = _tx(session, card, -120, BILL + timedelta(days=31), desc="late")
    _tx(session, card, -55, BILL + timedelta(days=31))
    r = reconcile_bill(session, _bill(session, bank, 520).id)
    assert r.status == "mismatch" and r.gap == 120 and r.card_total == 400
    assert [x["txn_id"] for x in r.suggestions] == [late.id]
    assert r.suggestions[0]["reason"] == "חויבה בחיוב אחר של הכרטיס"


def test_pending_suggested(session):
    bank, card = _acct(session, "x", "bank"), _acct(session, "isracard")
    _tx(session, card, -400, BILL)
    p = _tx(session, card, -33, BILL - timedelta(days=10), status="pending")
    r = reconcile_bill(session, _bill(session, bank, 450).id)
    assert r.status == "mismatch" and [x["txn_id"] for x in r.suggestions] == [p.id]


def test_unknown_card_and_unknown_issuer(session):
    bank, card = _acct(session, "x", "bank"), _acct(session, "isracard", excluded=True)
    _tx(session, card, -100, BILL)
    cal = _bill(session, bank, 100, "חיוב מ-כאל")
    other = _bill(session, bank, 100, "חיוב כרטיס פרימיום")
    isra = _bill(session, bank, 100)
    assert reconcile_bill(session, cal.id).status == "unknown_card"
    r = reconcile_bill(session, other.id)
    assert r.status == "unknown_card" and r.issuer is None
    r = reconcile_bill(session, isra.id)  # excluded card still matches, flagged
    assert r.status == "matched" and r.matched_accounts[0]["excluded"] is True


def test_excluded_bank_ignored(session):
    bank = _acct(session, "x", "bank", excluded=True)
    _acct(session, "isracard")
    b = _bill(session, bank, 100)
    assert reconcile_bill(session, b.id) is None
    c = cycle_for(BILL, get_start_day(session))
    assert reconcile_cycle(session, c) == []


def test_notifications_fire_once(session):
    bank, card = _acct(session, "x", "bank"), _acct(session, "isracard")
    _tx(session, card, -400, TODAY - timedelta(days=3))
    _bill(session, bank, 500, d=TODAY - timedelta(days=3))
    _bill(session, bank, 80, "חיוב מ-כאל", d=TODAY - timedelta(days=8))
    _bill(session, bank, 80, "חיוב מ-כאל", d=TODAY - timedelta(days=60))  # too old
    # Card not synced since the bill: a mismatch would be a false alarm, deduped forever.
    card.credential.last_success_at = datetime(2026, 10, 20, 8, tzinfo=UTC)
    generate_notifications(session, TODAY)
    kinds = list(session.scalars(select(Notification.kind)))
    assert kinds.count("card_bill_mismatch") == 0 and kinds.count("card_unknown") == 1
    card.credential.last_success_at = datetime(2026, 10, 22, 8, tzinfo=UTC)
    for _ in range(2):
        generate_notifications(session, TODAY)
        kinds = list(session.scalars(select(Notification.kind)))
        assert kinds.count("card_bill_mismatch") == 1 and kinds.count("card_unknown") == 1
    n = session.scalar(select(Notification).where(Notification.kind == "card_unknown"))
    assert n.link == "/accounts#health" and "₪80" in n.body


def test_split_debit(session):
    bank, card = _acct(session, "x", "bank"), _acct(session, "isracard", name="c1")
    _tx(session, card, -1000, BILL)
    b1, b2 = _bill(session, bank, 600), _bill(session, bank, 400, d=BILL + timedelta(days=1))
    assert reconcile_bill(session, b1.id).status == "matched"
    assert reconcile_bill(session, b2.id).status == "matched"


def test_card_not_synced_is_mismatch_not_unknown(session):
    bank, card = _acct(session, "x", "bank"), _acct(session, "max", name="c1")
    last = _tx(session, card, -700, BILL - timedelta(days=30))
    r = reconcile_bill(session, _bill(session, bank, 700, desc="מקס איט פיננסים").id)
    assert r.status == "mismatch" and r.card_total == 0 and r.gap == 700
    assert [x["txn_id"] for x in r.suggestions] == [last.id]
    assert r.suggestions[0]["account_id"] == card.id


def test_seven_cards(session):
    bank = _acct(session, "x", "bank")
    for i in range(7):
        _tx(session, _acct(session, "max", name=f"c{i}"), -(1000 - i * 100), BILL)
    r = reconcile_bill(session, _bill(session, bank, 400, desc="מקס איט פיננסים").id)
    assert r.status == "matched"


def test_gap_suggestion_is_signed(session):
    bank, card = _acct(session, "x", "bank"), _acct(session, "isracard")
    _tx(session, card, -400, BILL)
    _tx(session, card, 100, BILL + timedelta(days=30))  # a refund can't explain a missing charge
    r = reconcile_bill(session, _bill(session, bank, 500).id)
    assert r.status == "mismatch" and r.suggestions == []


def test_foreign_currency_suggested(session):
    bank, card = _acct(session, "x", "bank"), _acct(session, "isracard")
    _tx(session, card, -400, BILL)
    usd = _tx(session, card, -50, BILL)
    usd.raw = {"charged_currency": "USD"}
    session.flush()
    r = reconcile_bill(session, _bill(session, bank, 470).id)
    assert r.status == "mismatch" and [x["txn_id"] for x in r.suggestions] == [usd.id]
    assert "מט״ח" in r.suggestions[0]["reason"]
