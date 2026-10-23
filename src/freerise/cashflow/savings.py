"""Savings plans ("יעדי חיסכון"): how much to set aside each cycle, and marking it done."""

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.cashflow.cycles import Cycle, cycle_for
from freerise.models import PlanContribution, SavingsPlan


@dataclass
class PlanStatus:
    plan: SavingsPlan
    months_left: int
    monthly_needed: Decimal  # this cycle's amount; 0 once completed
    funded_this_cycle: bool
    completed: bool
    overdue: bool = False  # target cycle already over and not completed; stops feeding the goal


def months_left(cycle: Cycle, plan: SavingsPlan, start_day: int) -> int:
    """Cycles from the current one through the target date's cycle, at least 1."""
    t = cycle_for(plan.target_date, start_day).label_month
    c = cycle.label_month
    return max(1, (t.year - c.year) * 12 + t.month - c.month + 1)


def status(
    plan: SavingsPlan, cycle: Cycle, start_day: int, this_cycle: Decimal | None
) -> PlanStatus:
    """this_cycle: amount contributed in `cycle` (None = not funded yet).

    The amount is computed from the balance before this cycle's contribution so it stays put
    after "העברתי החודש"."""
    n = months_left(cycle, plan, start_day)
    remaining = plan.target_amount - (plan.saved_amount - (this_cycle or 0))
    if remaining <= 0:
        needed = Decimal(0)
    elif plan.monthly_override is not None:
        needed = min(plan.monthly_override, remaining)
    else:
        needed = Decimal(math.ceil(remaining / n))
    completed = plan.saved_amount >= plan.target_amount
    overdue = not completed and cycle_for(plan.target_date, start_day).start < cycle.start
    return PlanStatus(plan, n, needed, this_cycle is not None, completed, overdue)


def plan_statuses(session: Session, cycle: Cycle, start_day: int) -> list[PlanStatus]:
    done = dict(
        session.execute(
            select(PlanContribution.plan_id, PlanContribution.amount).where(
                PlanContribution.cycle_start == cycle.start
            )
        ).all()
    )
    plans = session.scalars(select(SavingsPlan).order_by(SavingsPlan.target_date, SavingsPlan.id))
    return [status(p, cycle, start_day, done.get(p.id)) for p in plans]


def monthly_total(statuses: list[PlanStatus]) -> Decimal:
    """ "לשים בצד כל חודש": sum over active plans that are not overdue."""
    return sum((s.monthly_needed for s in statuses if s.plan.active and not s.overdue), Decimal(0))


def contribute(session: Session, plan: SavingsPlan, cycle: Cycle, start_day: int) -> None:
    """saved += this cycle's amount, once per cycle (repeat calls are no-ops)."""
    exists = session.scalar(
        select(PlanContribution.id).where(
            PlanContribution.plan_id == plan.id, PlanContribution.cycle_start == cycle.start
        )
    )
    if exists is not None:
        return
    needed = status(plan, cycle, start_day, None).monthly_needed
    if needed <= 0:
        return
    session.add(PlanContribution(plan_id=plan.id, cycle_start=cycle.start, amount=needed))
    plan.saved_amount += needed
    session.flush()


def uncontribute(session: Session, plan: SavingsPlan, cycle_start: date) -> None:
    """Undo that cycle's contribution: saved -= its amount (never below 0). No-op if none."""
    c = session.scalar(
        select(PlanContribution).where(
            PlanContribution.plan_id == plan.id, PlanContribution.cycle_start == cycle_start
        )
    )
    if c is None:
        return
    plan.saved_amount = max(plan.saved_amount - c.amount, Decimal(0))
    session.delete(c)
    session.flush()
