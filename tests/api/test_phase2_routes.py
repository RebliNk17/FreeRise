import itertools
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, update

from freerise.api.deps import today
from freerise.cashflow.cycles import cycle_for
from freerise.crypto import encrypt_json
from freerise.models import (
    Account,
    Balance,
    Category,
    ClearingHouseReport,
    Credential,
    Fund,
    FundDeposit,
    FundSnapshot,
    MerchantRule,
    Notification,
    RecurringItem,
    Setting,
    Transaction,
)


@pytest.fixture
def ids(sf):
    """Bank + card account, a couple of categories by name. Cleans user-created categories."""
    with sf() as s:
        c = Credential(provider="onezero", label="Bank", owner="שי", secret_enc=encrypt_json({}))
        s.add(c)
        s.flush()
        bank = Account(
            credential_id=c.id, provider_account_id="b", kind="bank", display_name="עו״ש"
        )
        card = Account(
            credential_id=c.id, provider_account_id="c", kind="card", display_name="כרטיס"
        )
        s.add_all([bank, card])
        s.flush()
        cats = {cat.name: cat.id for cat in s.scalars(select(Category))}
        s.commit()
        out = {"bank": bank.id, "card": card.id, "cred": c.id, "cats": cats}
    yield out
    with sf() as s:
        s.execute(delete(Category).where(Category.name.like("test-%")))
        s.commit()


_seq = itertools.count()


def _txn(sf, account_id, d, amount, desc, key=None, cat=None, src=None):
    with sf() as s:
        t = Transaction(
            account_id=account_id,
            txn_key=f"t{next(_seq)}",
            date=d,
            processed_date=d,
            amount=Decimal(str(amount)),
            description=desc,
            merchant_key=key if key is not None else desc,
            category_id=cat,
            category_source=src,
            status="completed",
            raw={},
        )
        s.add(t)
        s.commit()
        return t.id


def test_categories_crud(authed, ids):
    cats = authed.get("/api/categories").json()
    assert {"id", "name", "group", "sort_order"} <= set(cats[0])
    r = authed.post("/api/categories", json={"name": "test-חיות", "group": "variable"})
    assert r.status_code == 200
    cid = r.json()["id"]
    r = authed.patch(f"/api/categories/{cid}", json={"group": "fixed"})
    assert r.json() == {"id": cid, "name": "test-חיות", "group": "fixed", "sort_order": 0}
    assert authed.post("/api/categories", json={"name": "x", "group": "bogus"}).status_code == 422
    assert authed.patch("/api/categories/99999", json={"name": "y"}).status_code == 404


def test_set_category_endpoint_remembers(authed, ids, sf):
    cid = ids["cats"]["אוכל בחוץ"]
    a = _txn(sf, ids["card"], date(2026, 9, 1), -50, "pizza")
    b = _txn(sf, ids["card"], date(2026, 9, 5), -40, "pizza")
    r = authed.put(f"/api/transactions/{a}/category", json={"category_id": cid})
    assert r.json() == {"changed": 1}
    rules = authed.get("/api/rules").json()
    rule = next(x for x in rules if x["pattern"] == "pizza")
    assert rule == {
        "id": rule["id"],
        "pattern": "pizza",
        "match": "exact",
        "category_id": cid,
        "category_name": "אוכל בחוץ",
        "source": "user",
    }
    with sf() as s:
        assert s.get(Transaction, b).category_id is None  # apply_to_past=false
    r = authed.put(
        f"/api/transactions/{a}/category", json={"category_id": cid, "apply_to_past": True}
    )
    assert r.json() == {"changed": 2}
    page = authed.get("/api/transactions", params={"category_id": cid}).json()
    assert {t["id"] for t in page["items"]} == {a, b}
    t = page["items"][0]
    assert t["category_name"] == "אוכל בחוץ" and t["merchant_key"] == "pizza"
    assert {t["category_source"] for t in page["items"]} == {"manual", "rule"}
    assert (
        authed.put("/api/transactions/99999/category", json={"category_id": cid}).status_code == 404
    )
    assert (
        authed.put(f"/api/transactions/{a}/category", json={"category_id": 99999}).status_code
        == 404
    )
    assert authed.delete(f"/api/rules/{rule['id']}").status_code == 204
    assert authed.delete(f"/api/rules/{rule['id']}").status_code == 404


