"""Bank balances and upcoming card charges, shared by the plan API and the insights engine."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, joinedload

from freerise.cashflow.cycles import Cycle
from freerise.models import Account, Balance, Transaction


@dataclass
class Balances:
    bank_total: Decimal | None  # None when no bank balance is known
    banks: list[tuple[Account, Decimal | None, datetime | None]]  # non-excluded bank accounts
    upcoming_card_charges: Decimal  # positive


def balances(session: Session, cycle: Cycle) -> Balances:
    latest = (
        select(Balance.account_id, Balance.balance, Balance.as_of)
        .ext(distinct_on(Balance.account_id))
        .order_by(Balance.account_id, Balance.as_of.desc())
        .subquery()
    )
    rows = session.execute(
        select(Account, latest.c.balance, latest.c.as_of)
        .options(joinedload(Account.credential))
        .outerjoin(latest, latest.c.account_id == Account.id)
        .where(Account.excluded.is_(False))
        .order_by(Account.id)
    ).all()
    banks = [(a, b, t) for a, b, t in rows if a.kind == "bank"]
    known = [b for _, b, _ in banks if b is not None]
    card_bals = [b for a, b, _ in rows if a.kind == "card" and b is not None]
    if card_bals:
        upcoming = abs(sum(card_bals, Decimal(0)))
    else:  # no card balance from the provider: this cycle's card charges so far
        upcoming = abs(
            session.scalar(
                select(func.coalesce(func.sum(Transaction.amount), 0))
                .join(Account, Account.id == Transaction.account_id)
                .where(
                    Account.kind == "card",
                    Account.excluded.is_(False),
                    Transaction.amount < 0,
                    Transaction.date >= cycle.start,
                    Transaction.date <= cycle.end,
                )
            )
        )
    return Balances(sum(known, Decimal(0)) if known else None, banks, Decimal(upcoming))
