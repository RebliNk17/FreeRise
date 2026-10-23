"""Savings plans, "חיפוש הוצאות" and "תרחישים" routes."""

import itertools
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from freerise.api.deps import today
from freerise.crypto import encrypt_json
from freerise.forecast.next_cycle import add_months
from freerise.models import Account, Category, Credential, Transaction

_seq = itertools.count()


@pytest.fixture
def acc(sf):
    with sf() as s:
        c = Credential(provider="onezero", label="b", owner="o", secret_enc=encrypt_json({}))
        live = Account(credential=c, provider_account_id="1", kind="card", display_name="c")
        off = Account(
            credential=c, provider_account_id="2", kind="bank", display_name="x", excluded=True
        )
        s.add_all([live, off])
        s.commit()
        cats = {cat.name: cat.id for cat in s.scalars(select(Category))}
        return {"live": live.id, "off": off.id, "cats": cats}


def _txn(sf, account_id, d, amount, desc, key=None, cat=None):
    with sf() as s:
        s.add(
            Transaction(
                account_id=account_id,
                txn_key=f"t{next(_seq)}",
                date=d,
                processed_date=d,
                amount=Decimal(str(amount)),
                description=desc,
                merchant_key=key if key is not None else desc,
                category_id=cat,
                status="completed",
                raw={},
            )
        )
        s.commit()


