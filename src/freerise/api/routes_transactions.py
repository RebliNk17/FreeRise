import base64
import csv
import io
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, exists, select, tuple_
from sqlalchemy.orm import joinedload

from freerise.accounts import account_holder, account_label
from freerise.api.deps import DB, get_or_404
from freerise.cashflow.cycles import cycle_for, cycle_shift, get_start_day, next_cycle, prev_cycle
from freerise.forecast.attribution import attribute_income
from freerise.forecast.recurring import mark_fixed_income
from freerise.models import Account, Category, RecurringItem, Transaction, TransactionSplit
from freerise.reconcile.card_bills import reconcile_range

router = APIRouter()


class SplitPartOut(BaseModel):
    category_id: int
    category_name: str
    amount: float


class TxnOut(BaseModel):
    id: int
    account_id: int
    account_name: str  # account_label(): "ישראכרט ••1234" or the user's own name
    date: date
    processed_date: date
    amount: float
    original_amount: float | None
    original_currency: str | None
    description: str
    memo: str | None
    installment_number: int | None
    installment_total: int | None
    status: str
    category_id: int | None
    category_name: str | None
    category_source: str | None
    merchant_key: str
    note: str | None
    reconcile_status: str | None = None
    account_holder: str = ""  # whose card: account.holder, else the credential's owner
    cycle_shift: Literal["previous", "next"] | None = None  # attributed to a neighbour cycle
    cycle_label: str | None = None  # that cycle's label month, e.g. "ספטמבר 2026"
    cycle_date_source: Literal["auto", "manual"] | None = None
    fixed_income_id: int | None = None  # confirmed income item of this merchant
    split: list[SplitPartOut] | None = None  # parts when split (they sum to amount)


class TxnPage(BaseModel):
    items: list[TxnOut]
    next_cursor: str | None


BANK_BILL = ("card_bill", "bank")
_JOINED = {
    "account_name",
    "category_name",
    "reconcile_status",
    "account_holder",
    "cycle_shift",
    "cycle_label",
    "fixed_income_id",
    "split",
}


def _encode(t: Transaction) -> str:
    return base64.urlsafe_b64encode(f"{t.date.isoformat()}|{t.id}".encode()).decode()


def _decode(cursor: str) -> tuple[date, int]:
    try:
        d, i = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return date.fromisoformat(d), int(i)
    except ValueError:  # binascii.Error and UnicodeDecodeError are ValueErrors
        raise HTTPException(400, "bad cursor") from None


class TxnFilters(BaseModel):
    """Shared by the list and the CSV export."""

    from_: date | None = Field(None, alias="from")
    to: date | None = None
    account_id: int | None = None
    include_excluded: bool = False
    q: str | None = None
    category_id: int | None = None
    uncategorized: bool = False


def _filtered(f: TxnFilters):
    stmt = (
        select(Transaction, Account, Category.name, Category.group, Account.kind)
        .join(Account)
        .outerjoin(Category, Category.id == Transaction.category_id)
    )
    if f.from_:
        stmt = stmt.where(Transaction.date >= f.from_)
    if f.to:
        stmt = stmt.where(Transaction.date <= f.to)
    if f.account_id is not None:
        stmt = stmt.where(Transaction.account_id == f.account_id)
    if not f.include_excluded:
        stmt = stmt.where(Account.excluded.is_(False))
    if f.q:
        stmt = stmt.where(Transaction.description.icontains(f.q, autoescape=True))
    if f.category_id is not None:  # a split txn matches any of its parts' categories
        part = exists().where(
            TransactionSplit.transaction_id == Transaction.id,
            TransactionSplit.category_id == f.category_id,
        )
        stmt = stmt.where((Transaction.category_id == f.category_id) | part)
    if f.uncategorized:
        stmt = stmt.where(Transaction.category_id.is_(None))
    return stmt


