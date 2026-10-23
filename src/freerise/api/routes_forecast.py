from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from freerise.accounts import account_labels
from freerise.api.deps import DB, get_or_404, today
from freerise.api.routes_cashflow import CycleOut
from freerise.forecast.attribution import attribute_income
from freerise.forecast.next_cycle import next_cycle_forecast
from freerise.forecast.recurring import (
    detect_recurring,
    mark_fixed_income,
    recent_previous_account,
    set_status,
)
from freerise.models import Category, RecurringItem

router = APIRouter()

Status = Literal["pending", "confirmed", "dismissed"]


class LineOut(BaseModel):
    """amount positive."""

    label: str
    amount: float
    date: date
    source: Literal["recurring", "installment"]
    basis: str
    charged: bool
    account_id: int | None
    account_label: str | None
    previous_account_label: str | None  # set only right after a switch
    category_name: str | None = None


class ForecastOut(BaseModel):
    cycle: CycleOut
    fixed_total: float
    income_total: float
    installments_stopping_total: float
    delta_fixed_vs_current: float
    fixed_items: list[LineOut]
    income_items: list[LineOut]
    installments_stopping: list[LineOut]


class RecurringOut(BaseModel):
    """expected_amount positive."""

    id: int
    merchant_key: str
    direction: Literal["expense", "income"]
    label: str
    category_id: int | None
    category_name: str | None
    cadence: str
    amount_kind: Literal["fixed", "variable"]
    expected_amount: float
    last_date: date
    next_expected_date: date
    status: Status
    basis: str
    account_id: int | None
    account_label: str | None
    previous_account_label: str | None  # set only right after a switch
    user_defined: bool  # fixed income marked by the user
    expected_day: int | None  # its day of month


class FixedIn(BaseModel):
    expected_day: int = Field(ge=1, le=31)
    expected_amount: Decimal | None = Field(None, gt=0)  # None -> variable, keep current


class StatusIn(BaseModel):
    status: Status


class Count(BaseModel):
    count: int


def _lines(xs, names: dict[int, str] | None = None) -> list[LineOut]:
    return [LineOut(**vars(x), category_name=(names or {}).get(x.category_id)) for x in xs]


@router.get("/forecast/next")
def forecast_next(db: DB) -> ForecastOut:
    f = next_cycle_forecast(db, today())
    names = dict(db.execute(select(Category.id, Category.name)).all())
    return ForecastOut(
        cycle=CycleOut.of(f.cycle),
        fixed_total=f.fixed_total,
        income_total=f.income_total,
        installments_stopping_total=f.installments_stopping_total,
        delta_fixed_vs_current=f.delta_fixed_vs_current,
        fixed_items=_lines(f.fixed_items, names),
        income_items=_lines(f.income_items, names),
        installments_stopping=_lines(f.installments_stopping, names),
    )


_JOINED = {"category_name", "account_label", "previous_account_label"}


def _recurring(db: DB, status: str | None = None, id: int | None = None) -> list[RecurringOut]:
    q = (
        select(RecurringItem, Category.name)
        .outerjoin(Category, Category.id == RecurringItem.category_id)
        .order_by(RecurringItem.next_expected_date, RecurringItem.id)
    )
    if status:
        q = q.where(RecurringItem.status == status)
    if id is not None:
        q = q.where(RecurringItem.id == id)
    labels, t = account_labels(db), today()
    return [
        RecurringOut(
            category_name=name,
            account_label=labels.get(r.account_id),
            previous_account_label=labels.get(recent_previous_account(r, t)),
            **{f: getattr(r, f) for f in RecurringOut.model_fields if f not in _JOINED},
        )
        for r, name in db.execute(q)
    ]


@router.get("/recurring")
def list_recurring(db: DB, status: Status | None = None) -> list[RecurringOut]:
    return _recurring(db, status)


@router.put("/recurring/{id}")
def update_recurring(id: int, body: StatusIn, db: DB) -> RecurringOut:
    get_or_404(db, RecurringItem, id)
    set_status(db, id, body.status)
    attribute_income(db)
    db.commit()
    return _recurring(db, id=id)[0]


@router.put("/recurring/{id}/fixed")
def update_fixed(id: int, body: FixedIn, db: DB) -> RecurringOut:
    """Make/keep a monthly income user-defined fixed, with its expected day (and amount)."""
    it = get_or_404(db, RecurringItem, id)
    if it.direction != "income":
        raise HTTPException(400, "not an income item")
    mark_fixed_income(
        db,
        it.merchant_key,
        it.label,
        it.category_id,
        it.account_id,
        it.last_date,
        body.expected_day,
        body.expected_amount or it.expected_amount,
        body.expected_amount is not None,
    )
    attribute_income(db)
    db.commit()
    return _recurring(db, id=id)[0]


@router.delete("/recurring/{id}/fixed")
def unmark_fixed(id: int, db: DB) -> RecurringOut:
    """Not a fixed income: dismissed (detection won't re-propose it), no longer user-defined."""
    it = get_or_404(db, RecurringItem, id)
    it.status, it.user_defined = "dismissed", False
    db.flush()
    attribute_income(db)
    db.commit()
    return _recurring(db, id=id)[0]


@router.post("/recurring/detect")
def detect(db: DB) -> Count:
    n = len(detect_recurring(db, today()))
    attribute_income(db)
    db.commit()
    return Count(count=n)