def test_plans_crud_and_contribute(authed):
    target = add_months(today(), 7)  # this cycle + 7 more = 8 (start day 10)
    r = authed.post(
        "/api/plans",
        json={"name": "חופשה", "target_amount": 6000, "target_date": target.isoformat()},
    )
    assert r.status_code == 201
    p = r.json()
    assert {"id", "months_left", "monthly_needed", "funded_this_cycle", "completed"} <= set(p)
    assert p["saved_amount"] == 0 and p["monthly_override"] is None
    n = p["months_left"]
    assert p["monthly_needed"] == -(-6000 // n)

    body = authed.get("/api/plans").json()
    assert (body["monthly_total"], body["active_count"]) == (p["monthly_needed"], 1)
    plan = authed.get("/api/plan/current").json()
    assert plan["goal_plans"] == p["monthly_needed"]
    assert plan["goal"] == plan["goal_personal"] + plan["goal_plans"]

    pid = p["id"]
    one = authed.post(f"/api/plans/{pid}/contribute").json()
    two = authed.post(f"/api/plans/{pid}/contribute").json()
    assert one == two and one["funded_this_cycle"]
    assert one["saved_amount"] == p["monthly_needed"] == one["monthly_needed"]
    start = authed.get("/api/home/current").json()["cycle"]["start"]
    undone = authed.delete(f"/api/plans/{pid}/contribute", params={"cycle_start": start}).json()
    assert not undone["funded_this_cycle"] and undone["saved_amount"] == 0
    assert authed.delete(f"/api/plans/{pid}/contribute").json() == undone  # no-op
    assert authed.post(f"/api/plans/{pid}/contribute").json() == one

    r = authed.patch(f"/api/plans/{pid}", json={"monthly_override": 1000, "name": "אילת"})
    assert (r.json()["monthly_override"], r.json()["name"]) == (1000, "אילת")
    r = authed.patch(f"/api/plans/{pid}", json={"monthly_override": None, "active": False})
    assert r.json()["monthly_override"] is None and not r.json()["active"]
    assert authed.get("/api/plans").json()["monthly_total"] == 0
    assert authed.post(f"/api/plans/{pid}/contribute").status_code == 409  # paused
    assert authed.post("/api/plans", json={"name": "", "target_amount": 0}).status_code == 422
    assert authed.delete(f"/api/plans/{pid}").status_code == 204
    assert authed.delete(f"/api/plans/{pid}").status_code == 404
    assert authed.post(f"/api/plans/{pid}/contribute").status_code == 404


def test_overdue_plan_leaves_the_goal(authed):
    past = (today() - timedelta(days=70)).isoformat()
    p = authed.post(
        "/api/plans", json={"name": "ישן", "target_amount": 500, "target_date": past}
    ).json()
    assert p["overdue"] and p["monthly_needed"] == 500
    assert authed.get("/api/plans").json()["monthly_total"] == 0
    assert authed.get("/api/plan/current").json()["goal_plans"] == 0


def test_cost_totals_filters_exclusions(authed, sf, acc):
    t = today()
    cats = acc["cats"]
    _txn(sf, acc["live"], t, -100, "WOLT תל אביב", key="wolt")
    _txn(sf, acc["live"], t - timedelta(days=40), -50.5, "WOLT", key="wolt")
    _txn(sf, acc["live"], t, -30, "100%_קפה", key="cafe")
    _txn(sf, acc["live"], t, 20, "WOLT זיכוי", key="wolt")  # refund: not an expense
    _txn(sf, acc["off"], t, -999, "WOLT", key="wolt")  # excluded account
    _txn(sf, acc["live"], t, -999, "WOLT", key="wolt", cat=cats["העברות"])
    _txn(sf, acc["live"], t, -999, "WOLT", key="wolt", cat=cats["חיוב כרטיס אשראי"])
    _txn(sf, acc["live"], t, -999, "WOLT", key="wolt", cat=cats["להתעלם"])

    r = authed.get("/api/cost", params={"q": "wolt"}).json()
    assert set(r) == {"total", "count", "monthly", "top_merchants", "avg_per_month"}
    assert (r["total"], r["count"]) == (150.5, 2)
    assert r["top_merchants"] == [
        {
            "merchant_key": "wolt",
            "sample": r["top_merchants"][0]["sample"],
            "total": 150.5,
            "count": 2,
        }
    ]
    assert sum(m["total"] for m in r["monthly"]) == 150.5
    assert r["avg_per_month"] == pytest.approx(150.5 / (41 / 30.44))  # 41 days in range
    assert {"label_year", "label_month", "total"} == set(r["monthly"][0])

    # LIKE wildcards are literal
    assert authed.get("/api/cost", params={"q": "100%_"}).json()["total"] == 30
    assert authed.get("/api/cost", params={"q": "W%T"}).json()["total"] == 0
    assert authed.get("/api/cost", params={"q": "0_"}).json()["count"] == 0
    r = authed.get("/api/cost", params={"from": t.isoformat(), "to": t.isoformat()}).json()
    assert (r["total"], r["count"], len(r["monthly"])) == (130, 2, 1)
    r = authed.get("/api/cost", params={"category_id": cats["העברות"]}).json()
    assert r["total"] == 0 and r["monthly"] == []


def test_cost_nets_refunds_and_skips_savings(authed, sf, acc):
    t, cats = today(), acc["cats"]
    _txn(sf, acc["live"], t, -300, "סופר", cat=cats["כלכלה"])
    _txn(sf, acc["live"], t, 50, "סופר זיכוי", cat=cats["כלכלה"])  # refund nets
    _txn(sf, acc["live"], t, 9000, "משכורת", cat=cats["משכורת"])  # income: not a refund
    _txn(sf, acc["live"], t, -1000, "פיקדון", cat=cats["השקעה וחיסכון"])
    r = authed.get("/api/cost").json()
    assert (r["total"], r["count"]) == (250, 2)
    r = authed.get("/api/cost", params={"category_id": cats["השקעה וחיסכון"]}).json()
    assert r["total"] == 1000


def test_whatif(authed):
    body = {
        "changes": [
            {"label": "חדר כושר", "monthly_amount": -250},
            {"label": "לבטל את נטפליקס", "monthly_amount": 50},
        ]
    }
    r = authed.post("/api/whatif", json=body).json()
    assert (r["monthly_delta"], r["yearly_impact"]) == (-200, -2400)
    b, s = r["baseline"], r["scenario"]
    assert set(b) == {"variable_allowance", "weekly_left", "month_end"}
    assert s["variable_allowance"] == b["variable_allowance"] - 200
    assert s["month_end"] == b["month_end"] - 200
    assert s["weekly_left"] < b["weekly_left"]
    assert authed.post("/api/whatif", json={"changes": []}).json()["yearly_impact"] == 0


def test_cost_no_data(authed):
    r = authed.get("/api/cost", params={"from": date(2026, 1, 1).isoformat()}).json()
    assert r["total"] == 0 and r["avg_per_month"] == 0