@router.get("/transactions")
def list_transactions(
    db: DB,
    f: Annotated[TxnFilters, Query()],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    cursor: str | None = None,
) -> TxnPage:
    stmt = _filtered(f)
    if cursor:
        stmt = stmt.where(tuple_(Transaction.date, Transaction.id) < tuple_(*_decode(cursor)))
    stmt = stmt.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit + 1)
    rows = db.execute(stmt).all()
    bill_dates = [t.date for t, _, _, group, kind in rows[:limit] if (group, kind) == BANK_BILL]
    recs = (
        {r.bank_txn_id: r for r in reconcile_range(db, min(bill_dates), max(bill_dates))}
        if bill_dates
        else {}
    )
    start_day, fixed = get_start_day(db), _fixed_income_ids(db)
    splits = _splits(db, [t.id for t, *_ in rows[:limit]])
    items = [
        _out(t, acct, cat, recs.get(t.id), start_day, fixed, splits.get(t.id))
        for t, acct, cat, _, _ in rows[:limit]  # excluded banks -> no rec
    ]
    return TxnPage(
        items=items, next_cursor=_encode(rows[limit - 1][0]) if len(rows) > limit else None
    )


def _fixed_income_ids(db: DB) -> dict[str, int]:
    return dict(
        db.execute(
            select(RecurringItem.merchant_key, RecurringItem.id).where(
                RecurringItem.direction == "income", RecurringItem.status == "confirmed"
            )
        ).all()
    )


def _splits(db: DB, ids: list[int]) -> dict[int, list[SplitPartOut]]:
    out: dict[int, list[SplitPartOut]] = {}
    rows = db.execute(
        select(TransactionSplit, Category.name)
        .join(Category, Category.id == TransactionSplit.category_id)
        .where(TransactionSplit.transaction_id.in_(ids))
        .order_by(TransactionSplit.id)
    )
    for r, name in rows:
        out.setdefault(r.transaction_id, []).append(
            SplitPartOut(category_id=r.category_id, category_name=name, amount=r.amount)
        )
    return out


def _out(
    t: Transaction, acct: Account, cat: str | None, rec, start_day: int, fixed, split=None
) -> TxnOut:
    shift, label = cycle_shift(t.date, t.cycle_date, start_day)
    return TxnOut(
        split=split,
        account_name=account_label(acct),
        category_name=cat,
        reconcile_status=rec.status if rec else None,
        account_holder=account_holder(acct),
        cycle_shift=shift,
        cycle_label=label,
        fixed_income_id=fixed.get(t.merchant_key) if t.amount > 0 else None,
        **{f: getattr(t, f) for f in TxnOut.model_fields if f not in _JOINED},
    )


def _one(db: DB, t: Transaction) -> TxnOut:
    db.refresh(t)
    acct = db.scalar(
        select(Account).options(joinedload(Account.credential)).where(Account.id == t.account_id)
    )
    cat = db.get(Category, t.category_id) if t.category_id else None
    name = cat.name if cat else None
    return _out(
        t, acct, name, None, get_start_day(db), _fixed_income_ids(db), _splits(db, [t.id]).get(t.id)
    )


class FixedIncomeIn(BaseModel):
    expected_day: int | None = Field(None, ge=1, le=31)  # default: the txn's day
    expected_amount: Decimal | None = Field(None, gt=0)  # given -> fixed amount


@router.post("/transactions/{id}/fixed-income")
def mark_fixed(id: int, body: FixedIncomeIn, db: DB) -> TxnOut:
    """Mark this income's merchant as fixed monthly income (user-defined RecurringItem)."""
    t = get_or_404(db, Transaction, id)
    if t.amount <= 0 or not t.merchant_key:
        raise HTTPException(400, "not an income transaction")
    cat = db.get(Category, t.category_id) if t.category_id else None
    mark_fixed_income(
        db,
        t.merchant_key,
        cat.name if cat else t.description,
        t.category_id,
        t.account_id,
        t.date,
        body.expected_day or t.date.day,
        body.expected_amount or t.amount,
        body.expected_amount is not None,
    )
    attribute_income(db)
    db.commit()
    return _one(db, t)


