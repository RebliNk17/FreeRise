""" "תרחישים" over the current cycle plan; nothing is saved."""

from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from freerise.api.deps import DB, today
from freerise.cashflow.plan import cycle_plan, history
from freerise.cashflow.summary import GROUPS, UNCATEGORIZED
from freerise.cashflow.whatif import what_if

router = APIRouter()


class Change(BaseModel):
    label: str = Field(max_length=80)
    monthly_amount: float  # negative = new expense, positive = new income / saving


class WhatIfIn(BaseModel):
    changes: list[Change] = Field(max_length=50)


class NumbersOut(BaseModel):
    variable_allowance: float
    weekly_left: float
    month_end: float


class WhatIfOut(BaseModel):
    baseline: NumbersOut
    scenario: NumbersOut
    monthly_delta: float
    yearly_impact: float


@router.post("/whatif")
def whatif(body: WhatIfIn, db: DB) -> WhatIfOut:
    t = today()
    p = cycle_plan(db, t)
    changes = [Decimal(str(c.monthly_amount)) for c in body.changes]
    r = what_if(p, t, changes, history(db, p.cycle))
    return WhatIfOut(
        baseline=NumbersOut(**vars(r.baseline)),
        scenario=NumbersOut(**vars(r.scenario)),
        monthly_delta=r.monthly_delta,
        yearly_impact=r.yearly_impact,
    )


class TypicalLine(BaseModel):
    label: str
    amount: float  # positive monthly average


class TypicalMonth(BaseModel):
    """A representative month: per-category monthly averages over the last complete cycles
    (up to 6, those with data). Nothing is saved; the planner edits it client side."""

    months: int
    income: list[TypicalLine]
    fixed: list[TypicalLine]
    savings: list[TypicalLine]
    variable: list[TypicalLine]
    goal: float  # this cycle's month-end goal (personal + savings plans)


@router.get("/whatif/typical")
def typical_month(db: DB) -> TypicalMonth:
    p = cycle_plan(db, today())
    hist = history(db, p.cycle)
    n = len(hist) or 1
    lines: dict[str, dict[str, Decimal]] = {g: defaultdict(Decimal) for g in GROUPS}
    for s in hist:
        for g in s.groups:
            for c in g.categories:
                lines[g.group][c.name or UNCATEGORIZED] += c.total
    out = {
        g: sorted(
            (TypicalLine(label=k, amount=round(v / n, 2)) for k, v in d.items() if v > 0),
            key=lambda x: -x.amount,
        )
        for g, d in lines.items()
    }
    return TypicalMonth(months=len(hist), goal=p.goal, **out)
