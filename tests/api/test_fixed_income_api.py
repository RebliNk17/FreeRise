import itertools
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from freerise.api import routes_forecast, routes_home
from freerise.models import Account, Category, Credential, RecurringItem, Transaction

TODAY = date(2026, 10, 23)
_seq = itertools.count()


def _tx(s, a, d, amount, key, cat):
    t = Transaction(
        account_id=a.id,
        txn_key=f"fa{next(_seq)}",
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
    return t.id


@pytest.fixture
def data(authed, sf, monkeypatch):
    for m in (routes_home, routes_forecast):
        monkeypatch.setattr(m, "today", lambda: TODAY)
    with sf() as s:
        cred = Credential(provider="isracard", label="ישראכרט", owner="שי", secret_enc=b"s")
        a = Account(
            credential=cred, provider_account_id="x5678", kind="card", display_name="ישראכרט 5678"
        )
        s.add(a)
        s.flush()
        ids = {
            "inc": _tx(s, a, date(2026, 10, 11), 9000, "salary", "משכורת"),
            "exp": _tx(s, a, date(2026, 10, 12), -50, "shop", "קניות"),
        }
        s.commit()
        return authed, ids, a.id


def _get(c, tid):
    return next(t for t in c.get("/api/transactions").json()["items"] if t["id"] == tid)


def test_fixed_income_and_cycle_endpoints(data, sf):
    c, ids, _acct = data
    t = _get(c, ids["inc"])
    assert t["account_holder"] == "שי" and t["fixed_income_id"] is None
    assert c.post(f"/api/transactions/{ids['exp']}/fixed-income", json={}).status_code == 400
    r = c.post(f"/api/transactions/{ids['inc']}/fixed-income", json={"expected_day": 9})
    assert r.status_code == 200
    rid = r.json()["fixed_income_id"]
    with sf() as s:
        it = s.get(RecurringItem, rid)
        assert (it.status, it.user_defined, it.expected_day, it.amount_kind) == (
            "confirmed",
            True,
            9,
            "variable",
        )
        assert it.expected_amount == 9000
    home = c.get("/api/home/current").json()
    assert home["income"]["expected"] >= 9000
    f = c.get("/api/forecast/next").json()
    assert [(x["label"], x["category_name"]) for x in f["income_items"]] == [("משכורת", "משכורת")]

    r = c.put(f"/api/transactions/{ids['inc']}/cycle", json={"target": "previous"})
    assert r.status_code == 200
    j = r.json()
    assert (j["cycle_shift"], j["cycle_label"], j["cycle_date_source"]) == (
        "previous",
        "ספטמבר 2026",
        "manual",
    )
    assert c.get("/api/cashflow/2026/9").json()["income"] == 9000
    assert _get(c, ids["inc"])["cycle_shift"] == "previous"
    r = c.put(f"/api/transactions/{ids['inc']}/cycle", json={"target": "own"})
    assert (r.json()["cycle_shift"], r.json()["cycle_date_source"]) == (None, "manual")
    home_txn = c.get("/api/home/current").json()["income"]["fixed_groups"][0]["items"][0]
    assert home_txn["transactions"][0]["cycle_date_source"] == "manual"
    r = c.put(f"/api/transactions/{ids['inc']}/cycle", json={"target": "auto"})
    # Usually on the 9th, landed on the 11th, September has none -> automatically September's.
    assert (r.json()["cycle_shift"], r.json()["cycle_date_source"]) == ("previous", "auto")
    assert c.put(f"/api/transactions/{ids['inc']}/cycle", json={"target": "x"}).status_code == 422

    r = c.put(f"/api/recurring/{rid}/fixed", json={"expected_day": 12, "expected_amount": 9500})
    assert r.json()["expected_day"] == 12 and r.json()["amount_kind"] == "fixed"
    assert r.json()["user_defined"] is True
    r = c.delete(f"/api/recurring/{rid}/fixed")
    assert r.json()["status"] == "dismissed" and r.json()["user_defined"] is False
    assert _get(c, ids["inc"])["fixed_income_id"] is None


def test_account_holder_patch(data):
    c, ids, acct = data
    assert c.get("/api/accounts").json()[0]["holder"] == "שי"
    r = c.patch(f"/api/accounts/{acct}", json={"holder": " אורטל "})
    assert r.json()["holder"] == "אורטל"
    assert _get(c, ids["exp"])["account_holder"] == "אורטל"
    h = c.get("/api/home/current").json()
    assert h["variable"]["weeks"][1]["transactions"][0]["account_holder"] == "אורטל"
    assert c.patch(f"/api/accounts/{acct}", json={"holder": ""}).json()["holder"] == "שי"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/transactions/1/fixed-income"),
        ("put", "/api/transactions/1/cycle"),
        ("put", "/api/recurring/1/fixed"),
        ("delete", "/api/recurring/1/fixed"),
    ],
)
def test_requires_auth(client, method, path):
    assert (
        getattr(client, method)(path, **({} if method == "delete" else {"json": {}})).status_code
        == 401
    )
