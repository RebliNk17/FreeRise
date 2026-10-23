from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from freerise.api.deps import DB, today
from freerise.api.routes_cashflow import CycleOut
from freerise.insights.engine import compute_insights, dismiss, run, snooze
from freerise.insights.progress import progress

router = APIRouter()


class InsightOut(BaseModel):
    key: str
    kind: str
    severity: Literal["info", "warning", "positive"]
    title: str
    body: str
    action_label: str | None
    link: str | None
    amount: float | None


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
