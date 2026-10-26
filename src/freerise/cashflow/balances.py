"""Bank balances and upcoming card charges, shared by the plan API and the insights engine."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from freerise.accounts import latest_balances
from freerise.cashflow.cycles import Cycle
from freerise.models import Account, Transaction
from freerise.view import counted


@dataclass
class Balances:
    bank_total: Decimal | None  # None when no bank balance is known
    banks: list[tuple[Account, Decimal | None, datetime | None]]  # non-excluded bank accounts
    upcoming_card_charges: Decimal  # positive
    # Per card, on the same basis as the total: (account, upcoming charge (credit < 0), as_of).
    cards: list[tuple[Account, Decimal, datetime | None]]


def balances(session: Session, cycle: Cycle) -> Balances:
    latest = latest_balances().subquery()
    rows = session.execute(
        select(Account, latest.c.balance, latest.c.as_of)
        .options(joinedload(Account.credential))
        .outerjoin(latest, latest.c.account_id == Account.id)
        .where(counted())
        .order_by(Account.id)
    ).all()
    banks = [(a, b, t) for a, b, t in rows if a.kind == "bank"]
    known = [b for _, b, _ in banks if b is not None]
    cards = [(a, b, t) for a, b, t in rows if a.kind == "card"]
    if any(b is not None for _, b, _ in cards):
        per_card = [(a, -(b or Decimal(0)), t) for a, b, t in cards]
    else:  # no card balance from the provider: this cycle's card charges so far
        spent = dict(
            session.execute(
                select(Transaction.account_id, func.sum(Transaction.amount))
                .join(Account, Account.id == Transaction.account_id)
                .where(
                    Account.kind == "card",
                    counted(),
                    Transaction.amount < 0,
                    Transaction.date >= cycle.start,
                    Transaction.date <= cycle.end,
                )
                .group_by(Transaction.account_id)
            ).all()
        )
        per_card = [(a, -Decimal(spent.get(a.id, 0)), None) for a, _, _ in cards]
    upcoming = abs(sum((c for _, c, _ in per_card), Decimal(0)))
    return Balances(sum(known, Decimal(0)) if known else None, banks, upcoming, per_card)
