from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from freerise.api.deps import DB, today
from freerise.api.routes_cashflow import CycleOut
from freerise.cashflow.cycles import cycle_for, get_start_day
from freerise.cashflow.summary import cycle_summary
from freerise.insights.engine import compute_insights, dismiss, run, snooze
from freerise.insights.history import cycles_before, value_of
from freerise.insights.progress import progress

router = APIRouter()


class InsightAction(BaseModel):
    label: str
    method: Literal["POST", "PUT", "DELETE"]
    path: str  # under /api


class InsightOut(BaseModel):
    key: str
    kind: str
    severity: Literal["info", "warning", "positive"]
    title: str
    body: str
    action_label: str | None
    link: str | None
    amount: float | None
    actions: list[InsightAction] | None = None


class CycleNet(BaseModel):
    cycle: CycleOut
    net: float


class CategoryChange(BaseModel):
    category_id: int | None
    name: str
    previous: float  # monthly average, previous 3 cycles
    current: float  # monthly average, latest 3 cycles
    change_pct: float  # (current − previous) ÷ previous


class ProgressOut(BaseModel):
    cycles: list[CycleNet]  # oldest first
    avg_net: float
    positive_cycles: int
    savings_total: float
    savings_avg: float
    increases: list[CategoryChange]
    decreases: list[CategoryChange]
    cumulative_net: float
    since: date | None


@router.get("/insights")
def list_insights(db: DB) -> list[InsightOut]:
    return [InsightOut(**vars(i)) for i in compute_insights(db, today())]


def _current(db: DB, key: str) -> str:
    """Only keys the engine produces right now may be hidden (no junk rows)."""
    if key not in {i.key for i in run(db, today())}:
        raise HTTPException(404, "no such insight")
    return key


@router.post("/insights/{key}/snooze", status_code=204)
def snooze_insight(key: str, db: DB) -> None:
    snooze(db, _current(db, key))
    db.commit()


@router.post("/insights/{key}/dismiss", status_code=204)
def dismiss_insight(key: str, db: DB) -> None:
    dismiss(db, _current(db, key))
    db.commit()


@router.get("/progress")
def get_progress(db: DB) -> ProgressOut:
    p = progress(db, today())
    return ProgressOut(
        cycles=[CycleNet(cycle=CycleOut.of(c), net=n) for c, n in p.cycles],
        avg_net=p.avg_net,
        positive_cycles=p.positive_cycles,
        savings_total=p.savings_total,
        savings_avg=p.savings_avg,
        increases=[CategoryChange(**vars(x)) for x in p.increases],
        decreases=[CategoryChange(**vars(x)) for x in p.decreases],
        cumulative_net=p.cumulative_net,
        since=p.since,
    )


class MonthTotal(BaseModel):
    label_year: int
    label_month: int
    total: float


class CategoryRef(BaseModel):
    category_id: int
    name: str


class ProgressHistoryOut(BaseModel):
    """Last `months` complete cycles, oldest first; totals positive."""

    cycles: list[MonthTotal]
    average: float  # over the cycles that have any data
    categories: list[CategoryRef]  # this group's categories seen in the period (filter options)


@router.get("/progress/history")
def progress_history(
    db: DB,
    group: Literal["income", "fixed", "variable"],
    months: Annotated[int, Query(ge=1, le=24)] = 6,
    category_id: int | None = None,
) -> ProgressHistoryOut:
    cycles = cycles_before(db, cycle_for(today(), get_start_day(db)), months)
    sums = [cycle_summary(db, c) for c in cycles]
    names = {
        c.category_id: c.name
        for s in sums
        for g in s.groups
        if g.group == group
        for c in g.categories
        if c.category_id is not None
    }
    values = [value_of(s, group, category_id) for s in sums]
    with_data = [v for v, s in zip(values, sums, strict=True) if s.income or s.spending]
    return ProgressHistoryOut(
        cycles=[
            MonthTotal(label_year=c.label_month.year, label_month=c.label_month.month, total=v)
            for c, v in zip(cycles, values, strict=True)
        ],
        average=sum(with_data) / len(with_data) if with_data else 0,
        categories=[
            CategoryRef(category_id=k, name=v) for k, v in sorted(names.items(), key=lambda x: x[1])
        ],
    )
