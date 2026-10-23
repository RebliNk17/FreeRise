"""Detect recurring charges and income streams from transaction history."""

from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from statistics import median, quantiles

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from freerise.categorize.normalize import _is_ref
from freerise.models import Account, Category, RecurringItem, Transaction

CADENCE_BANDS = {
    "monthly": (25, 35),
    "bimonthly": (54, 68),
    "quarterly": (82, 100),
    "semiannual": (165, 200),
    "annual": (340, 390),
}
CADENCE_HE = {
    "monthly": "כל חודש",
    "bimonthly": "כל ~2 חודשים",
    "quarterly": "כל ~3 חודשים",
    "semiannual": "כל ~חצי שנה",
    "annual": "כל שנה",
}
LOOKBACK_DAYS = 400
NON_SPENDING = ("transfer", "card_bill", "ignore")
STATUSES = ("pending", "confirmed", "dismissed")
CENT = Decimal("0.01")
SWITCH_DAYS = 60  # how long a "moved to another card" note stays visible
# Auto-confirm: the latest AUTO_N monthly occurrences, one cycle apart, similar amount and day.
AUTO_N = 3
AUTO_AMOUNT = Decimal("0.10")  # each within ±10% of their median
AUTO_DAYS = 4  # day-of-month spread at most this


def strong_monthly(occ: list[tuple[date, Decimal]]) -> bool:
    """A sure fixed charge/income: confirmed automatically (uncertain ones stay pending,
    silently; the user can undo from the transaction sheet)."""
    last = occ[-AUTO_N:]
    if len(last) < AUTO_N:
        return False
    lo, hi = CADENCE_BANDS["monthly"]
    if not all(lo <= (b - a).days <= hi for (a, _), (b, _) in pairwise(last)):
        return False
    med = median(a for _, a in last)
    days = [d.day for d, _ in last]
    # day of month is circular: the 30th and the 1st are 1-2 days apart
    near = all(min(abs(x - y), 31 - abs(x - y)) <= AUTO_DAYS for x in days for y in days)
    return near and all(abs(a - med) <= med * AUTO_AMOUNT for _, a in last)


def clean_label(description: str, fallback: str) -> str:
    """Merchant name for display: original casing, reference codes dropped, max 40 chars."""
    toks = [t for t in description.split() if not _is_ref(t.lower())]
    return " ".join(toks)[:40].strip() or fallback


def _cadence(dates: list[date]) -> tuple[str, int] | None:
    gaps = [(b - a).days for a, b in pairwise(dates)]
    if not gaps:
        return None
    med = median(gaps)
    for name, (lo, hi) in CADENCE_BANDS.items():
        if lo <= med <= hi:
            min_n = 2 if name in ("semiannual", "annual") else 3
            in_band = sum(lo <= g <= hi for g in gaps)
            if len(dates) >= min_n and in_band >= 0.75 * len(gaps):
                return name, round(med)
            return None
    return None


def _estimate(
    occ: list[tuple[date, Decimal]], direction: str, fixed: bool, next_date: date
) -> tuple[Decimal, str]:
    amounts = [a for _, a in occ]
    if direction == "income":
        last6 = amounts[-6:]
        q1 = quantiles(last6, n=4, method="inclusive")[0] if len(last6) > 1 else last6[0]
        return Decimal(q1), f"אחוזון 25 של {len(last6)} הכנסות אחרונות"
    if fixed:
        return median(amounts[-3:]), "חציון 3 חיובים אחרונים"
    target = next_date - timedelta(days=365)
    near = [(abs((d - target).days), a) for d, a in occ if abs((d - target).days) <= 20]
    if near:
        return min(near)[1], "לפי אותה תקופה בשנה שעברה"
    last6 = amounts[-6:]
    return median(last6), f"ממוצע חציוני של {len(last6)} חיובים אחרונים"


def _track_account(item: RecurringItem, txns: list[Transaction]) -> None:
    """account_id = account of the latest occurrence; on a switch remember the old one."""
    cur = txns[-1].account_id
    i = next((i for i in range(len(txns) - 1, -1, -1) if txns[i].account_id != cur), None)
    if i is not None:  # switch visible in history...
        # ...unless cur was also charged in the 2 occurrences before it (paid from two cards).
        if all(t.account_id != cur for t in txns[max(0, i - 1) : i + 1]):
            item.previous_account_id = txns[i].account_id
            item.account_changed_on = txns[i + 1].date
    elif item.account_id is not None and item.account_id != cur:  # older history aged out
        item.previous_account_id, item.account_changed_on = item.account_id, txns[-1].date
    item.account_id = cur


