from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from freerise.cashflow.cycles import cycle_by_label
from freerise.cashflow.plan import set_goal
from freerise.insights import engine
from freerise.insights.engine import compute_insights, dismiss, snooze
from freerise.insights.progress import progress
from freerise.models import (
    Account,
    Balance,
    Category,
    Credential,
    InsightState,
    Notification,
    RecurringItem,
    Transaction,
)
from freerise.notify.rules import generate_notifications

TODAY = date(2026, 10, 23)  # cycle 10.10-9.11: day 14 of 31
OCT = cycle_by_label(2026, 10, 10)
_n = 0


def _acct(session, kind="bank", balance=None):
    cred = Credential(provider="x", label="l", owner="o", secret_enc=b"s")
    a = Account(credential=cred, provider_account_id=f"{kind}{_n}", kind=kind, display_name="a")
    session.add(a)
    session.flush()
    if balance is not None:
        session.add(Balance(account_id=a.id, as_of=datetime.now(UTC), balance=Decimal(balance)))
        session.flush()
    return a


def _tx(session, a, d, amount, cat=None, key="m"):
    global _n
    _n += 1
    cid = session.scalar(select(Category.id).where(Category.name == cat)) if cat else None
    session.add(
        Transaction(
            account_id=a.id,
            txn_key=f"i{_n}",
            date=d,
            processed_date=d,
            amount=Decimal(str(amount)),
            description=key,
            merchant_key=key,
            category_id=cid,
            status="completed",
            raw={},
        )
    )
    session.flush()


def _rec(session, key, direction, amount, next_date, kind="fixed", account=None):
    session.add(
        RecurringItem(
            account_id=account and account.id,
            merchant_key=key,
            direction=direction,
            label=key,
            cadence="monthly",
            amount_kind=kind,
            expected_amount=Decimal(amount),
            last_date=next_date - timedelta(days=30),
            next_expected_date=next_date,
            status="confirmed",
            basis="b",
        )
    )
    session.flush()


def _history(session, a, income=10000, fixed=3000, food=1000, out=1000, months=range(4, 10)):
    for m in months:  # cycles Apr..Sep 2026, all complete
        _tx(session, a, date(2026, m, 15), income, "משכורת")
        _tx(session, a, date(2026, m, 16), -fixed, "משכנתא")
        _tx(session, a, date(2026, m, 17), -food, "כלכלה")
        _tx(session, a, date(2026, m, 18), -out, "אוכל בחוץ")


def _kinds(session, today=TODAY):
    return {i.kind: i for i in engine.run(session, today)}


def test_negative_cycle(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 11), 10000, "משכורת")
    _tx(session, a, date(2026, 10, 12), -9000, "משכנתא")
    _tx(session, a, date(2026, 10, 13), -2000, "כלכלה")
    i = _kinds(session)["negative_cycle"]
    # 10000 − 9000 − 2000 − 2000/14 × 17 days left
    assert i.severity == "warning" and i.amount.quantize(Decimal(1)) == Decimal(3429)
    assert i.key == "negative_cycle:2026-10-10"


def test_negative_cycle_quiet_when_income_covers(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 11), 20000, "משכורת")
    _tx(session, a, date(2026, 10, 13), -2000, "כלכלה")
    assert "negative_cycle" not in _kinds(session)


def test_low_balance_before_income(session):
    bank = _acct(session, balance=1000)
    card = _acct(session, "card", balance=-400)  # upcoming card bill
    off = _acct(session, balance=50000)
    off.excluded = True
    _rec(session, "mortgage", "expense", 3000, date(2026, 10, 30), account=bank)
    _rec(session, "late", "expense", 500, date(2026, 11, 5), account=bank)  # after payday
    _rec(session, "gym", "expense", 700, date(2026, 10, 25), account=card)  # in the card bill
    _rec(session, "salary", "income", 15000, date(2026, 11, 1))
    i = _kinds(session)["low_balance_before_income"]
    assert i.amount == Decimal(2400) and "01.11" in i.body  # 1000 − 3000 − 400


