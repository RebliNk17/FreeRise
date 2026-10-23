import itertools
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from freerise.api import routes_home
from freerise.models import Account, Category, Credential, MerchantRule, Transaction

TODAY = date(2026, 10, 23)
_seq = itertools.count()


def _acct(s):
    cred = Credential(provider="max", label="מקס", owner="o", secret_enc=b"s")
    a = Account(credential=cred, provider_account_id="x7282", kind="card", display_name="מקס 7282")
    s.add(a)
    s.flush()
    return a


def _tx(s, a, d, amount, cat, key):
    t = Transaction(
        account_id=a.id,
        txn_key=f"ha{next(_seq)}",
        date=d,
        processed_date=d,
        amount=Decimal(str(amount)),
        description=key,
        merchant_key=key,
        category_id=s.scalar(select(Category.id).where(Category.name == cat)),
        status="completed",
        raw={},
    )
    s.add(t)
    s.flush()
    return t


@pytest.fixture
def home_api(authed, sf, monkeypatch):
    monkeypatch.setattr(routes_home, "today", lambda: TODAY)
    with sf() as s:
        a = _acct(s)
        t1 = _tx(s, a, date(2026, 10, 12), -50, "כלכלה", key="shop")
        t2 = _tx(s, a, date(2026, 10, 13), -60, "כלכלה", key="shop")
        t3 = _tx(s, a, date(2026, 10, 14), -70, "כלכלה", key="other")
        s.commit()
        cats = {c.name: c.id for c in s.scalars(select(Category))}
        return authed, [t1.id, t2.id, t3.id], cats


def test_home_and_tracking_api(home_api, sf):
    c, _, cats = home_api
    h = c.get("/api/home/current").json()
    assert h["cycle"]["start"] == "2026-10-10" and h["tracked"] == []  # no history -> none
    assert c.get("/api/home/2026/9").json()["summary"] is None
    food = cats["כלכלה"]
    assert c.put(f"/api/tracking/{food}", json={"tracked": True}).status_code == 204
    (t,) = c.get("/api/home/current").json()["tracked"]
    assert (t["name"], t["mode"], t["spent"]) == ("כלכלה", "weekly", 180)
    r = c.put(f"/api/tracking/{food}/expected", json={"cycle_start": "2026-10-10", "amount": 900})
    assert r.status_code == 204
    r = c.put(
        f"/api/tracking/{food}/weeks",
        json={"cycle_start": "2026-10-10", "week_index": 4, "amount": 50},
    )
    assert r.status_code == 204
    (t,) = c.get("/api/home/current").json()["tracked"]
    assert t["expected"] == 900 and t["expected_overridden"] and t["weeks"][4]["expected"] == 50
    c.put(f"/api/tracking/{food}", json={"tracked": True, "mode": "monthly"})
    c.put(f"/api/tracking/{food}/expected", json={"cycle_start": "2026-10-10", "amount": None})
    (t,) = c.get("/api/home/current").json()["tracked"]
    assert (t["mode"], t["weeks"], t["expected_overridden"]) == ("monthly", None, False)
    c.put(f"/api/tracking/{food}", json={"tracked": False})
    h = c.get("/api/home/current").json()
    assert h["tracked"] == [] and food in {x["category_id"] for x in h["untracked_available"]}
    assert c.put(f"/api/tracking/{cats['משכנתא']}", json={"tracked": True}).status_code == 422
    assert c.put("/api/tracking/99999", json={"tracked": True}).status_code == 404


def test_note_and_move_api(home_api, sf):
    c, (t1, t2, t3), cats = home_api
    assert c.put(f"/api/transactions/{t1}/note", json={"note": " מתנה "}).status_code == 204
    items = {t["id"]: t for t in c.get("/api/transactions").json()["items"]}
    assert items[t1]["note"] == "מתנה" and items[t2]["note"] is None
    c.put(f"/api/transactions/{t1}/note", json={"note": None})
    with sf() as s:
        assert s.get(Transaction, t1).note is None
    assert c.put("/api/transactions/99999/note", json={"note": "x"}).status_code == 404

    fun = cats["פנאי"]
    body = {"ids": [t1, 99999], "category_id": fun, "remember": True}
    assert c.post("/api/transactions/move", json=body).status_code == 404
    body["ids"] = [t1, t2, t3]
    r = c.post("/api/transactions/move", json=body)
    assert r.json() == {"changed": 3}
    with sf() as s:
        assert {s.get(Transaction, i).category_id for i in (t1, t2, t3)} == {fun}
        rules = s.scalars(select(MerchantRule.pattern).where(MerchantRule.source == "user")).all()
        assert sorted(rules) == ["other", "shop"]
