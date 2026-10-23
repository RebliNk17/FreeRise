""" "לבדוק עם…": flag a transaction for the other household member (or just "לבדיקה")."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from freerise.accounts import account_holder, account_label
from freerise.api.deps import DB, get_or_404
from freerise.models import Account, Category, Transaction, TransactionReview
from freerise.notify.store import notify

router = APIRouter()


class ReviewIn(BaseModel):
    assignee: str | None = Field(None, max_length=100)
    note: str | None = Field(None, max_length=500)


class ReviewOut(BaseModel):
    transaction_id: int
    assignee: str | None
    note: str | None
    created_at: datetime
    date: date
    description: str
    amount: float
    account_label: str
    category_name: str | None


def household(db: DB) -> list[str]:
    """Names of the people whose accounts are here (account holder, else the login owner)."""
    accts = db.scalars(
        select(Account).options(joinedload(Account.credential)).where(Account.excluded.is_(False))
    )
    return sorted({account_holder(a) for a in accts} - {""})


@router.get("/reviews/people")
def review_people(db: DB) -> list[str]:
    return household(db)


@router.get("/reviews")
def list_reviews(db: DB) -> list[ReviewOut]:
    rows = db.execute(
        select(TransactionReview, Transaction, Account, Category.name)
        .join(Transaction, Transaction.id == TransactionReview.transaction_id)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .options(joinedload(Account.credential))
        .order_by(TransactionReview.created_at.desc(), TransactionReview.id.desc())
    ).all()
    return [
        ReviewOut(
            transaction_id=t.id,
            assignee=r.assignee,
            note=r.note,
            created_at=r.created_at,
            date=t.date,
            description=t.description,
            amount=t.amount,
            account_label=account_label(a),
            category_name=cat,
        )
        for r, t, a, cat in rows
    ]


@router.put("/transactions/{id}/review", status_code=204)
def put_review(id: int, body: ReviewIn, db: DB) -> None:
    """Flag (or update the flag) and leave an in-app notification for the household."""
    t = get_or_404(db, Transaction, id)
    assignee = (body.assignee or "").strip() or None
    if assignee and assignee not in household(db):
        raise HTTPException(422, "not a household member")
    note = (body.note or "").strip() or None
    r = db.scalar(select(TransactionReview).where(TransactionReview.transaction_id == id))
    if r is None:
        r = TransactionReview(transaction_id=id)
        db.add(r)
    r.assignee, r.note = assignee, note
    db.flush()
    amount = f"₪{abs(t.amount):,.2f}".replace(".00", "")
    notify(
        db,
        "review",
        f"לבדוק עם {assignee}" if assignee else "עסקה לבדיקה",
        f"{t.description} · {amount}" + (f" · {note}" if note else ""),
        "/review",
        f"review:{id}:{datetime.now(UTC).isoformat()}",
    )
    db.commit()


@router.delete("/transactions/{id}/review", status_code=204)
def resolve_review(id: int, db: DB) -> None:
    db.execute(delete(TransactionReview).where(TransactionReview.transaction_id == id))
    db.commit()
