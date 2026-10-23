from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from freerise.api.deps import DB, get_or_404
from freerise.categorize.pipeline import set_category
from freerise.home.builder import MANUAL_ORDER, default_mode
from freerise.models import (
    Category,
    CategoryBudget,
    CategoryWeekBudget,
    Setting,
    TrackedCategory,
    Transaction,
)

router = APIRouter()

Mode = Literal["weekly", "monthly"]


class TrackingIn(BaseModel):
    tracked: bool
    mode: Mode | None = None


class ExpectedIn(BaseModel):
    cycle_start: date
    amount: float | None = Field(default=None, ge=0)


class WeekIn(ExpectedIn):
    week_index: int = Field(ge=0, le=6)


def _variable_cat(db: DB, category_id: int) -> Category:
    cat = get_or_404(db, Category, category_id)
    if cat.group != "variable":
        raise HTTPException(422, "only variable categories can be tracked")
    return cat


class OrderIn(BaseModel):
    category_ids: list[int] = Field(max_length=200)


@router.put("/tracking/order", status_code=204)
def put_order(body: OrderIn, db: DB) -> None:
    """The user's order for tracked categories on home (first = top). Others keep theirs after."""
    rows = {r.category_id: r for r in db.scalars(select(TrackedCategory))}
    if any(cid not in rows for cid in body.category_ids):
        raise HTTPException(404, "not a tracked category")
    rest = sorted(
        (r for c, r in rows.items() if c not in body.category_ids), key=lambda r: r.sort_order
    )
    for i, r in enumerate([*(rows[c] for c in body.category_ids), *rest]):
        r.sort_order = i
    flag = db.scalar(select(Setting).where(Setting.key == MANUAL_ORDER))
    if flag is None:
        db.add(Setting(key=MANUAL_ORDER, value=True))
    db.commit()


@router.delete("/tracking/order", status_code=204)
def reset_order(db: DB) -> None:
    """Back to automatic: biggest expected first."""
    db.execute(delete(Setting).where(Setting.key == MANUAL_ORDER))
    db.commit()


@router.put("/tracking/{category_id}", status_code=204)
def put_tracking(category_id: int, body: TrackingIn, db: DB) -> None:
    cat = _variable_cat(db, category_id)
    row = db.scalar(select(TrackedCategory).where(TrackedCategory.category_id == category_id))
    if row is None:
        last = db.scalar(
            select(TrackedCategory.sort_order).order_by(TrackedCategory.sort_order.desc())
        )
        row = TrackedCategory(
            category_id=category_id, mode=default_mode(cat.name), sort_order=(last or 0) + 1
        )
        db.add(row)
    row.active = body.tracked
    if body.mode:
        row.mode = body.mode
    db.commit()


def _upsert(db: DB, model, where: dict, amount: float | None) -> None:
    conds = [getattr(model, k) == v for k, v in where.items()]
    if amount is None:
        db.execute(delete(model).where(*conds))
    else:
        row = db.scalar(select(model).where(*conds)) or model(**where)
        row.amount = Decimal(str(amount))
        db.add(row)
    db.commit()


@router.put("/tracking/{category_id}/expected", status_code=204)
def put_expected(category_id: int, body: ExpectedIn, db: DB) -> None:
    _variable_cat(db, category_id)
    where = {"cycle_start": body.cycle_start, "category_id": category_id}
    _upsert(db, CategoryBudget, where, body.amount)


@router.put("/tracking/{category_id}/weeks", status_code=204)
def put_week(category_id: int, body: WeekIn, db: DB) -> None:
    _variable_cat(db, category_id)
    where = {
        "cycle_start": body.cycle_start,
        "category_id": category_id,
        "week_index": body.week_index,
    }
    _upsert(db, CategoryWeekBudget, where, body.amount)


class NoteIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


@router.put("/transactions/{id}/note", status_code=204)
def put_note(id: int, body: NoteIn, db: DB) -> None:
    t = get_or_404(db, Transaction, id)
    t.note = (body.note or "").strip() or None
    db.commit()


class MoveIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)
    category_id: int
    remember: bool = False


class Changed(BaseModel):
    changed: int


@router.post("/transactions/move")
def move_transactions(body: MoveIn, db: DB) -> Changed:
    get_or_404(db, Category, body.category_id)
    ids = list(dict.fromkeys(body.ids))
    keys = dict(
        db.execute(
            select(Transaction.id, Transaction.merchant_key).where(Transaction.id.in_(ids))
        ).all()
    )
    if len(keys) != len(ids):
        raise HTTPException(404, "transaction not found")
    seen: set[str] = set()
    n = 0
    for i in ids:
        remember = body.remember and keys[i] not in seen  # one rule per merchant
        seen.add(keys[i])
        n += set_category(db, i, body.category_id, remember=remember)
    db.commit()
    return Changed(changed=n)
