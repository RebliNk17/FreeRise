from datetime import date
from decimal import Decimal

from freerise.cashflow.cycles import cycle_by_label
from freerise.cashflow.plan import CyclePlan, WeekPlan, projected_month_end
from freerise.cashflow.summary import CycleSummary, GroupSummary
from freerise.cashflow.whatif import what_if

OCT = cycle_by_label(2026, 10, 10)  # 10.10 - 9.11, 31 days


def _plan(spent):
    allowance = Decimal(4000)
    weeks = [
        WeekPlan(date(2026, 10, 10), date(2026, 10, 10), Decimal(0), Decimal(0), Decimal(0)),
        WeekPlan(date(2026, 10, 11), date(2026, 10, 17), Decimal(0), Decimal(0), Decimal(0)),
        WeekPlan(date(2026, 10, 18), date(2026, 10, 24), spent, Decimal(1000), 1000 - spent),
        WeekPlan(date(2026, 10, 25), date(2026, 10, 31), Decimal(0), Decimal(1000), Decimal(1000)),
        WeekPlan(date(2026, 11, 1), date(2026, 11, 7), Decimal(0), Decimal(1000), Decimal(1000)),
        WeekPlan(date(2026, 11, 8), date(2026, 11, 9), Decimal(0), Decimal(1000), Decimal(1000)),
    ]
    return CyclePlan(
        OCT, Decimal(20000), Decimal(14000), Decimal(2000), allowance, spent,
        allowance - spent, Decimal(0), weeks, [], [], [],
    )  # fmt: skip


def test_whatif_math():
    # 1,100 spent in 11 of 31 days -> 100/day -> 3,100 variable -> 6000 − 3100
    r = what_if(_plan(Decimal(1100)), date(2026, 10, 20), [Decimal(-400), Decimal(100)], [])
    assert (r.monthly_delta, r.yearly_impact) == (-300, -3600)
    assert r.baseline.variable_allowance == 4000 and r.scenario.variable_allowance == 3700
    # -300 split by days: the current week holds 7 of the 23 remaining days
    assert (r.baseline.weekly_left, r.scenario.weekly_left) == (-100, Decimal("-191.30"))
    # the delta is applied once, on top of the same spending pace
    assert (r.baseline.month_end, r.scenario.month_end) == (2900, 2600)


def test_whatif_no_change():
    r = what_if(_plan(Decimal(3100)), date(2026, 10, 20), [], [])
    assert r.baseline == r.scenario and r.yearly_impact == 0
    assert r.baseline.month_end == Decimal("-2736.36")


def test_projected_month_end_uses_history_early_in_cycle():
    p = _plan(Decimal(1000))  # day 3: pace (333/day) would be noise
    hist = [
        CycleSummary(OCT, v, v, Decimal(0), "positive", [GroupSummary("variable", v)], 0, 0, 0)
        for v in (Decimal(3100), Decimal(6200), Decimal(1000))
    ]
    # median 3100 / 31 = 100/day for the 28 days left
    assert projected_month_end(p, date(2026, 10, 12), hist) == 6000 - 1000 - 2800
    assert projected_month_end(p, date(2026, 10, 12), []) == 6000 - 1000 - Decimal(1000) / 3 * 28