def test_low_balance_late_income_counts_from_today(session):
    bank = _acct(session, balance=100)
    _rec(session, "rent", "expense", 300, date(2026, 10, 20), account=bank)  # overdue, pending
    _rec(session, "salary", "income", 15000, date(2026, 10, 18))  # late, still expected
    i = _kinds(session)["low_balance_before_income"]
    assert i.amount == Decimal(200) and "23.10" in i.body


def test_low_balance_quiet(session):
    a = _acct(session, balance=5000)
    _rec(session, "mortgage", "expense", 3000, date(2026, 10, 30), account=a)
    assert "low_balance_before_income" not in _kinds(session)
    session.query(Balance).delete()
    assert "low_balance_before_income" not in _kinds(session)  # no balance known


def test_idle_cash(session):
    a = _acct(session, balance=30000)
    _history(session, a)  # spending 5000 a month -> cushion 10000
    for m in range(4, 10):  # savings deposits are not spending the cushion has to cover
        _tx(session, a, date(2026, m, 20), -3000, "השקעה וחיסכון")
    i = _kinds(session)["idle_cash"]
    assert i.severity == "positive" and i.amount == Decimal(20000)
    assert i.key == "idle_cash:4"


def test_idle_cash_rounds_down_and_quiet_below_cushion(session):
    a = _acct(session, balance=10400)
    _history(session, a)
    assert "idle_cash" not in _kinds(session)  # 400 over the cushion rounds down to 0
    session.query(Balance).update({"balance": Decimal(11400)})
    assert _kinds(session)["idle_cash"].amount == Decimal(1000)


def test_no_goal(session):
    assert _kinds(session, date(2026, 10, 15))["no_goal"].link == "/home#goal"
    assert "no_goal" not in _kinds(session, TODAY)  # day 14 > 10
    set_goal(session, OCT, Decimal(1000))
    assert "no_goal" not in _kinds(session, date(2026, 10, 15))


def test_goal_on_track_and_at_risk(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 11), 20000, "משכורת")
    _tx(session, a, date(2026, 10, 12), -5000, "משכנתא")
    _tx(session, a, date(2026, 10, 13), -1400, "כלכלה")  # 100/day -> 1700 more
    set_goal(session, OCT, Decimal(1000))
    assert _kinds(session)["goal_on_track"].amount == Decimal(10900)
    set_goal(session, OCT, Decimal(15000))
    got = _kinds(session)
    assert "goal_on_track" not in got
    assert got["goal_at_risk"].amount == Decimal(3100)
    _tx(session, a, date(2026, 10, 14), -20000, "משכנתא")  # ends negative
    got = _kinds(session)
    assert "negative_cycle" in got and "goal_at_risk" not in got


def test_no_goal_carries_personal_goal_only(session):
    from freerise.models import SavingsPlan

    set_goal(session, cycle_by_label(2026, 9, 10), Decimal(1000))
    session.add(
        SavingsPlan(
            name="p",
            target_amount=Decimal(6000),
            target_date=date(2027, 5, 20),
            saved_amount=Decimal(0),
            active=True,
        )
    )
    session.flush()
    assert "₪1,000" in _kinds(session, date(2026, 10, 15))["no_goal"].body


def test_category_trend_up_and_down(session):
    a = _acct(session)
    _history(session, a)
    _tx(session, a, date(2026, 10, 12), -1500, "כלכלה")  # pace 3321 vs 1000
    _tx(session, a, date(2026, 10, 12), -100, "אוכל בחוץ")
    got = _kinds(session)
    assert got["category_up"].title.startswith("סופר") and got["category_up"].severity == "warning"
    assert "category_down" not in got  # too early in the cycle for a decrease
    got = _kinds(session, date(2026, 10, 30))
    assert got["category_down"].severity == "positive"
    assert got["category_down"].key.startswith("category_down:2026-10-10:")


def test_category_trend_quiet_at_normal_pace(session):
    a = _acct(session)
    _history(session, a)
    _tx(session, a, date(2026, 10, 12), -450, "כלכלה")
    _tx(session, a, date(2026, 10, 12), -450, "אוכל בחוץ")
    got = _kinds(session)
    assert "category_up" not in got and "category_down" not in got