def test_uncategorized_and_merchant_bulk(authed, ids, sf):
    cid = ids["cats"]["אוכל בחוץ"]
    other = ids["cats"]["כלכלה"]
    _txn(sf, ids["card"], date(2026, 9, 1), -30, "Falafel 1", key="falafel")
    _txn(sf, ids["card"], date(2026, 9, 2), -20, "Falafel 2", key="falafel")
    _txn(sf, ids["card"], date(2026, 9, 3), -10, "Falafel 3", key="falafel", cat=other, src="ai")
    manual = _txn(
        sf, ids["card"], date(2026, 9, 4), -5, "Falafel", key="falafel", cat=other, src="manual"
    )
    _txn(sf, ids["bank"], date(2026, 9, 2), -7, "Other")
    unc = authed.get("/api/categories/uncategorized").json()
    assert unc[0] == {
        "merchant_key": "falafel",
        "sample_description": "Falafel 1",
        "count": 2,
        "total": -50.0,
        "kind": "card",
    }
    assert (
        authed.get("/api/transactions", params={"uncategorized": True}).json()["items"].__len__()
        == 3
    )
    r = authed.put(
        "/api/categories/merchant",
        json={"merchant_key": "falafel", "category_id": cid, "apply_to_past": False},
    )
    assert r.json() == {"changed": 2}
    r = authed.put("/api/categories/merchant", json={"merchant_key": "falafel", "category_id": cid})
    assert r.json() == {"changed": 3}  # the two (already) + the ai one; manual untouched
    with sf() as s:
        assert s.get(Transaction, manual).category_id == other
        rule = s.scalar(select(MerchantRule).where(MerchantRule.pattern == "falafel"))
        assert (rule.category_id, rule.source, rule.match) == (cid, "user", "exact")
    assert [u["merchant_key"] for u in authed.get("/api/categories/uncategorized").json()] == [
        "Other"
    ]


def test_cashflow_endpoint_shape(authed, ids, sf):
    salary = ids["cats"]["משכורת"]
    _txn(sf, ids["bank"], date(2026, 9, 12), 10000, "salary", cat=salary)
    _txn(sf, ids["card"], date(2026, 9, 15), -300, "shop")
    r = authed.get("/api/cashflow/2026/9")
    assert r.status_code == 200
    body = r.json()
    assert body["cycle"] == {
        "start": "2026-09-10",
        "end": "2026-10-09",
        "label_year": 2026,
        "label_month": 9,
    }
    assert body["income"] == 10000.0 and body["spending"] == 300.0 and body["net"] == 9700.0
    assert body["verdict"] == "positive"
    assert [g["group"] for g in body["groups"]] == ["fixed", "variable", "savings", "income"]
    var = next(g for g in body["groups"] if g["group"] == "variable")
    assert var["categories"] == [
        {"category_id": None, "name": "לא מסווג", "total": 300.0, "count": 1}
    ]
    assert body["uncategorized_count"] == 1
    assert {"uncategorized_total", "pending_count", "basis"} <= set(body)
    assert body["income_fixed"] == 0.0 and body["income_variable"] == 10000.0
    assert len(body["history"]) == 6
    assert body["history"][-1] == {
        "label_year": 2026,
        "label_month": 9,
        "start": "2026-09-10",
        "end": "2026-10-09",
        "net": 9700.0,
    }
    assert body["history"][0]["label_month"] == 4
    cur = authed.get("/api/cashflow/current").json()
    c = cycle_for(today(), 10)
    assert cur["cycle"]["start"] == c.start.isoformat()
    assert authed.get("/api/cashflow/2026/13").status_code == 422


