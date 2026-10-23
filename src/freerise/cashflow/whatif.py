""" "תרחישים": apply monthly changes to the current cycle plan. Pure; no DB."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from freerise.cashflow.plan import CENT, CyclePlan, projected_month_end
from freerise.cashflow.summary import CycleSummary


@dataclass
class Numbers:
    variable_allowance: Decimal  # scenario: allowance + delta ("if you adjust spending")
    weekly_left: Decimal  # this week's "left to spend"
    month_end: Decimal  # projected month end; scenario: baseline + delta, spending pace unchanged


@dataclass
class WhatIf:
    baseline: Numbers
    scenario: Numbers
    monthly_delta: Decimal
    yearly_impact: Decimal


def _weekly(p: CyclePlan, today: date, delta: Decimal) -> Decimal:
    rest = [w for w in p.weeks if w.end >= today]  # weeks the allowance is still split over
    cur = next((w for w in rest if w.start <= today), None)
    if not cur:
        return Decimal(0)
    days = sum((w.end - w.start).days + 1 for w in rest)  # split by days, as the plan
    return cur.left + (delta * ((cur.end - cur.start).days + 1) / days).quantize(CENT)


def what_if(p: CyclePlan, today: date, changes: list[Decimal], hist: list[CycleSummary]) -> WhatIf:
    """changes: signed monthly amounts (negative = new expense, positive = income / saving)."""
    delta = sum(changes, Decimal(0))
    end = projected_month_end(p, today, hist).quantize(CENT)
    base = Numbers(p.variable_allowance, _weekly(p, today, Decimal(0)), end)
    scen = Numbers(p.variable_allowance + delta, _weekly(p, today, delta), end + delta)
    return WhatIf(base, scen, delta, delta * 12)
