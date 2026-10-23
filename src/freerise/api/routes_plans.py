"""Savings plans ("יעדי חיסכון")."""

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from freerise.api.deps import DB, get_or_404, today
from freerise.cashflow.cycles import cycle_for, get_start_day
from freerise.cashflow.savings import (
    PlanStatus,
    contribute,
    monthly_total,
    plan_statuses,
    uncontribute,
)
from freerise.models import SavingsPlan

router = APIRouter()


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    target_amount: float = Field(gt=0)
    target_date: date
    saved_amount: float = Field(0, ge=0)
    monthly_override: float | None = Field(None, gt=0)
    active: bool = True


class PlanPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    target_amount: float | None = Field(None, gt=0)
    target_date: date | None = None
    saved_amount: float | None = Field(None, ge=0)
    monthly_override: float | None = Field(None, gt=0)  # explicit null clears it
    active: bool | None = None


class SavingsPlanOut(BaseModel):
    id: int
    name: str
    target_amount: float
    target_date: date
    saved_amount: float
    monthly_override: float | None
    active: bool
    created_at: datetime
    months_left: int
    monthly_needed: float
    funded_this_cycle: bool
    completed: bool
    overdue: bool  # target date's cycle is over; not part of monthly_total


class PlansOut(BaseModel):
    monthly_total: float  # "לשים בצד כל חודש", active plans
    active_count: int
    plans: list[SavingsPlanOut]


def _out(s: PlanStatus) -> SavingsPlanOut:
    p = s.plan
    return SavingsPlanOut(
        id=p.id,
        name=p.name,
        target_amount=p.target_amount,
        target_date=p.target_date,
        saved_amount=p.saved_amount,
        monthly_override=p.monthly_override,
        active=p.active,
        created_at=p.created_at,
        months_left=s.months_left,
        monthly_needed=s.monthly_needed,
        funded_this_cycle=s.funded_this_cycle,
        completed=s.completed,
        overdue=s.overdue,
    )


def _statuses(db: DB):
    start_day = get_start_day(db)
    return plan_statuses(db, cycle_for(today(), start_day), start_day)


def _one(db: DB, id: int) -> SavingsPlanOut:
    return _out(next(s for s in _statuses(db) if s.plan.id == id))


def _dec(v):
    return Decimal(str(v)) if isinstance(v, float) else v


@router.get("/plans")
def list_plans(db: DB) -> PlansOut:
    st = _statuses(db)
    return PlansOut(
        monthly_total=monthly_total(st),
        active_count=sum(s.plan.active for s in st),
        plans=[_out(s) for s in st],
    )


@router.post("/plans", status_code=201)
def create_plan(body: PlanIn, db: DB) -> SavingsPlanOut:
    p = SavingsPlan(**{k: _dec(v) for k, v in body.model_dump().items()})
    db.add(p)
    db.commit()
    return _one(db, p.id)


@router.patch("/plans/{id}")
def update_plan(id: int, body: PlanPatch, db: DB) -> SavingsPlanOut:
    p = get_or_404(db, SavingsPlan, id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is None and k != "monthly_override":
            continue  # only the override may be cleared
        setattr(p, k, _dec(v))
    db.commit()
    return _one(db, id)


@router.delete("/plans/{id}", status_code=204)
def delete_plan(id: int, db: DB) -> None:
    db.delete(get_or_404(db, SavingsPlan, id))
    db.commit()


@router.post("/plans/{id}/contribute")
def contribute_plan(id: int, db: DB) -> SavingsPlanOut:
    p = get_or_404(db, SavingsPlan, id)
    if not p.active:
        raise HTTPException(409, "plan is paused")
    start_day = get_start_day(db)
    contribute(db, p, cycle_for(today(), start_day), start_day)
    db.commit()
    return _one(db, id)


@router.delete("/plans/{id}/contribute")
def uncontribute_plan(id: int, db: DB, cycle_start: date | None = None) -> SavingsPlanOut:
    """Undo "העברתי החודש" for `cycle_start` (default: the current cycle)."""
    p = get_or_404(db, SavingsPlan, id)
    uncontribute(db, p, cycle_start or cycle_for(today(), get_start_day(db)).start)
    db.commit()
    return _one(db, id)
