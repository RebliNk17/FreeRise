from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from freerise.cashflow.cycles import cycle_by_label
from freerise.cashflow.plan import cycle_plan, get_goal, set_goal, split_by_days
from freerise.forecast.next_cycle import expected_in_cycle
from freerise.models import Account, Category, Credential, RecurringItem, Transaction

OCT = cycle_by_label(2026, 10, 10)  # 10.10 (Sat) - 9.11
_n = 0


def _acct(session):
    cred = Credential(provider="x", label="l", owner="o", secret_enc=b"s")
    a = Account(credential=cred, provider_account_id="1", kind="bank", display_name="a")
    session.add(a)
    session.flush()
    return a


def _cat(session, name):
    return session.scalar(select(Category.id).where(Category.name == name))


def _tx(session, a, d, amount, cat=None, key="m"):
    global _n
    _n += 1
    session.add(
        Transaction(
            account_id=a.id,
            txn_key=f"p{_n}",
            date=d,
            processed_date=d,
            amount=Decimal(str(amount)),
            description=key,
            merchant_key=key,
            category_id=_cat(session, cat) if cat else None,
            status="completed",
            raw={},
        )
    )
    session.flush()


def test_allowance_formula(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 11), 20000, "משכורת")
    _tx(session, a, date(2026, 10, 12), -12000, "משכנתא")
    _tx(session, a, date(2026, 10, 13), -500, "כלכלה")
    set_goal(session, OCT, Decimal(1000))
    p = cycle_plan(session, date(2026, 10, 23))
    assert (p.expected_income, p.expected_fixed, p.goal) == (20000, 12000, 1000)
    assert p.variable_allowance == Decimal(7000)
    assert (p.variable_spent, p.variable_left) == (Decimal(500), Decimal(6500))
    assert p.basis


def test_expected_income_uses_stream_before_payday(session):
    session.add(
        RecurringItem(
            merchant_key="salary",
            direction="income",
            label="משכורת",
            cadence="monthly",
            amount_kind="fixed",
            expected_amount=Decimal(15000),
            last_date=date(2026, 10, 1),
            next_expected_date=date(2026, 11, 1),
            status="confirmed",
            basis="b",
        )
    )
    session.flush()
    p = cycle_plan(session, date(2026, 10, 23))
    assert p.expected_income == Decimal(15000)


def test_week_split_rolls_forward(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 10), 20000, "משכורת")
    _tx(session, a, date(2026, 10, 10), -12000, "משכנתא")
    _tx(session, a, date(2026, 10, 14), -2000, "כלכלה")  # overspend in week 11-17
    _tx(session, a, date(2026, 10, 19), -300)  # uncategorized, current week
    p = cycle_plan(session, date(2026, 10, 19))
    assert [(w.start, w.end) for w in p.weeks] == [
        (date(2026, 10, 10), date(2026, 10, 10)),
        (date(2026, 10, 11), date(2026, 10, 17)),
        (date(2026, 10, 18), date(2026, 10, 24)),
        (date(2026, 10, 25), date(2026, 10, 31)),
        (date(2026, 11, 1), date(2026, 11, 7)),
        (date(2026, 11, 8), date(2026, 11, 9)),
    ]
    # past weeks keep their planned share (8000 / 31 days) with left 0
    assert [(w.allowance, w.left) for w in p.weeks[:2]] == [
        (Decimal("258.06"), 0),
        (Decimal("1806.45"), 0),
    ]
    # the 6000 left after past spending is split by days: 23 days -> 260.87/day
    assert [w.allowance for w in p.weeks[2:]] == [
        Decimal("1826.09"),
        Decimal("1826.09"),
        Decimal("1826.09"),
        Decimal("521.73"),  # 2 days + rounding remainder
    ]
    assert p.weeks[2].left == Decimal("1526.09")


def test_split_by_days_owner_example():
    # 30-day cycle, 3,000: weeks of 4/7/7/7/5 days -> 400/700/700/700/500
    d0 = date(2026, 10, 1)
    spans, a = [], d0
    for n in (4, 7, 7, 7, 5):
        spans.append((a, a + timedelta(days=n - 1)))
        a += timedelta(days=n)
    assert split_by_days(spans, d0, Decimal(3000), Decimal(0)) == [400, 700, 700, 700, 500]
    # 800 spent in week 1 -> the 400 excess spreads over the 26 remaining days
    shares = split_by_days(spans, date(2026, 10, 5), Decimal(3000), Decimal(800))
    assert shares == [
        400,
        Decimal("592.31"),
        Decimal("592.31"),
        Decimal("592.31"),
        Decimal("423.07"),
    ]
    assert sum(shares[1:]) == 2200
    # a fixed (overridden) week is taken out first; never negative with floor_zero
    fixed = split_by_days(spans, d0, Decimal(3000), Decimal(0), {0: Decimal(1300)})
    assert fixed == [
        1300,
        Decimal("457.69"),
        Decimal("457.69"),
        Decimal("457.69"),
        Decimal("326.93"),
    ]
    assert split_by_days(spans, date(2026, 10, 5), Decimal(100), Decimal(800), floor_zero=True)[
        1:
    ] == [0, 0, 0, 0]