def detect_recurring(session: Session, today: date) -> list[RecurringItem]:
    """Upsert detected items (flush only; caller commits). Returns non-dismissed detections."""
    rows = session.execute(
        select(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Account.excluded.is_(False),
            or_(Category.id.is_(None), Category.group.not_in(NON_SPENDING)),
            or_(Transaction.installment_total.is_(None), Transaction.installment_total <= 1),
            Transaction.date >= today - timedelta(days=LOOKBACK_DAYS),
            Transaction.merchant_key != "",
            Transaction.amount != 0,
        )
        .order_by(Transaction.date, Transaction.id)
    ).scalars()

    groups: dict[tuple[str, str], list[Transaction]] = defaultdict(list)
    for t in rows:
        groups[(t.merchant_key, "expense" if t.amount < 0 else "income")].append(t)

    existing = {(r.merchant_key, r.direction): r for r in session.scalars(select(RecurringItem))}
    out = []
    for (key, direction), txns in groups.items():
        by_day: dict[date, Decimal] = defaultdict(Decimal)
        for t in txns:  # same-day duplicates are one occurrence
            by_day[t.date] += abs(t.amount)
        occ = sorted(by_day.items())
        found = _cadence([d for d, _ in occ])
        if not found:
            continue
        cadence, gap = found
        row = existing.get((key, direction))
        last_date = occ[-1][0]
        if (today - last_date).days > 2 * CADENCE_BANDS[cadence][1]:  # stream stopped
            if row is not None and row.status == "pending":
                session.delete(row)
            continue
        amounts = [a for _, a in occ]
        med = median(amounts)
        fixed = sum(abs(a - med) <= med * Decimal("0.15") for a in amounts) >= 0.75 * len(amounts)
        next_date = last_date + timedelta(days=gap)
        while next_date < today:
            next_date += timedelta(days=gap)
        amount, how = _estimate(occ, direction, fixed, next_date)
        if row is not None and row.user_defined:  # the user's day/amount win
            row.last_date = last_date
            if row.amount_kind == "variable":
                row.expected_amount = Decimal(amount).quantize(CENT)
            _track_account(row, txns)
            if row.status != "dismissed":
                out.append(row)
            continue
        last = txns[-1]
        cat = session.get(Category, last.category_id) if last.category_id else None
        label = clean_label(last.description, key)
        item = row or RecurringItem(merchant_key=key, direction=direction, status="pending")
        item.label = label
        item.category_id = last.category_id
        item.cadence = cadence
        item.amount_kind = "fixed" if fixed else "variable"
        item.expected_amount = Decimal(amount).quantize(CENT)
        item.last_date = last_date
        item.next_expected_date = next_date
        item.basis = f"{label}{f' · {cat.name}' if cat else ''}: {how}, {CADENCE_HE[cadence]}"
        _track_account(item, txns)
        if item.status == "pending" and cadence == "monthly" and strong_monthly(occ):
            item.status = "confirmed"  # never touches dismissed (the user said no)
        session.add(item)
        if item.status != "dismissed":
            out.append(item)
    session.flush()
    return out


def recent_previous_account(item: RecurringItem, today: date) -> int | None:
    """previous_account_id if the item switched accounts in the last SWITCH_DAYS."""
    if item.account_changed_on and (today - item.account_changed_on).days <= SWITCH_DAYS:
        return item.previous_account_id
    return None


def usual_day(expected_day: int | None, days: list[int]) -> int:
    """The user's expected day, else the median day of month of the occurrences."""
    # ponytail: plain median; a stream straddling month end (30, 1, 31) lands mid-month
    return expected_day or int(median(days))


def mark_fixed_income(
    session: Session,
    merchant_key: str,
    label: str,
    category_id: int | None,
    account_id: int | None,
    last_date: date,
    expected_day: int,
    expected_amount: Decimal,
    amount_given: bool,
) -> RecurringItem:
    """Upsert a user-defined monthly income (flush only). next_expected_date = the first
    date after last_date on expected_day (clamped to short months)."""
    item = session.scalar(
        select(RecurringItem).where(
            RecurringItem.merchant_key == merchant_key, RecurringItem.direction == "income"
        )
    ) or RecurringItem(merchant_key=merchant_key, direction="income", label=label)
    d = last_date.replace(day=min(expected_day, monthrange(last_date.year, last_date.month)[1]))
    if d <= last_date:
        y, m = divmod(last_date.month, 12)
        y, m = last_date.year + y, m + 1
        d = date(y, m, min(expected_day, monthrange(y, m)[1]))
    item.category_id = item.category_id or category_id
    item.cadence = "monthly"
    item.amount_kind = "fixed" if amount_given else "variable"
    item.expected_amount = Decimal(expected_amount).quantize(CENT)
    item.last_date = max(item.last_date or last_date, last_date)
    item.next_expected_date = d
    item.status = "confirmed"
    item.user_defined = True
    item.expected_day = expected_day
    item.account_id = account_id
    item.basis = f"{item.label}: הכנסה קבועה שהגדרת, בכל חודש ב-{expected_day}"
    session.add(item)
    session.flush()
    return item


def set_status(session: Session, item_id: int, status: str) -> RecurringItem:
    if status not in STATUSES:
        raise ValueError(f"bad status {status!r}")
    item = session.get(RecurringItem, item_id)
    if item is None:
        raise LookupError(item_id)
    item.status = status
    session.flush()
    return item
