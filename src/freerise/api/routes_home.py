from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from freerise.api.deps import DB, get_or_404, today
from freerise.cashflow.cycles import Cycle, cycle_by_label, cycle_for, get_start_day
from freerise.cashflow.plan import tracked_ids
from freerise.cashflow.summary import GROUPS
from freerise.home.builder import build_home
from freerise.insights.history import EXPECTED_BASIS, spent_vs_expected
from freerise.models import Category
from freerise.view import hiding

router = APIRouter()


def _home(db: DB, c: Cycle) -> dict:
    out = jsonable_encoder(build_home(db, c, today()))  # Decimal -> number
    db.commit()  # first call seeds default tracking
    return out


@router.get("/home/current")
def home_current(db: DB, hide_accounts: str | None = None) -> dict:
    with hiding(hide_accounts):
        return _home(db, cycle_for(today(), get_start_day(db)))


@router.get("/home/{year}/{month}")
def home_for(
    db: DB,
    year: Annotated[int, Path(ge=2000, le=2100)],
    month: Annotated[int, Path(ge=1, le=12)],
    hide_accounts: str | None = None,
) -> dict:
    with hiding(hide_accounts):
        return _home(db, cycle_by_label(year, month, get_start_day(db)))


class HistoryRowOut(BaseModel):
    label_year: int
    label_month: int
    spent: float
    expected: float


class HomeHistoryOut(BaseModel):
    """The 6 cycles before the viewed one, oldest first; spent/expected positive."""

    cycles: list[HistoryRowOut]
    avg_spent: float
    avg_expected: float
    basis: str


@router.get("/home/history")
def home_history(
    db: DB,
    kind: Literal["variable", "fixed", "savings", "income", "category"],
    category_id: int | None = None,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    hide_accounts: str | None = None,
) -> HomeHistoryOut:
    """ "חודשים קודמים" for a home card: a group, or one category (kind=category)."""
    start_day = get_start_day(db)
    c = cycle_by_label(year, month, start_day) if year and month else cycle_for(today(), start_day)
    group: str = kind
    if kind == "category":
        if category_id is None:
            raise HTTPException(422, "category_id required")
        group = get_or_404(db, Category, category_id).group
        if group not in GROUPS:
            raise HTTPException(422, "not a cash-flow category")
    # the variable card is spending outside tracked categories (they have their own cards)
    exclude = frozenset(tracked_ids(db)) if kind == "variable" else frozenset()
    with hiding(hide_accounts):
        rows = spent_vs_expected(
            db, c, group, category_id if kind == "category" else None, exclude=exclude
        )
    n = len(rows) or 1
    return HomeHistoryOut(
        cycles=[HistoryRowOut(**vars(r)) for r in rows],
        avg_spent=sum(r.spent for r in rows) / n,
        avg_expected=sum(r.expected for r in rows) / n,
        basis=EXPECTED_BASIS,
    )