def test_cashflow_and_plan_fees(authed, ids, sf):
    t = today()
    tid = _txn(sf, ids["bank"], t, "-6.90", "עמלת פעולה 12 40", cat=ids["cats"]["עמלות"])
    c = cycle_for(t, 10)
    fees = authed.get(f"/api/cashflow/{c.label_month.year}/{c.label_month.month}").json()["fees"]
    assert fees == {
        "total": 6.9,
        "count": 1,
        "previous_total": 0.0,
        "items": [
            {
                "txn_id": tid,
                "date": t.isoformat(),
                "description": "עמלת פעולה 12 40",
                "account_id": ids["bank"],
                "account_name": "עו״ש",
                "merchant_key": "עמלת פעולה 12 40",
                "fee_key": "עמלת פעולה",
                "amount": 6.9,
            }
        ],
        "new_fee_merchants": ["עמלת פעולה"],
    }
    assert authed.get("/api/plan/current").json()["fees"] == {"total": 6.9, "count": 1}


def test_plan_current(authed, ids, sf):
    t = today()
    _txn(sf, ids["card"], t, -120, "groceries")
    with sf() as s:
        now = datetime.now(UTC)
        s.add(Balance(account_id=ids["bank"], as_of=now, balance=Decimal("5000.50")))
        s.commit()
    body = authed.get("/api/plan/current").json()
    assert body["today"] == t.isoformat()
    assert body["variable_spent"] == 120.0
    assert body["balances"]["bank_total"] == 5000.5
    assert body["balances"]["accounts"] == [
        {
            "id": ids["bank"],
            "display_name": "עו״ש",
            "balance": 5000.5,
            "as_of": body["balances"]["accounts"][0]["as_of"],
        }
    ]
    assert body["balances"]["upcoming_card_charges"] == 120.0  # no card balance -> txns
    assert sum(w["is_current"] for w in body["weeks"]) == 1
    assert set(body["next_cycle"]) == {"installments_stopping_total", "fixed_total", "income_total"}
    assert {"categories", "goal", "variable_left", "savings_spent"} <= set(body)
    with sf() as s:
        s.add(Balance(account_id=ids["card"], as_of=datetime.now(UTC), balance=Decimal(-900)))
        s.commit()
    assert authed.get("/api/plan/current").json()["balances"]["upcoming_card_charges"] == 900.0
    assert authed.put("/api/plan/goal", json={"amount": 1500}).json() == {"goal": 1500.0}
    assert authed.get("/api/plan/current").json()["goal"] == 1500.0
    assert authed.put("/api/plan/goal", json={"amount": -1}).status_code == 422


def test_forecast_and_recurring(authed, ids, sf):
    t = today()
    with sf() as s:
        item = RecurringItem(
            merchant_key="netflix",
            direction="expense",
            label="Netflix",
            category_id=ids["cats"]["כלכלה"],
            cadence="monthly",
            amount_kind="fixed",
            expected_amount=Decimal("49.90"),
            last_date=t,
            next_expected_date=t,
            basis="b",
        )
        s.add(item)
        s.commit()
        rid = item.id
    f = authed.get("/api/forecast/next").json()
    assert set(f) >= {
        "cycle",
        "fixed_total",
        "income_total",
        "installments_stopping_total",
        "delta_fixed_vs_current",
        "fixed_items",
        "income_items",
        "installments_stopping",
    }
    assert "label_year" in f["cycle"]
    rows = authed.get("/api/recurring", params={"status": "pending"}).json()
    assert rows[0]["id"] == rid and rows[0]["expected_amount"] == 49.9
    assert rows[0]["category_name"] == "כלכלה"
    r = authed.put(f"/api/recurring/{rid}", json={"status": "confirmed"})
    assert r.json()["status"] == "confirmed"
    assert authed.get("/api/recurring", params={"status": "pending"}).json() == []
    assert authed.put(f"/api/recurring/{rid}", json={"status": "nope"}).status_code == 422
    assert authed.put("/api/recurring/99999", json={"status": "dismissed"}).status_code == 404
    assert authed.post("/api/recurring/detect").json() == {"count": 0}


