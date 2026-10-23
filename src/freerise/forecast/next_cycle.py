"""Expected fixed charges / income per cycle, installments ending, next-cycle forecast."""

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from operator import attrgetter
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.accounts import account_labels
from freerise.cashflow.cycles import Cycle, cycle_for, day_in_cycle, get_start_day, next_cycle
from freerise.forecast.recurring import recent_previous_account, usual_day
from freerise.models import Account, Category, RecurringItem, RecurringSkip, Transaction
from freerise.view import counted

CADENCE_MONTHS = {"monthly": 1, "bimonthly": 2, "quarterly": 3, "semiannual": 6, "annual": 12}
STALE_DAYS = 7
CHARGED_BASIS = "חויב בפועל במחזור הנוכחי"


@dataclass
class ExpectedLine:
    label: str
    amount: Decimal  # positive
    date: date
    source: Literal["recurring", "installment"]
    basis: str
    charged: bool = False
    account_id: int | None = None  # expected to be charged from / land in
    account_label: str | None = None
    previous_account_label: str | None = None  # set only right after a switch
    # For the home screen: which item/category this is and which cycle txns it matched.
    recurring_id: int | None = None
    category_id: int | None = None
    expected_amount: Decimal | None = None  # the item's own expectation, even once charged
    txn_ids: list[int] = field(default_factory=list)


def _acct(labels: dict[int, str], account_id: int | None, previous: int | None = None) -> dict:
    return {
        "account_id": account_id,
        "account_label": labels.get(account_id),
        "previous_account_label": labels.get(previous),
    }


@dataclass
class ExpectedCycle:
    fixed_items: list[ExpectedLine]
    income_items: list[ExpectedLine]
    fixed_total: Decimal
    income_total: Decimal
    savings_items: list[ExpectedLine] = field(default_factory=list)  # not part of fixed


@dataclass
class NextCycleForecast:
    cycle: Cycle
    fixed_total: Decimal
    income_total: Decimal
    installments_stopping_total: Decimal
    installments_stopping: list[ExpectedLine]
    fixed_items: list[ExpectedLine]
    income_items: list[ExpectedLine]
    delta_fixed_vs_current: Decimal
    basis: str = field(
        default="חיובים קבועים והכנסות מאושרים לפי מחזוריות, ותשלומים שנותרו בעסקאות תשלומים"
    )


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _in(d: date, c: Cycle) -> bool:
    return c.start <= d <= c.end