def test_saving_capacity_and_fixed_heavy(session):
    a = _acct(session)
    for m in range(4, 10):
        _tx(session, a, date(2026, m, 15), 10000, "משכורת")
        _tx(session, a, date(2026, m, 16), -7000, "משכנתא")
        _tx(session, a, date(2026, m, 17), -400 if m % 2 else -600, "כלכלה")
    got = _kinds(session)
    assert got["saving_capacity"].amount == Decimal(2400)
    assert "₪2,400" in got["saving_capacity"].body
    assert got["fixed_heavy"].severity == "warning" and "70%" in got["fixed_heavy"].body
    # standing insights: same key next cycle, so a dismiss sticks
    assert got["fixed_heavy"].key == "fixed_heavy:70"
    assert got["saving_capacity"].key == "saving_capacity:2000"
    nxt = _kinds(session, date(2026, 10, 30))
    assert nxt["fixed_heavy"].key == got["fixed_heavy"].key
    assert nxt["saving_capacity"].key == got["saving_capacity"].key
    set_goal(session, OCT, Decimal(1000))  # suggest only what the goal doesn't cover
    assert _kinds(session)["saving_capacity"].amount == Decimal(1400)
    set_goal(session, OCT, Decimal(2400))
    assert "saving_capacity" not in _kinds(session)


def test_saving_and_fixed_quiet(session):
    assert not {"saving_capacity", "fixed_heavy"} & set(_kinds(session))
    a = _acct(session)
    _history(session, a, income=4000)  # nets negative; fixed is 75% of income
    got = _kinds(session)
    assert "saving_capacity" not in got and "fixed_heavy" in got


def test_fees(session):
    a = _acct(session)
    assert "fees" not in _kinds(session)
    _tx(session, a, date(2026, 10, 12), -15, "עמלות")
    i = _kinds(session)["fees"]
    assert i.amount == Decimal(15) and i.link == "/cashflow/2026/10"


def test_unknown_card(session):
    a = _acct(session)
    _tx(session, a, date(2026, 9, 1), -700, "חיוב כרטיס אשראי", "old card")  # > 45 days
    assert "unknown_card" not in _kinds(session)
    _tx(session, a, date(2026, 10, 2), -610, "חיוב כרטיס אשראי", "חיוב כרטיס פרימיום")
    i = _kinds(session)["unknown_card"]
    assert i.amount == Decimal(610) and i.link == "/reconcile/2026/9"  # the bill's cycle


def test_variable_income_expected(session):
    _rec(session, "bonus", "income", 3000, date(2026, 11, 1), kind="fixed")
    assert "variable_income_expected" not in _kinds(session)
    _rec(session, "freelance", "income", 4000, date(2026, 11, 1), kind="variable")
    i = _kinds(session)["variable_income_expected"]
    assert i.severity == "info" and i.amount == Decimal(4000)
    assert i.body.startswith("ההכנסה מהמקורות: freelance משתנה")
    rid = session.scalar(select(RecurringItem.id).where(RecurringItem.merchant_key == "freelance"))
    assert i.key == f"variable_income_expected:{rid}"


def test_failing_rule_does_not_hide_others(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 12), -15, "עמלות")

    def broken(ctx):
        raise RuntimeError("boom")

    got = engine.run(session, TODAY, (broken, engine.fees))
    assert [i.kind for i in got] == ["fees"]


def test_order_and_cap(session):
    a = _acct(session, balance=1000)
    _history(session, a, income=4000)
    _tx(session, a, date(2026, 10, 12), -15, "עמלות")
    _tx(session, a, date(2026, 10, 12), -3000, "כלכלה")
    _rec(session, "freelance", "income", 4000, date(2026, 11, 1), kind="variable")
    got = compute_insights(session, date(2026, 10, 15))
    sev = [i.severity for i in got]
    assert sev == sorted(sev, key=engine.ORDER.get) and len(got) <= engine.CAP
    warnings = [i.amount for i in got if i.severity == "warning"]
    assert warnings == sorted(warnings, reverse=True)


