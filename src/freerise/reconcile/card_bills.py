"""Match each bank-side credit card bill (one line) against the card's individual charges."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from freerise.cashflow.cycles import Cycle
from freerise.config import get_settings
from freerise.models import Account, Category, Credential, Transaction

# Provider key -> bank description patterns (lowercase). Checked in order.
ISSUER_PATTERNS = {
    "isracard": ["ישראכרט"],
    "amex": ["אמריקן אקספרס", "amex"],
    "max": ["מקס איט", "max it", "לאומי קארד"],
    # "כרטיסי אשראי לישראל" is Cal; bare "כאל" is too broad (מיכאל).
    "visa cal": ["מ-כאל", " כאל", "כ.א.ל", "כרטיסי אשראי", "cal "],
    "diners": ["דיינרס", "diners"],  # no scraper: always unknown_card
}


# Reconciliation runs on its own; only problems surface, in the data-health section.
HEALTH_LINK = "/accounts#health"


def cards_synced_after(s: Session, issuer: str, d: date) -> bool:
    """Every enabled card credential of the issuer synced after d (so its bill is visible)."""
    tz = ZoneInfo(get_settings().tz)
    stamps = s.scalars(
        select(Credential.last_success_at).where(
            Credential.provider == issuer, Credential.enabled, Credential.verified
        )
    ).all()
    return all(x is not None and x.astimezone(tz).date() > d for x in stamps)


ISSUER_NAMES = {
    "isracard": "ישראכרט",
    "amex": "אמריקן אקספרס",
    "max": "מקס",
    "visa cal": "כאל",
    "diners": "דיינרס",
}
WINDOW = timedelta(days=5)  # bank debit date vs card processed_date (billing date)
NEAR = timedelta(days=35)
TOL = Decimal(1)
MAX_ACCOUNTS = 12

Status = Literal["matched", "mismatch", "unknown_card"]


@dataclass
class BillReconciliation:
    bank_txn_id: int
    date: date
    amount: Decimal  # positive
    issuer: str | None
    status: Status
    matched_accounts: list[dict] = field(default_factory=list)  # {id, name, excluded}
    card_total: Decimal = Decimal(0)  # positive = spend
    gap: Decimal = Decimal(0)  # bank amount - card_total
    suggestions: list[dict] = field(default_factory=list)

    @property
    def matched_account_ids(self) -> list[int]:
        return [a["id"] for a in self.matched_accounts]


def issuer_of(description: str) -> str | None:
    d = f" {description.lower()} "  # padded so " כאל" / "cal " match at the edges
    for issuer, pats in ISSUER_PATTERNS.items():
        if any(p in d for p in pats):
            return issuer
    return None


def _bills():
    return (
        select(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Account.kind == "bank",
            Account.excluded.is_(False),
            Category.group == "card_bill",
            Transaction.amount < 0,
        )
    )


def _spend(txns) -> Decimal:
    return -sum((t.amount for t in txns), Decimal(0))


def _suggest(t: Transaction, reason: str) -> dict:
    return {
        "txn_id": t.id,
        "description": t.description,
        "amount": t.amount,
        "date": t.date,
        "account_id": t.account_id,
        "reason": reason,
    }


def _issuer_accounts(session: Session, issuer: str) -> dict[int, Account]:
    # Excluded card accounts count too: the bank still pays them.
    q = (
        select(Account)
        .join(Credential, Credential.id == Account.credential_id)
        .where(Credential.provider == issuer, Account.kind == "card")
    )
    return {a.id: a for a in session.scalars(q)}


def _reconcile(session: Session, bill: Transaction) -> BillReconciliation:
    amount = -bill.amount
    issuer = issuer_of(bill.description)
    r = BillReconciliation(bill.id, bill.date, amount, issuer, "unknown_card", gap=amount)
    accounts = _issuer_accounts(session, issuer) if issuer else {}
    if not accounts:
        return r
    near = list(
        session.scalars(
            select(Transaction).where(
                Transaction.account_id.in_(accounts),
                Transaction.processed_date.between(bill.date - NEAR, bill.date + NEAR),
            )
        )
    )
    lo, hi = bill.date - WINDOW, bill.date + WINDOW
    window = [t for t in near if lo <= t.processed_date <= hi and t.status == "completed"]
    per_acct = {a: _spend(t for t in window if t.account_id == a) for a in accounts}
    # ponytail: all subsets of the 12 busiest cards (2^12 combos); go DP/greedy past that.
    ids = sorted((a for a in per_acct if per_acct[a]), key=lambda a: -abs(per_acct[a]))
    ids = ids[:MAX_ACCOUNTS]
    best: tuple[int, ...] = ()
    best_gap = amount
    for n in range(1, len(ids) + 1):
        for combo in combinations(ids, n):
            g = amount - sum(per_acct[a] for a in combo)
            if abs(g) < abs(best_gap):
                best, best_gap = combo, g
    r.card_total, r.gap = amount - best_gap, best_gap
    r.status = "matched" if abs(best_gap) <= TOL else "mismatch"
    if r.status == "mismatch" and _split_debit_matches(
        session, bill, issuer, sum(per_acct.values())
    ):
        # One card bill split across several bank debits (or several cards paid together):
        # each debit's share is reported as matched against the issuer's whole window.
        best = tuple(ids)
        r.status, r.card_total, r.gap = "matched", amount, Decimal(0)
    r.matched_accounts = [
        {"id": a, "name": accounts[a].display_name, "excluded": accounts[a].excluded} for a in best
    ]
    if r.status == "matched":
        return r
    counted = {t.id for t in window if t.account_id in best}
    for t in window:
        cur = (t.raw or {}).get("charged_currency")
        if t.id in counted and cur not in (None, "ILS"):
            r.suggestions.append(_suggest(t, "חיוב במט״ח — ייתכן שהסכום אינו בש״ח"))
    pending_from = lo - timedelta(days=31)
    for t in sorted(near, key=lambda t: abs(t.processed_date - bill.date)):
        if t.id in counted:
            continue
        if t.status == "pending":
            # Pending card txns carry the purchase date as processed_date (vendor scrapers).
            mine = t.account_id in best or not best
            if mine and pending_from <= t.processed_date <= hi:
                r.suggestions.append(_suggest(t, "עסקה ממתינה שטרם נקלטה בחיוב"))
        elif abs(t.amount + best_gap) <= TOL:  # gap > 0: a missing purchase of -gap
            reason = "חויבה בחיוב אחר של הכרטיס" if t.account_id in best else "סכום זהה לפער"
            r.suggestions.append(_suggest(t, reason))
    return r


def _split_debit_matches(session: Session, bill: Transaction, issuer: str, spend: Decimal) -> bool:
    lo, hi = bill.date - WINDOW, bill.date + WINDOW
    siblings = [
        b
        for b in session.scalars(_bills().where(Transaction.date.between(lo, hi)))
        if issuer_of(b.description) == issuer
    ]
    total = -sum((b.amount for b in siblings), Decimal(0))
    return len(siblings) > 1 and abs(total - spend) <= TOL


def latest_bill_date(session: Session) -> date | None:
    return session.scalar(_bills().with_only_columns(func.max(Transaction.date)))


def reconcile_bill(session: Session, bank_txn_id: int) -> BillReconciliation | None:
    bill = session.scalar(_bills().where(Transaction.id == bank_txn_id))
    return None if bill is None else _reconcile(session, bill)


def reconcile_range(session: Session, start: date, end: date) -> list[BillReconciliation]:
    q = _bills().where(Transaction.date.between(start, end)).order_by(Transaction.date)
    return [_reconcile(session, b) for b in session.scalars(q)]


def reconcile_cycle(session: Session, cycle: Cycle) -> list[BillReconciliation]:
    return reconcile_range(session, cycle.start, cycle.end)
