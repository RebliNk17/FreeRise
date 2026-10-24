"""Every expense counts exactly once on home, and the month adds up (RiseUp's rule: fixed,
each tracked category, and the rest of variable spending are disjoint buckets)."""

from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from test_home import OCT, _acct, _cat, _home, _rec, _tx

from freerise.cashflow.plan import set_goal
from freerise.models import CategoryBudget


def _buckets(h) -> dict[str, list[dict]]:
    """Every list of transactions on home, by the card that counts it."""
    out = {
        "variable": [t for w in h["variable"]["weeks"] for t in w["transactions"]],
        "savings": h["savings"]["transactions"],
        "income_variable": h["income"]["variable"]["transactions"],
    }
    for c in h["tracked"]:
        out[f"tracked:{c['name']}"] = c["transactions"]
    for kind, groups in (("fixed", h["fixed"]["groups"]), ("income", h["income"]["fixed_groups"])):
        for g in groups:
            out[f"{kind}:{g['name']}"] = [t for i in g["items"] for t in i["transactions"]]
    return out


def _spent(ts) -> float:
    return -sum(t["amount"] for t in ts)


def _setup(s):
    a = _acct(s, kind="bank")
    _rec(s, "salary", "משכורת", 20000, date(2026, 11, 11), direction="income")
    ids = [
        _tx(s, a, date(2026, 10, 11), 20000, "משכורת", key="salary").id,
        _tx(s, a, date(2026, 10, 11), -5000, "משכנתא", key="loan").id,
        _tx(s, a, date(2026, 10, 15), -1000, "השקעה וחיסכון", key="dep").id,
        _tx(s, a, date(2026, 10, 12), -300, "כלכלה", key="shufersal").id,
        _tx(s, a, date(2026, 10, 19), -200, "כלכלה", key="shufersal").id,
        _tx(s, a, date(2026, 10, 20), -900, "אוכל בחוץ", key="rest").id,  # over its budget
        _tx(s, a, date(2026, 10, 13), -150, "קניות", key="zara").id,  # not tracked
        _tx(s, a, date(2026, 10, 21), -40, key="unknown").id,  # uncategorized
        _tx(s, a, date(2026, 10, 14), 120, "הכנסות אחרות", key="gift").id,
    ]
    for name, amount in (("כלכלה", 2000), ("אוכל בחוץ", 500)):
        s.add(CategoryBudget(cycle_start=OCT.start, category_id=_cat(s, name), amount=amount))
    set_goal(s, OCT, Decimal(3000))
    return a, ids


def _check(h, ids):
    b = _buckets(h)
    seen = Counter(t["id"] for ts in b.values() for t in ts)
    assert sorted(seen) == sorted(ids) and set(seen.values()) == {1}, seen

    assert h["variable"]["spent"] == pytest.approx(_spent(b["variable"]))
    assert h["fixed"]["spent"] == pytest.approx(
        sum(_spent(v) for k, v in b.items() if k.startswith("fixed:"))
    )
    for c in h["tracked"]:
        assert c["spent"] == pytest.approx(_spent(c["transactions"]))
    assert h["total"]["spent"] == pytest.approx(
        h["fixed"]["spent"]
        + sum(c["spent"] for c in h["tracked"])
        + h["variable"]["spent"]
        + h["savings"]["spent"]
    )

    # month: income − fixed − goal = tracked (expected, or spent when over) + the rest
    reserved = sum(max(c["expected"], c["spent"]) for c in h["tracked"])
    s = h["summary"]
    assert s["variable_allowance"] == pytest.approx(
        h["income"]["expected"] - h["fixed"]["expected"] - s["goal"]
    )
    assert h["variable"]["allowance"] == pytest.approx(s["variable_allowance"] - reserved)
    assert h["total"]["expected"] == pytest.approx(
        h["fixed"]["expected"] + reserved + h["variable"]["allowance"] + h["savings"]["expected"]
    )
    cur = next(w for w in h["variable"]["weeks"] if w["is_current"])
    assert s["week_left"] == pytest.approx(cur["expected"] - cur["spent"])
    return b, reserved, cur


def test_every_txn_counted_once_and_totals_balance(session):
    _, ids = _setup(session)
    h = _home(session)
    b, reserved, cur = _check(h, ids)
    assert {t["category_name"] for t in b["variable"]} == {"קניות", None}
    tracked = {c["name"]: c for c in h["tracked"]}
    assert (tracked["כלכלה"]["spent"], tracked["כלכלה"]["expected"]) == (500, 2000)
    assert (tracked["אוכל בחוץ"]["spent"], tracked["אוכל בחוץ"]["expected"]) == (900, 500)
    assert reserved == 2000 + 900
    assert h["variable"]["spent"] == 190
    # 20120 income − 5000 − 3000 − 2900 reserved; this week's spending is the uncategorized ₪40 only
    assert h["variable"]["allowance"] == 9220
    assert cur["spent"] == 40