class CycleIn(BaseModel):
    # previous/next: relative to the txn's real cycle; own: pinned to it; auto: let the rule decide
    target: Literal["previous", "next", "own", "auto"]


@router.put("/transactions/{id}/cycle")
def set_cycle(id: int, body: CycleIn, db: DB) -> TxnOut:
    """Attribute a txn to the previous/next cycle (manual), or back to automatic."""
    t = get_or_404(db, Transaction, id)
    start_day = get_start_day(db)
    own = cycle_for(t.date, start_day)
    if body.target == "auto":
        t.cycle_date, t.cycle_date_source = None, None
        db.flush()
        attribute_income(db)
    else:
        t.cycle_date = {
            "previous": prev_cycle(own, start_day).end,
            "next": next_cycle(own, start_day).start,
            "own": t.date,
        }[body.target]
        t.cycle_date_source = "manual"
        db.flush()
        attribute_income(db)  # a neighbour's automatic move may no longer be needed
    db.commit()
    return _one(db, t)


class SplitPartIn(BaseModel):
    category_id: int
    amount: Decimal = Field(decimal_places=2)


class SplitIn(BaseModel):
    parts: list[SplitPartIn] = Field(min_length=2, max_length=20)


@router.put("/transactions/{id}/split")
def split_transaction(id: int, body: SplitIn, db: DB) -> TxnOut:
    """Replace the txn's split. Parts: distinct categories, same sign as the txn, summing to it."""
    t = get_or_404(db, Transaction, id)
    cids = [p.category_id for p in body.parts]
    if len(set(cids)) != len(cids):
        raise HTTPException(422, "each category once")
    if len(set(db.scalars(select(Category.id).where(Category.id.in_(cids))))) != len(cids):
        raise HTTPException(404, "category not found")
    if any(p.amount == 0 or (p.amount > 0) != (t.amount > 0) for p in body.parts):
        raise HTTPException(422, "parts must have the transaction's sign")
    if sum(p.amount for p in body.parts) != t.amount:
        raise HTTPException(422, "parts must sum to the transaction amount")
    db.execute(delete(TransactionSplit).where(TransactionSplit.transaction_id == id))
    db.add_all(
        TransactionSplit(transaction_id=id, category_id=p.category_id, amount=p.amount)
        for p in body.parts
    )
    db.commit()
    return _one(db, t)


@router.delete("/transactions/{id}/split")
def unsplit_transaction(id: int, db: DB) -> TxnOut:
    t = get_or_404(db, Transaction, id)
    db.execute(delete(TransactionSplit).where(TransactionSplit.transaction_id == id))
    db.commit()
    return _one(db, t)


EXPORT_MAX = 50_000
CSV_HEADER = ("תאריך", "תאריך חיוב", "תיאור", "קטגוריה", "סכום", "חשבון", "על שם", "הערה", "סטטוס")
STATUS_HE = {"pending": "בקליטה", "completed": "סופית"}


@router.get("/transactions/export.csv")
def export_transactions(db: DB, f: Annotated[TxnFilters, Query()]) -> Response:
    """The filtered transactions as CSV for Excel: UTF-8 BOM, Hebrew headers, newest first."""
    stmt = _filtered(f).options(joinedload(Account.credential))
    rows = db.execute(
        stmt.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(EXPORT_MAX)
    ).all()
    splits = _splits(db, [t.id for t, *_ in rows])
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(CSV_HEADER)
    for t, acct, cat, _, _ in rows:
        parts = splits.get(t.id)
        category = (
            "פיצול: " + "; ".join(f"{p.category_name} {abs(p.amount):g}" for p in parts)
            if parts
            else cat or ""
        )
        w.writerow(
            (
                t.date.isoformat(),
                t.processed_date.isoformat(),
                t.description,
                category,
                f"{t.amount:.2f}",
                account_label(acct).replace("\u2066", "").replace("\u2069", ""),
                account_holder(acct),
                t.note or "",
                STATUS_HE.get(t.status, t.status),
            )
        )
    return Response(
        "\ufeff" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="freerise-transactions.csv"'},
    )