def test_charge_source_labels(authed, ids, sf):
    t = today()
    with sf() as s:
        cred = Credential(provider="isracard", label="ישראכרט", owner="o", secret_enc=b"s")
        old = Account(credential=cred, provider_account_id="1111", kind="card", display_name="x")
        new = Account(
            credential=cred, provider_account_id="2222", kind="card", display_name="ישראכרט 2222"
        )
        s.add_all([old, new])
        s.flush()
        s.add(
            RecurringItem(
                merchant_key="netflix",
                direction="expense",
                label="Netflix",
                cadence="monthly",
                amount_kind="fixed",
                expected_amount=Decimal("49.90"),
                last_date=t,
                next_expected_date=t,
                status="confirmed",
                basis="b",
                account_id=new.id,
                previous_account_id=old.id,
                account_changed_on=t,
            )
        )
        s.commit()
        new_id = new.id
    _txn(sf, new_id, t, -10, "shop")
    assert (
        authed.get("/api/transactions").json()["items"][0]["account_name"]
        == "ישראכרט \u2066••2222\u2069"
    )
    [r] = authed.get("/api/recurring").json()
    assert (r["account_id"], r["account_label"], r["previous_account_label"]) == (
        new_id,
        "ישראכרט \u2066••2222\u2069",
        "x",
    )
    lines = authed.get("/api/plan/current").json()["still_expected"]
    line = next(x for x in lines if x["label"] == "Netflix")
    assert (line["account_label"], line["previous_account_label"]) == (
        "ישראכרט \u2066••2222\u2069",
        "x",
    )
    for x in authed.get("/api/forecast/next").json()["fixed_items"]:
        assert {"account_id", "account_label", "previous_account_label"} <= set(x)


def test_pension_funds(authed, sf):
    with sf() as s:
        c = Credential(provider="mislaka", label="מסלקה", owner="שי", secret_enc=encrypt_json({}))
        s.add(c)
        s.flush()
        f = Fund(
            credential_id=c.id,
            policy_id="P1",
            product_type="pension",
            name="מקיפה",
            company="מגדל",
            fee_deposit_pct=Decimal("1.5"),
            fee_savings_pct=Decimal("0.22"),
            tracks=[{"name": "כללי"}],
            details={"monthly_pension_forecast": 9100.5},
            owner="שי",
        )
        s.add(f)
        s.flush()
        s.add_all(
            [
                FundSnapshot(fund_id=f.id, as_of=date(2025, 12, 31), balance=Decimal(100000)),
                FundSnapshot(fund_id=f.id, as_of=date(2026, 6, 30), balance=Decimal(110000)),
                FundDeposit(fund_id=f.id, date=date(2026, 3, 1), amount=Decimal(2000)),
                ClearingHouseReport(
                    credential_id=c.id,
                    report_month=date(2026, 5, 1),
                    data={"calc_date": "2026-05-31", "forecast_monthly_pension": 1.0},
                ),
                ClearingHouseReport(
                    credential_id=c.id,
                    report_month=date(2026, 6, 1),
                    data={
                        "calc_date": "2026-06-30",
                        "total_savings": 110000.0,
                        "forecast_total_balance": 2400000.0,
                        "forecast_monthly_pension": 9100.5,
                        "forecast_lump_sum": 350000.0,
                    },
                ),
            ]
        )
        s.commit()
        fid, cid = f.id, c.id
    body = authed.get("/api/pension/funds").json()
    assert body["total"] == 110000.0 and body["as_of"] == "2026-06-30"
    fund = body["funds"][0]
    assert fund["id"] == fid and fund["latest_balance"] == 110000.0
    assert fund["ytd_profit"] == 8000.0 and 0 < fund["ytd_return_pct"] < 1
    assert fund["fee_deposit_pct"] == 1.5
    assert fund["forecast_monthly_pension"] == 9100.5
    [fc] = body["forecast"]
    assert fc["credential_id"] == cid and fc["owner"] == "שי"
    assert fc["report_month"] == "2026-06-01" and fc["forecast_monthly_pension"] == 9100.5
    assert fc["forecast_lump_sum"] == 350000.0 and fc["forecast_total_balance"] == 2400000.0
    assert fc["total_savings"] == 110000.0 and "raw" not in fc
    assert fund["monthly"][-1] == {"date": "2026-06-30", "balance": 110000.0}
    assert body["credentials"] == [
        {"id": cid, "label": "מסלקה", "owner": "שי", "last_success_at": None}
    ]
    d = authed.get(f"/api/pension/funds/{fid}").json()
    assert d["fund"] == fund
    assert d["yearly"][-1]["year"] == 2026 and d["yearly"][-1]["deposits"] == 2000.0
    assert d["deposits"] == [{"date": "2026-03-01", "amount": 2000.0}]
    assert d["tracks"] == [{"name": "כללי"}]
    assert authed.get("/api/pension/funds/99999").status_code == 404
    with sf() as s:  # a non-numeric portal value must not 500 the list
        s.get(Fund, fid).details = {"monthly_pension_forecast": "n/a"}
        s.commit()
    assert authed.get("/api/pension/funds").json()["funds"][0]["forecast_monthly_pension"] is None


