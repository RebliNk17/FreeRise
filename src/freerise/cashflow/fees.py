"""Fees paid in a cycle (category עמלות), vs the previous cycle, and new fee merchants."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.accounts import account_label
from freerise.cashflow.cycles import Cycle, get_start_day, prev_cycle
from freerise.models import Account, Category, Transaction
from freerise.view import counted

FEES = "עמלות"
NEW_LOOKBACK = 6  # cycles


def fee_key(merchant_key: str) -> str:
    """merchant_key without number-only tokens: fee lines carry dates/amounts
    ("ריבית חובה 01 10 31 10", "עמלת המרה 12 40 usd") that change every month."""
    return " ".join(t for t in merchant_key.split() if not t.isdigit())


@dataclass
class FeeItem:
    txn_id: int
    date: date
    description: str
    account_id: int
    account_name: str
    merchant_key: str
    fee_key: str
    amount: Decimal  # positive


@dataclass
class FeesSummary:
    total: Decimal
    count: int
    items: list[FeeItem]
    previous_total: Decimal
    new_fee_merchants: list[str] = field(default_factory=list)  # fee_keys


def _fees(session: Session, start: date, end: date) -> list[FeeItem]:
    rows = session.execute(
        select(Transaction, Account)
        .join(Account, Account.id == Transaction.account_id)
        .join(Category, Category.id == Transaction.category_id)
        .where(
            counted(),
            Category.name == FEES,
            Transaction.amount < 0,
            Transaction.effective_date >= start,
            Transaction.effective_date <= end,
        )
        .order_by(Transaction.date, Transaction.id)
    )
    return [
        FeeItem(
            t.id,
            t.date,
            t.description,
            a.id,
            account_label(a),
            t.merchant_key,
            fee_key(t.merchant_key),
            -t.amount,
        )
        for t, a in rows
    ]


def _total(items: list[FeeItem]) -> Decimal:
    return sum((x.amount for x in items), Decimal(0))


def fees_in_cycle(session: Session, cycle: Cycle) -> FeesSummary:
    start_day = get_start_day(session)
    items = _fees(session, cycle.start, cycle.end)
    prev = prev_cycle(cycle, start_day)
    oldest = prev
    for _ in range(NEW_LOOKBACK - 1):
        oldest = prev_cycle(oldest, start_day)
    seen = {x.fee_key for x in _fees(session, oldest.start, prev.end)}
    new = list(dict.fromkeys(x.fee_key for x in items if x.fee_key not in seen))
    return FeesSummary(
        _total(items),
        len(items),
        items,
        _total(_fees(session, prev.start, prev.end)),
        new,
    )
