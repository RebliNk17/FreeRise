from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from freerise.accounts import account_label
from freerise.api.deps import DB, today
from freerise.api.routes_cashflow import CycleOut
from freerise.api.routes_forecast import LineOut, _lines
from freerise.cashflow.balances import balances
from freerise.cashflow.cycles import cycle_for, get_start_day
from freerise.cashflow.fees import fees_in_cycle
from freerise.cashflow.plan import cycle_plan, set_goal
from freerise.forecast.next_cycle import next_cycle_forecast

router = APIRouter()


class WeekOut(BaseModel):
    start: date
    end: date
    spent: float
    allowance: float
    left: float
    is_current: bool
    is_past: bool


class CategoryPlanOut(BaseModel):
    category_id: int | None
    name: str
    spent: float
    expected: float
    left: float


class BalanceAccount(BaseModel):
    id: int
    display_name: str
    balance: float
    as_of: datetime | None


class Balances(BaseModel):
    bank_total: float
    accounts: list[BalanceAccount]
    upcoming_card_charges: float  # positive


class NextCycle(BaseModel):
    installments_stopping_total: float
    fixed_total: float
    income_total: float


class FeesTotal(BaseModel):
    total: float
    count: int


class PlanOut(BaseModel):
    """Amounts positive (spent / expected / left; left may go negative)."""

    cycle: CycleOut
    today: date
    expected_income: float
    expected_fixed: float
    goal: float  # goal_personal + goal_plans
    goal_personal: float
    goal_plans: float
    variable_allowance: float
    variable_spent: float
    variable_left: float
    savings_spent: float
    weeks: list[WeekOut]
    categories: list[CategoryPlanOut]
    balances: Balances
    next_cycle: NextCycle
    fees: FeesTotal
    still_expected: list[LineOut]  # fixed charges not yet seen this cycle
    still_expected_income: list[LineOut]


class GoalIn(BaseModel):
    amount: float = Field(ge=0)


class GoalOut(BaseModel):
    goal: float


def _balances(db: DB, cycle) -> Balances:
    b = balances(db, cycle)
    return Balances(
        bank_total=b.bank_total or 0,
        accounts=[
            BalanceAccount(id=a.id, display_name=account_label(a), balance=bal or 0, as_of=as_of)
            for a, bal, as_of in b.banks
        ],
        upcoming_card_charges=b.upcoming_card_charges,
    )


@router.get("/plan/current")
def plan_current(db: DB) -> PlanOut:
    t = today()
    p = cycle_plan(db, t)
    f = next_cycle_forecast(db, t)
    fees = fees_in_cycle(db, p.cycle)
    return PlanOut(
        cycle=CycleOut.of(p.cycle),
        today=t,
        expected_income=p.expected_income,
        expected_fixed=p.expected_fixed,
        goal=p.goal,
        goal_personal=p.goal_personal,
        goal_plans=p.goal_plans,
        variable_allowance=p.variable_allowance,
        variable_spent=p.variable_spent,
        variable_left=p.variable_left,
        savings_spent=p.savings_spent,
        weeks=[
            WeekOut(**vars(w), is_current=w.start <= t <= w.end, is_past=w.end < t) for w in p.weeks
        ],
        categories=[CategoryPlanOut(**vars(c)) for c in p.categories],
        balances=_balances(db, p.cycle),
        next_cycle=NextCycle(
            installments_stopping_total=f.installments_stopping_total,
            fixed_total=f.fixed_total,
            income_total=f.income_total,
        ),
        fees=FeesTotal(total=fees.total, count=fees.count),
        still_expected=_lines(p.still_expected),
        still_expected_income=_lines(p.still_expected_income),
    )


@router.put("/plan/goal")
def put_goal(body: GoalIn, db: DB) -> GoalOut:
    set_goal(db, cycle_for(today(), get_start_day(db)), Decimal(str(body.amount)))
    db.commit()
    return GoalOut(goal=body.amount)