def test_notifications_read_flow(authed, sf):
    with sf() as s:
        for i in range(3):
            s.add(
                Notification(
                    kind="k", title=f"t{i}", body="b", dedup_key=f"d{i}", severity="warning"
                )
            )
        s.commit()
    rows = authed.get("/api/notifications").json()
    assert len(rows) == 3 and rows[0]["title"] == "t2"  # newest first
    assert set(rows[0]) == {
        "id",
        "created_at",
        "kind",
        "severity",
        "title",
        "body",
        "link",
        "read_at",
    }
    assert authed.get("/api/notifications/unread-count").json() == {"count": 3}
    assert authed.post(f"/api/notifications/{rows[0]['id']}/read").status_code == 204
    assert authed.get("/api/notifications/unread-count").json() == {"count": 2}
    assert len(authed.get("/api/notifications", params={"unread_only": True}).json()) == 2
    assert len(authed.get("/api/notifications", params={"limit": 1}).json()) == 1
    assert authed.post("/api/notifications/99999/read").status_code == 404
    assert authed.post("/api/notifications/read-all").status_code == 204
    assert authed.get("/api/notifications/unread-count").json() == {"count": 0}


@pytest.fixture
def restore_settings(sf):
    with sf() as s:
        saved = {x.key: x.value for x in s.scalars(select(Setting))}
    yield
    with sf() as s:
        for k, v in saved.items():
            s.execute(update(Setting).where(Setting.key == k).values(value=v))
        s.commit()


def test_settings_validation(authed, restore_settings):
    assert authed.get("/api/settings").json() == {
        "cycle_start_day": 10,
        "month_end_goal_default": 0,
        "income_grace_days": 10,
    }
    for bad in ({"cycle_start_day": 0}, {"cycle_start_day": 29}, {"month_end_goal_default": -5}):
        assert authed.put("/api/settings", json=bad).status_code == 422
    r = authed.put("/api/settings", json={"cycle_start_day": 15})
    assert r.json() == {"cycle_start_day": 15, "month_end_goal_default": 0, "income_grace_days": 10}
    r = authed.put("/api/settings", json={"month_end_goal_default": 2000.5})
    assert r.json() == {
        "cycle_start_day": 15,
        "month_end_goal_default": 2000.5,
        "income_grace_days": 10,
    }
    assert authed.get("/api/cashflow/2026/9").json()["cycle"]["start"] == "2026-09-15"
