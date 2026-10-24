"""Data health ("בדיקת תקינות"): is everything syncing and adding up?"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from freerise.accounts import PROVIDER_HE, account_label, active_card_ids
from freerise.models import Account, Credential, Transaction
from freerise.reconcile.card_bills import reconcile_range

MONTHS = 12  # look back this far for months with no data
IDLE_DAYS = 90
BILL_DAYS = 90


@dataclass
class ConnectionHealth:
    id: int
    label: str
    provider: str
    owner: str
    enabled: bool
    last_success_at: datetime | None
    last_error: str | None
    months_without_data: list[str] = field(default_factory=list)  # "2026-03", oldest first


@dataclass
class IdleAccount:
    id: int
    label: str
    kind: str
    last_txn: date | None


@dataclass
class BillIssue:
    bank_txn_id: int
    date: date
    issuer: str  # Hebrew name, or "" when unknown
    amount: Decimal  # the bank-side bill, positive
    status: str  # mismatch | unknown_card
    gap: Decimal  # bank amount − card charges we have


@dataclass
class DataHealth:
    connections: list[ConnectionHealth]
    idle_accounts: list[IdleAccount]
    card_bills: list[BillIssue]
    uncategorized: int

    @property
    def ok(self) -> bool:
        return not (
            self.idle_accounts
            or self.card_bills
            or self.uncategorized
            or any(c.months_without_data or c.last_error for c in self.connections)
        )


def _months(today: date, n: int) -> list[date]:
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append(date(y, m, 1))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out[::-1]


def data_health(session: Session, today: date) -> DataHealth:
    creds = list(session.scalars(select(Credential).where(Credential.verified.is_(True))))
    accounts = list(
        session.scalars(
            select(Account)
            .options(joinedload(Account.credential))
            .where(Account.excluded.is_(False), Account.kind != "fund")
        )
    )
    # (credential, month) pairs with any transaction; last txn per account
    months = _months(today.replace(day=1) - timedelta(days=1), MONTHS)  # complete months
    since = months[0]
    seen = {
        (cid, m.date() if isinstance(m, datetime) else m)
        for cid, m in session.execute(
            select(Account.credential_id, func.date_trunc("month", Transaction.date))
            .join(Account, Account.id == Transaction.account_id)
            .where(Transaction.date >= since)
            .distinct()
        )
    }
    first = dict(
        session.execute(
            select(Account.credential_id, func.min(Transaction.date))
            .join(Account, Account.id == Transaction.account_id)
            .group_by(Account.credential_id)
        ).all()
    )
    last = dict(
        session.execute(
            select(Transaction.account_id, func.max(Transaction.date)).group_by(
                Transaction.account_id
            )
        ).all()
    )
    has_accounts = {a.credential_id for a in accounts}
    conns = []
    for c in creds:
        gaps = []
        if c.id in has_accounts and c.id in first:  # funds/pension have no monthly txns
            start = first[c.id].replace(day=1)
            gaps = [f"{m:%Y-%m}" for m in months if m >= start and (c.id, m) not in seen]
        conns.append(
            ConnectionHealth(
                c.id,
                c.label,
                PROVIDER_HE.get(c.provider, c.provider),
                c.owner,
                c.enabled,
                c.last_success_at,
                c.last_error,
                gaps,
            )
        )
    # Expired/replaced cards (no charge in 6 months, no balance) aren't a problem, just old.
    active = active_card_ids(session, accounts)
    idle = [
        IdleAccount(a.id, account_label(a), a.kind, last.get(a.id))
        for a in accounts
        if a.id in active and (last.get(a.id) or date.min) < today - timedelta(days=IDLE_DAYS)
    ]
    bills = [
        BillIssue(
            b.bank_txn_id,
            b.date,
            PROVIDER_HE.get(b.issuer or "", ""),
            b.amount,
            b.status,
            b.gap,
        )
        for b in reconcile_range(session, today - timedelta(days=BILL_DAYS), today)
        if b.status != "matched"
    ]
    uncategorized = session.scalar(
        select(func.count())
        .select_from(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .where(Account.excluded.is_(False), Transaction.category_id.is_(None))
    )
    return DataHealth(conns, idle, bills, uncategorized)
