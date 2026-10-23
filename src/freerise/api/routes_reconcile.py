from dataclasses import asdict
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Path
from pydantic import BaseModel

from freerise.api.deps import DB, today
from freerise.api.routes_cashflow import CycleOut
from freerise.cashflow.cycles import Cycle, cycle_by_label, cycle_for, get_start_day
from freerise.reconcile.card_bills import latest_bill_date, reconcile_cycle

router = APIRouter()


class MatchedAccountOut(BaseModel):
    id: int
    name: str
    excluded: bool


class SuggestionOut(BaseModel):
    txn_id: int
    description: str
    amount: float
    date: date
    account_id: int
    reason: str


class BillOut(BaseModel):
    bank_txn_id: int
    date: date
    amount: float
    issuer: str | None
    status: Literal["matched", "mismatch", "unknown_card"]
    matched_accounts: list[MatchedAccountOut]
    matched_account_ids: list[int]
    card_total: float
    gap: float
    suggestions: list[SuggestionOut]


class ReconcileOut(BaseModel):
    cycle: CycleOut
    bills: list[BillOut]
    matched_count: int
    mismatch_count: int
    unknown_count: int


def _reconcile(db: DB, c: Cycle) -> ReconcileOut:
    bills = reconcile_cycle(db, c)
    n = {s: sum(b.status == s for b in bills) for s in ("matched", "mismatch", "unknown_card")}
    return ReconcileOut(
        cycle=CycleOut.of(c),
        bills=[BillOut(**asdict(b), matched_account_ids=b.matched_account_ids) for b in bills],
        matched_count=n["matched"],
        mismatch_count=n["mismatch"],
        unknown_count=n["unknown_card"],
    )


@router.get("/reconcile/current")
def reconcile_current(db: DB) -> ReconcileOut:
    """The cycle of the latest bank card bill: bills land early, so today's cycle is often empty."""
    return _reconcile(db, cycle_for(latest_bill_date(db) or today(), get_start_day(db)))


@router.get("/reconcile/{year}/{month}")
def reconcile_for(
    db: DB,
    year: Annotated[int, Path(ge=2000, le=2100)],
    month: Annotated[int, Path(ge=1, le=12)],
) -> ReconcileOut:
    return _reconcile(db, cycle_by_label(year, month, get_start_day(db)))
