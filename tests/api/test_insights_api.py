from decimal import Decimal

from sqlalchemy import select

from freerise.api.deps import today
from freerise.cashflow.cycles import cycle_for
from freerise.crypto import encrypt_json
from freerise.forecast.next_cycle import add_months
from freerise.models import Account, Category, Credential, Transaction


def _fee(sf, history=False):
    with sf() as s:
        c = Credential(provider="onezero", label="Bank", owner="o", secret_enc=encrypt_json({}))
        s.add(c)
        s.flush()
        a = Account(credential_id=c.id, provider_account_id="b", kind="bank", display_name="b")
        s.add(a)
        s.flush()
        t = today()
        cats = {c.name: c.id for c in s.scalars(select(Category))}
        for k in range(1, 7) if history else ():  # 6 past cycles, food up in the latest 3
            d = add_months(t, -k)
            for i, (amt, cat) in enumerate(
                ((5000, "משכורת"), (-1500 if k < 4 else -1000, "כלכלה"))
            ):
                s.add(
                    Transaction(
                        account_id=a.id,
                        txn_key=f"h{k}-{i}",
                        date=d,
                        processed_date=d,
                        amount=Decimal(amt),
                        description=cat,
                        merchant_key=cat,
                        category_id=cats[cat],
                        status="completed",
                        raw={},
                    )
                )
        s.add(
            Transaction(
                account_id=a.id,
                txn_key="fee",
                date=t,
                processed_date=t,
                amount=Decimal(-15),
                description="עמלה",
                merchant_key="עמלה",
                category_id=s.scalar(select(Category.id).where(Category.name == "עמלות")),
                status="completed",
                raw={},
            )
        )
        s.commit()
    return f"fees:{cycle_for(today(), 10).start}"


def test_insights_list_snooze_dismiss(authed, sf):
    key = _fee(sf)
    body = authed.get("/api/insights").json()
    [fee] = [i for i in body if i["key"] == key]
    assert set(fee) == {
        "key",
        "kind",
        "severity",
        "title",
        "body",
        "action_label",
        "link",
        "amount",
        "actions",
    }
    assert (fee["kind"], fee["severity"], fee["amount"]) == ("fees", "warning", 15.0)
    assert authed.post(f"/api/insights/{key}/snooze").status_code == 204
    assert key not in {i["key"] for i in authed.get("/api/insights").json()}
    assert authed.post(f"/api/insights/{key}/dismiss").status_code == 204
    assert key not in {i["key"] for i in authed.get("/api/insights").json()}
    assert authed.post("/api/insights/junk:1/dismiss").status_code == 404
    assert authed.post("/api/insights/fees:1999-01-10/snooze").status_code == 404


def test_progress_shape(authed, sf):
    _fee(sf, history=True)
    body = authed.get("/api/progress").json()
    assert set(body["cycles"][0]) == {"cycle", "net"}
    assert set(body["cycles"][0]["cycle"]) == {"start", "end", "label_year", "label_month"}
    assert body["increases"] == [
        {
            "category_id": body["increases"][0]["category_id"],
            "name": "כלכלה",
            "previous": 1000.0,
            "current": 1500.0,
            "change_pct": 0.5,
        }
    ]
    assert body["positive_cycles"] == 6 and body["since"]


def test_progress_empty(authed):
    body = authed.get("/api/progress").json()
    assert body == {
        "cycles": [],
        "avg_net": 0.0,
        "positive_cycles": 0,
        "savings_total": 0.0,
        "savings_avg": 0.0,
        "increases": [],
        "decreases": [],
        "cumulative_net": 0.0,
        "since": None,
    }