def test_goal_carries_from_previous_cycle(session):
    sep = cycle_by_label(2026, 9, 10)
    assert get_goal(session, OCT) == Decimal(0)  # seeded default
    set_goal(session, sep, Decimal(1500))
    assert get_goal(session, OCT) == Decimal(1500)
    set_goal(session, OCT, Decimal(2000))
    set_goal(session, OCT, Decimal(2500))
    assert get_goal(session, OCT) == Decimal(2500)
    assert get_goal(session, sep) == Decimal(1500)


def test_category_expected_is_history_median(session):
    a = _acct(session)
    for m in range(4, 10):  # cycles Apr..Sep 2026, all complete
        _tx(session, a, date(2026, m, 15), 10000, "משכורת")
        _tx(session, a, date(2026, m, 16), -7000, "משכנתא")
        _tx(session, a, date(2026, m, 17), -400 if m % 2 else -600, "כלכלה")
    p = cycle_plan(session, date(2026, 10, 23))
    [food] = [c for c in p.categories if c.name == "כלכלה"]
    assert (food.spent, food.expected, food.left) == (0, Decimal(500), Decimal(500))


def _rec(session, key, direction, amount, next_date, cat=None):
    session.add(
        RecurringItem(
            merchant_key=key,
            direction=direction,
            label=key,
            category_id=_cat(session, cat) if cat else None,
            cadence="monthly",
            amount_kind="fixed",
            expected_amount=Decimal(amount),
            last_date=next_date,
            next_expected_date=next_date,
            status="confirmed",
            basis="b",
        )
    )
    session.flush()


def test_savings_deposit_does_not_move_variable_left(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 11), 20000, "משכורת")
    _tx(session, a, date(2026, 9, 25), -1000, "השקעה וחיסכון", key="deposit")  # history only
    _rec(session, "deposit", "expense", 1000, date(2026, 10, 25))  # group from latest txn
    before = cycle_plan(session, date(2026, 10, 23))
    assert [x.label for x in before.savings_expected] == ["deposit"]
    assert before.expected_fixed == 0
    _tx(session, a, date(2026, 10, 25), -1000, "השקעה וחיסכון", key="deposit")
    after = cycle_plan(session, date(2026, 10, 26))
    assert after.savings_spent == Decimal(1000)
    assert after.variable_left == before.variable_left == Decimal(20000)


def test_charged_item_shown_even_if_next_date_stale(session):
    a = _acct(session)
    _rec(session, "rent", "expense", 5000, date(2026, 10, 1), cat="דיור")  # not advanced
    _tx(session, a, date(2026, 10, 11), -5000, "דיור", key="rent")
    p = cycle_plan(session, date(2026, 10, 23))
    assert p.expected_fixed == Decimal(5000)  # actual, not doubled
    [line] = expected_in_cycle(session, OCT, date(2026, 10, 23)).fixed_items
    assert (line.label, line.charged, line.amount) == ("rent", True, Decimal(5000))


def test_landed_salary_counted_once(session):
    a = _acct(session)
    _rec(session, "salary", "income", 15000, date(2026, 11, 8), cat="משכורת")
    _tx(session, a, date(2026, 10, 10), 15500, "משכורת", key="salary")
    p = cycle_plan(session, date(2026, 10, 23))
    assert p.expected_income == Decimal(15500)
    assert p.still_expected == []


def test_week_split_sums_exactly(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 10), 1000, "משכורת")
    for today in (date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 27)):
        p = cycle_plan(session, today)
        rest = [w for w in p.weeks if w.end >= today]
        assert sum(w.allowance for w in rest) == p.variable_allowance  # nothing spent yet
    # 16 days left: 7/7/2 -> 437.5 / 437.5 / 125
    assert [w.allowance for w in rest] == [Decimal("437.5"), Decimal("437.5"), Decimal(125)]


def test_tracked_categories_stay_out_of_the_weekly_allowance(session):
    from freerise.models import CategoryBudget, TrackedCategory

    a = _acct(session)
    _tx(session, a, date(2026, 10, 10), 10000, "משכורת")
    _tx(session, a, date(2026, 10, 19), -300, "כלכלה")  # tracked, budget 1000
    _tx(session, a, date(2026, 10, 20), -100, "קניות")  # the rest
    food = _cat(session, "כלכלה")
    session.add(TrackedCategory(category_id=food, mode="weekly"))
    session.add(CategoryBudget(cycle_start=OCT.start, category_id=food, amount=1000))
    session.flush()
    p = cycle_plan(session, date(2026, 10, 23))
    assert p.variable_allowance == 10000 and p.variable_spent == 400
    ((t),) = p.tracked
    assert (t.category_id, t.spent, t.expected) == (food, 300, 1000)
    assert (p.rest_allowance, p.rest_spent) == (9000, 100)
    cur = next(w for w in p.weeks if w.start <= date(2026, 10, 23) <= w.end)
    assert cur.spent == 100  # the supermarket isn't in the week
    assert sum(w.spent for w in p.weeks) == p.rest_spent
