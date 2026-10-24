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
    # 20120 income − 5000 − 3000 − 2900 reserved; this week: the uncategorized ₪40 only
    assert h["variable"]["allowance"] == 9220
    assert cur["spent"] == 40


def test_installments_are_fixed(session):
    """Installment payments are fixed (known in advance), whatever their category; listed
    under one "תשלומים" group with n/N; expected = the payments due this cycle."""
    _, ids = _setup(session)
    card = _acct(session, "5678")
    inst = {"installment_total": 6}
    # תשלומים: 2/6 last cycle, 3/6 this cycle (charged)
    _tx(
        session,
        card,
        date(2026, 9, 12),
        -1900,
        "תשלומים",
        key="sochachei",
        installment_number=2,
        **inst,
    )
    sochachei = _tx(
        session,
        card,
        date(2026, 10, 12),
        -1900,
        "תשלומים",
        key="sochachei",
        installment_number=3,
        **inst,
    )
    # a hotel paid in 3, categorized תיירות: 2/3 charged this week
    _tx(
        session,
        card,
        date(2026, 9, 20),
        -800,
        "תיירות",
        key="hotel",
        installment_number=1,
        installment_total=3,
    )
    hotel = _tx(
        session,
        card,
        date(2026, 10, 20),
        -800,
        "תיירות",
        key="hotel",
        installment_number=2,
        installment_total=3,
    )
    # a sofa paid in 10, uncategorized: 4/10 last cycle -> 5/10 due on 25.10 (not charged yet)
    _tx(
        session,
        card,
        date(2026, 9, 25),
        -500,
        key="sofa",
        installment_number=4,
        installment_total=10,
    )
    ids += [sochachei.id, hotel.id]
    h = _home(session)
    b, _, cur = _check(h, ids)

    g = next(g for g in h["fixed"]["groups"] if g["name"] == "תשלומים")
    assert sorted(t["id"] for t in b["fixed:תשלומים"]) == sorted([sochachei.id, hotel.id])
    assert {t["category_name"] for t in b["fixed:תשלומים"]} == {"תשלומים", "תיירות"}
    items = {i["label"]: i for i in g["items"]}
    assert (items["sochachei"]["installment_number"], items["sochachei"]["installment_total"]) == (
        3,
        6,
    )
    assert (items["hotel"]["installment_number"], items["hotel"]["installment_total"]) == (2, 3)
    sofa = items["sofa"]
    assert (sofa["status"], sofa["installment_number"], sofa["installment_total"]) == (
        "expected",
        5,
        10,
    )
    assert (g["spent"], g["expected"]) == (2700, 3200)  # charged + the sofa's 5th payment
    assert g["category_id"] == _cat(session, "תשלומים")
    # nothing of it in variable spending, tracked cards or the weekly allowance
    assert h["variable"]["spent"] == 190
    assert "תשלומים" not in {c["name"] for c in h["tracked"]}
    assert "תשלומים" not in {c["name"] for c in h["untracked_available"]}
    assert h["variable"]["allowance"] == 9220 - 3200  # fixed is 3200 bigger
    assert cur["spent"] == 40


def test_installments_category_is_fixed(session):
    from sqlalchemy import select

    from freerise.models import Category

    assert session.scalar(select(Category.group).where(Category.name == "תשלומים")) == "fixed"