def _txns(session: Session, *where) -> list[Transaction]:
    return list(
        session.scalars(
            select(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .where(counted(), *where)
            .order_by(Transaction.date, Transaction.id)
        )
    )


def _series(session: Session) -> list[list[Transaction]]:
    """Installment series: same account, merchant_key, installment_total, amount within ±1 ₪."""
    groups: dict[tuple, list[Transaction]] = defaultdict(list)
    for t in _txns(
        session, Transaction.installment_total > 1, Transaction.installment_number.is_not(None)
    ):
        groups[(t.account_id, t.merchant_key, t.installment_total)].append(t)
    out = []
    for txns in groups.values():
        # ponytail: two identical concurrent purchases at one merchant merge into one series
        txns.sort(key=lambda t: t.amount)
        cur: list[Transaction] = []
        for t in txns:
            if cur and abs(t.amount - cur[0].amount) > 1:
                out.append(cur)
                cur = []
            cur.append(t)
        out.append(cur)
    return out


def _bucket(session: Session, it: RecurringItem) -> str:
    """income | savings | fixed — savings-group deposits are their own line, not fixed."""
    if it.direction == "income":
        return "income"
    cid = it.category_id or session.scalar(
        select(Transaction.category_id)
        .where(Transaction.merchant_key == it.merchant_key, Transaction.amount < 0)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(1)
    )
    group = cid and session.scalar(select(Category.group).where(Category.id == cid))
    return "savings" if group == "savings" else "fixed"


def _recurring_lines(session: Session, cycle: Cycle, today: date) -> list[tuple[str, ExpectedLine]]:
    items = session.scalars(select(RecurringItem).where(RecurringItem.status == "confirmed"))
    labels = account_labels(session)
    charged: dict[tuple[str, str], list] = {}
    for t in _txns(
        session, Transaction.effective_date >= cycle.start, Transaction.effective_date <= cycle.end
    ):
        e = charged.setdefault(
            (t.merchant_key, "expense" if t.amount < 0 else "income"), [0, t.date, None, []]
        )
        e[0] += abs(t.amount)
        e[2] = t.account_id  # latest charge's account
        e[3].append(t.id)
    history: dict[str, list[date]] = defaultdict(list)  # income occurrences, real dates
    for k, d in session.execute(
        select(Transaction.merchant_key, Transaction.date)
        .join(Account, Account.id == Transaction.account_id)
        .join(
            RecurringItem,
            (RecurringItem.merchant_key == Transaction.merchant_key)
            & (RecurringItem.direction == "income")
            & (RecurringItem.status == "confirmed"),
        )
        .where(Account.excluded.is_(False), Transaction.amount > 0)
    ):
        history[k].append(d)
    skipped = set(
        session.scalars(
            select(RecurringSkip.recurring_id).where(RecurringSkip.cycle_start == cycle.start)
        )
    )
    out = []
    for it in items:
        hit = charged.get((it.merchant_key, it.direction))
        if not hit and it.id in skipped:
            continue  # the user said it won't happen this cycle
        prev = recent_previous_account(it, today)
        if hit:  # checked before staleness: next_expected_date may not be advanced yet
            line = ExpectedLine(
                it.label,
                hit[0],
                hit[1],
                "recurring",
                CHARGED_BASIS,
                True,
                **_acct(labels, hit[2], prev),
                txn_ids=hit[3],
            )
        else:
            if it.direction == "income" and it.cadence == "monthly":
                # Every cycle at its usual day, so a late salary counted for the previous
                # cycle doesn't make this cycle's own expected salary disappear.
                if not it.user_defined and it.next_expected_date < today - timedelta(
                    days=STALE_DAYS
                ):
                    continue  # stream stopped (a user-defined one never does)
                seen = history.get(it.merchant_key, [])
                if cycle.end < min([*seen, it.created_at.date()]):
                    continue  # before it existed
                day = usual_day(it.expected_day, [x.day for x in seen]) if seen else None
                d = day_in_cycle(day or it.expected_day or it.next_expected_date.day, cycle)
            else:
                if it.next_expected_date < today - timedelta(days=STALE_DAYS):
                    continue  # stream stopped
                d, k, step = it.next_expected_date, 0, CADENCE_MONTHS[it.cadence]
                while d < cycle.start:
                    k += step
                    d = add_months(it.next_expected_date, k)
                if not _in(d, cycle):
                    continue
            line = ExpectedLine(
                it.label,
                it.expected_amount,
                d,
                "recurring",
                it.basis,
                **_acct(labels, it.account_id, prev),
            )
        line.recurring_id, line.category_id = it.id, it.category_id
        line.expected_amount = it.expected_amount
        out.append((_bucket(session, it), line))
    return out


def _installment_lines(session: Session, cycle: Cycle) -> list[ExpectedLine]:
    labels = account_labels(session)
    out = []
    for s in _series(session):
        latest = max(s, key=lambda t: (t.installment_number, t.date))
        n, total = latest.installment_number, latest.installment_total
        here = [t for t in s if _in(t.effective_date, cycle)]
        if here:
            amt = sum(abs(t.amount) for t in here)
            basis = f"{CHARGED_BASIS} (תשלום {here[-1].installment_number} מתוך {total})"
            out.append(
                ExpectedLine(
                    latest.description,
                    amt,
                    here[-1].date,
                    "installment",
                    basis,
                    True,
                    **_acct(labels, latest.account_id),
                    category_id=latest.category_id,
                    expected_amount=amt,
                    txn_ids=[t.id for t in here],
                )
            )
            continue
        for k in range(1, total - n + 1):
            d = add_months(latest.date, k)
            if _in(d, cycle):
                basis = f"תשלום {n + k} מתוך {total}, לפי התשלום האחרון שנראה ({n})"
                out.append(
                    ExpectedLine(
                        latest.description,
                        abs(latest.amount),
                        d,
                        "installment",
                        basis,
                        **_acct(labels, latest.account_id),
                        category_id=latest.category_id,
                        expected_amount=abs(latest.amount),
                    )
                )
    return out


def expected_in_cycle(session: Session, cycle: Cycle, today: date) -> ExpectedCycle:
    rec = _recurring_lines(session, cycle, today)
    by_date = attrgetter("date")
    fixed = sorted(
        [ln for b, ln in rec if b == "fixed"] + _installment_lines(session, cycle), key=by_date
    )
    income = sorted((ln for b, ln in rec if b == "income"), key=by_date)
    return ExpectedCycle(
        fixed,
        income,
        sum((x.amount for x in fixed), Decimal(0)),
        sum((x.amount for x in income), Decimal(0)),
        [ln for b, ln in rec if b == "savings"],
    )


def installments_ending(session: Session, cycle: Cycle) -> list[ExpectedLine]:
    """Final installments charged in `cycle` — these amounts stop next cycle."""
    labels = account_labels(session)
    return [
        ExpectedLine(
            t.description,
            abs(t.amount),
            t.date,
            "installment",
            f"תשלום אחרון ({t.installment_number} מתוך {t.installment_total}) — לא יחויב במחזור הבא",
            True,
            **_acct(labels, t.account_id),
        )
        for t in _txns(
            session,
            Transaction.installment_total > 1,
            Transaction.installment_number == Transaction.installment_total,
            Transaction.effective_date >= cycle.start,
            Transaction.effective_date <= cycle.end,
        )
    ]


def next_cycle_forecast(session: Session, today: date) -> NextCycleForecast:
    start_day = get_start_day(session)
    cur = cycle_for(today, start_day)
    nxt = next_cycle(cur, start_day)
    ec = expected_in_cycle(session, nxt, today)
    stopping = installments_ending(session, cur)
    return NextCycleForecast(
        nxt,
        ec.fixed_total,
        ec.income_total,
        sum((x.amount for x in stopping), Decimal(0)),
        stopping,
        ec.fixed_items,
        ec.income_items,
        ec.fixed_total - expected_in_cycle(session, cur, today).fixed_total,
    )
