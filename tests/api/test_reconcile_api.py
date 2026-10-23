from datetime import date
from decimal import Decimal

from sqlalchemy import select

from freerise.cashflow.cycles import cycle_for, get_start_day
from freerise.models import Account, Category, Credential, Transaction

BILL = date(2026, 10, 15)


def _acct(s, provider, kind, name):
    cred = Credential(provider=provider, label="l", owner="o", secret_enc=b"s")
    a = Account(credential=cred, provider_account_id=name, kind=kind, display_name=name)
    s.add(a)
    s.flush()
    return a


def _tx(s, a, amount, desc="m", cat=None):
    t = Transaction(
        account_id=a.id,
        txn_key=f"{a.id}-{desc}",
        date=BILL,
        processed_date=BILL,
        amount=Decimal(amount),
        description=desc,
        merchant_key=desc,
        status="completed",
        raw={},
        category_id=cat,
    )
    s.add(t)
    s.flush()
    return t


def _bill(s, bank, amount, desc="חיוב מ-ישראכרט"):
    cat = s.scalar(select(Category.id).where(Category.group == "card_bill"))
    return _tx(s, bank, -amount, desc, cat)


def test_api_shape(authed, sf):
    with sf.begin() as s:
        bank, card = _acct(s, "x", "bank", "b"), _acct(s, "isracard", "card", "ישראכרט 1234")
        _tx(s, card, -100)
        bid = _bill(s, bank, 100).id
        _bill(s, bank, 70, "חיוב מ-כאל")
        c = cycle_for(BILL, get_start_day(s))
    body = authed.get(f"/api/reconcile/{c.label_month.year}/{c.label_month.month}").json()
    assert body["cycle"]["start"] == c.start.isoformat()
    assert (body["matched_count"], body["mismatch_count"], body["unknown_count"]) == (1, 0, 1)
    b = next(x for x in body["bills"] if x["bank_txn_id"] == bid)
    assert b["status"] == "matched" and b["amount"] == 100 and b["issuer"] == "isracard"
    assert b["matched_accounts"] == [{"id": card.id, "name": "ישראכרט 1234", "excluded": False}]
    cur = authed.get("/api/reconcile/current").json()  # cycle of the latest bill
    assert cur["cycle"] == body["cycle"]
    items = authed.get("/api/transactions?limit=500").json()["items"]
    st = {i["id"]: i["reconcile_status"] for i in items}
    assert st[bid] == "matched" and sorted(map(str, st.values())).count("None") == 1
