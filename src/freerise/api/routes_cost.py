""" "חיפוש הוצאות": total spent on a search / category over a date range."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import or_, select

from freerise.api.deps import DB
from freerise.cashflow.cycles import cycle_for, get_start_day, next_cycle
from freerise.models import Account, Category, Transaction

router = APIRouter()

NOT_SPENDING = ("transfer", "card_bill", "ignore")
TOP = 10
DAYS_PER_MONTH = Decimal("30.44")


class MonthTotal(BaseModel):
    label_year: int
    label_month: int
    total: float


class MerchantTotal(BaseModel):
    merchant_key: str
    sample: str  # a description to show
    total: float
    count: int


class CostOut(BaseModel):
    """Expenses net of refunds, as positive amounts; months are cycles (label month)."""

    total: float
    count: int
    monthly: list[MonthTotal]
    top_merchants: list[MerchantTotal]
    avg_per_month: float


@router.get("/cost")
def cost(
    db: DB,
    q: str | None = None,
    category_id: int | None = None,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> CostOut:
    # Savings deposits aren't a cost, unless the user asked for that category explicitly.
    skip = NOT_SPENDING if category_id is not None else (*NOT_SPENDING, "savings")
    stmt = (
        select(
            Transaction.effective_date,  # cycle membership; ranges are cycle-aligned
            Transaction.amount,
            Transaction.merchant_key,
            Transaction.description,
        )
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Account.excluded.is_(False),
            or_(
                (Transaction.amount < 0) & or_(Category.id.is_(None), Category.group.not_in(skip)),
                # refunds: categorized credits outside income
                (Transaction.amount > 0) & Category.group.not_in((*skip, "income")),
            ),
        )
    )
    if q := (q or "").strip():
        stmt = stmt.where(
            or_(
                Transaction.description.icontains(q, autoescape=True),
                Transaction.merchant_key.icontains(q, autoescape=True),
            )
        )
    if category_id is not None:
        stmt = stmt.where(Transaction.category_id == category_id)
    if from_:
        stmt = stmt.where(Transaction.effective_date >= from_)
    if to:
        stmt = stmt.where(Transaction.effective_date <= to)
    rows = db.execute(stmt.order_by(Transaction.effective_date)).all()

    start_day = get_start_day(db)
    by_cycle: dict[date, Decimal] = defaultdict(Decimal)
    merchants: dict[str, list] = {}  # key -> [sample, total, count]
    for d, amt, key, desc in rows:
        by_cycle[cycle_for(d, start_day).start] -= amt
        m = merchants.setdefault(key or desc, [desc, Decimal(0), 0])
        m[1] -= amt
        m[2] += 1

    # Every cycle in range (zeros included) so the chart and the average are honest.
    monthly = []
    first, last = from_ or (rows[0][0] if rows else None), to or (rows[-1][0] if rows else None)
    days = (last - first).days + 1 if first and last and first <= last else 0
    if days:
        c, end = cycle_for(first, start_day), cycle_for(last, start_day)
        while c.start <= end.start:
            m = c.label_month
            monthly.append(
                MonthTotal(label_year=m.year, label_month=m.month, total=by_cycle[c.start])
            )
            c = next_cycle(c, start_day)
    total = sum((-amt for _, amt, _, _ in rows), Decimal(0))
    top = sorted(merchants.items(), key=lambda kv: kv[1][1], reverse=True)[:TOP]
    return CostOut(
        total=total,
        count=len(rows),
        monthly=monthly,
        top_merchants=[
            MerchantTotal(merchant_key=k, sample=s, total=t, count=n) for k, (s, t, n) in top
        ],
        # ponytail: ranges under a month count as one month, so a 1-day range isn't ×30
        avg_per_month=total / max(1, days / DAYS_PER_MONTH) if days else 0,
    )