def test_snooze_and_dismiss(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 12), -15, "עמלות")
    _tx(session, a, date(2026, 10, 12), 20000, "משכורת")
    keys = lambda t=TODAY: {i.key for i in compute_insights(session, t)}
    assert "fees:2026-10-10" in keys()
    snooze(session, "fees:2026-10-10")
    assert "fees:2026-10-10" not in keys()
    st = session.scalar(select(InsightState).where(InsightState.key == "fees:2026-10-10"))
    st.dismissed_until = datetime.now(UTC) - timedelta(minutes=1)  # snooze over
    session.flush()
    assert "fees:2026-10-10" in keys()
    dismiss(session, "fees:2026-10-10")
    assert "fees:2026-10-10" not in keys()
    # Next cycle has a new key, so a dismissed insight comes back.
    _tx(session, a, date(2026, 11, 12), -15, "עמלות")
    assert "fees:2026-11-10" in keys(date(2026, 11, 20))


def test_warning_insights_notify_once_per_cycle(session):
    a = _acct(session, balance=100)
    _tx(session, a, date(2026, 10, 11), 1000, "משכורת")
    _tx(session, a, date(2026, 10, 12), -2000, "משכנתא")
    _rec(session, "rent", "expense", 3000, date(2026, 10, 30), account=a)
    generate_notifications(session, TODAY)
    generate_notifications(session, date(2026, 10, 25))
    kinds = [n.kind for n in session.scalars(select(Notification))]
    assert kinds.count("negative_cycle") == 1
    assert kinds.count("low_balance_before_income") == 1
    n = session.scalar(select(Notification).where(Notification.kind == "negative_cycle"))
    assert n.severity == "warning" and n.dedup_key == "insight:negative_cycle:2026-10-10"


def test_dismissed_insight_does_not_notify(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 11), 1000, "משכורת")
    _tx(session, a, date(2026, 10, 12), -2000, "משכנתא")
    dismiss(session, "negative_cycle:2026-10-10")
    generate_notifications(session, TODAY)
    kinds = [n.kind for n in session.scalars(select(Notification))]
    assert "negative_cycle" not in kinds


def test_stale_states_pruned(session):
    session.add(InsightState(key="old", dismissed=True))
    session.flush()
    session.query(InsightState).update({"updated_at": datetime.now(UTC) - timedelta(days=121)})
    snooze(session, "fees:2026-10-10")
    assert {s.key for s in session.scalars(select(InsightState))} == {"fees:2026-10-10"}


def test_progress_numbers(session):
    a = _acct(session)
    _tx(session, a, date(2026, 3, 15), 1000, "משכורת")  # older than the 6-cycle window
    for m in range(4, 10):
        later = m >= 7
        _tx(session, a, date(2026, m, 15), 5000 if m == 9 else 10000, "משכורת")
        _tx(session, a, date(2026, m, 16), -3000, "משכנתא")
        _tx(session, a, date(2026, m, 17), -1600 if later else -1000, "כלכלה")
        _tx(session, a, date(2026, m, 18), -500 if later else -1000, "אוכל בחוץ")
        _tx(session, a, date(2026, m, 19), -500, "השקעה וחיסכון")
    _tx(session, a, date(2026, 10, 12), 99999, "משכורת")  # current cycle: not counted
    p = progress(session, TODAY)
    assert [n for _, n in p.cycles] == [4500, 4500, 4500, 4400, 4400, -600]
    assert p.cycles[0][0].start == date(2026, 4, 10)
    assert p.avg_net.quantize(Decimal("0.01")) == Decimal("3616.67")
    assert p.positive_cycles == 5
    assert (p.savings_total, p.savings_avg) == (3000, 500)
    [up] = p.increases
    [down] = p.decreases
    assert (up.name, up.previous, up.current, up.change_pct) == (
        "כלכלה",
        1000,
        1600,
        Decimal("0.6"),
    )
    assert (down.name, down.change_pct) == ("אוכל בחוץ", Decimal("-0.5"))
    assert p.cumulative_net == 22700
    assert p.since == date(2026, 3, 15)


def test_progress_empty(session):
    p = progress(session, TODAY)
    assert p.cycles == [] and p.avg_net == 0 and p.cumulative_net == 0 and p.since is None
    assert p.increases == p.decreases == []
