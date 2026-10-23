""" "תרחישים" over the current cycle plan; nothing is saved."""

from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from freerise.api.deps import DB, today
from freerise.cashflow.plan import cycle_plan, history
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
