"""Missing, late, short and raised employer deposits, per fund and employer.

Months are salary months when the portal gives them (Migdal), else deposit months (value
dates). An employer that deposits monthly should show one in every month whose due date is more
than GRACE days before the fund's newest data (its latest snapshot). Due: a salary month's money
by the 15th of the next month; a deposit month's on the employer's usual day of the month.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from freerise.cashflow.cycles import HE_MONTHS
from freerise.models import Fund, FundDeposit, FundSnapshot

LOOKBACK = 12  # months reported; older gaps are history, not news
ENDED_AFTER = 3  # this many empty months at the end -> the job ended, not a missed deposit
SHORT = Decimal("0.75")  # under 75% of the usual amount
UP = Decimal("1.05")  # 5% above usual and above last month: a raise (or a bonus)
CATCH_UP = Decimal("1.6")  # this far above usual right after an empty month = the late deposit
GRACE = timedelta(days=45)  # deposits may come up to ~a month after the due date: not missing
SALARY_DUE_DAY = 15  # a salary month's deposit is due by the 15th of the next month
USUAL_OF = 6  # usual = median of this many previous deposit months


@dataclass
class DepositAlert:
    kind: str  # missing|late|short|up
    fund_id: int
    fund_name: str
    company: str | None
    product_type: str
    employer: str
    month: date  # first of the deposit month
    amount: Decimal  # what arrived (0 if missing; for late, the catch-up month's total)
    usual: Decimal  # median of the employer's previous monthly totals
    days_late: int | None = None  # late: days after the due date it arrived


def _employer(raw: dict | None) -> str | None:
    """Employer from the scraper's "הפקדה - <employer>"; None for transfers between funds."""
    d = (raw or {}).get("description") or ""
    return None if d.startswith("העברה") else d.partition(" - ")[2].strip()


def _salary_month(d: FundDeposit) -> date | None:
    sm = ((d.raw or {}).get("details") or {}).get("salary_month")  # "YYYY-MM"
    return date(int(sm[:4]), int(sm[5:7]), 1) if sm else None


def _next(m: date) -> date:
    return date(m.year + 1, 1, 1) if m.month == 12 else date(m.year, m.month + 1, 1)


def _prev(m: date) -> date:
    return date(m.year - 1, 12, 1) if m.month == 1 else date(m.year, m.month - 1, 1)


def _check(
    amounts: dict[date, Decimal],
    arrived: dict[date, date],
    due: Callable[[date], date],
    as_of: date,
) -> list[tuple[str, date, Decimal, Decimal, int | None]]:
    """(kind, month, amount, usual, days_late) for one employer's monthly totals; `arrived` is
    each month's last deposit date."""
    months, m = [], min(amounts)
    while due(m) + GRACE <= as_of:
        months.append(m)
        m = _next(m)
    trailing = 0
    while trailing < len(months) and months[-1 - trailing] not in amounts:
        trailing += 1
    if trailing >= ENDED_AFTER:
        months = months[: len(months) - trailing]
    out = []
    for i, m in enumerate(months):
        prior = [amounts[x] for x in months[:i] if x in amounts][-USUAL_OF:]
        if not prior:
            continue
        usual = Decimal(median(prior))
        if m not in amounts:
            prv, nxt = months[i - 1], months[i + 1] if i + 1 < len(months) else None
            if prv in amounts and amounts[prv] >= CATCH_UP * usual:
                continue  # deposited early: two in the month before (e.g. 4.3 and 30.3)
            if nxt in amounts and amounts[nxt] >= CATCH_UP * usual:
                late = (arrived[nxt] - due(m)).days
                if late > GRACE.days:  # within the grace it just came a month on: fine
                    out.append(("late", m, amounts[nxt], usual, late))
            else:
                out.append(("missing", m, Decimal(0), usual, None))
        elif len(prior) >= 3 and (last := amounts.get(_prev(m))):
            # Compared with last month too, so a lasting change is reported once.
            if amounts[m] < SHORT * min(usual, last):
                out.append(("short", m, amounts[m], usual, None))
            elif amounts[m] >= UP * max(usual, last) and not (
                _next(m) in months and _next(m) not in amounts  # next month's, paid early
            ):
                out.append(("up", m, amounts[m], usual, None))
    return [a for a in out if a[1] in months[-LOOKBACK:]]


def deposit_alerts(s: Session) -> list[DepositAlert]:
    """Newest first."""
    out = []
    for f in s.scalars(select(Fund).order_by(Fund.id)):
        as_of = s.scalar(select(func.max(FundSnapshot.as_of)).where(FundSnapshot.fund_id == f.id))
        if as_of is None:
            continue
        rows: dict[str, list[FundDeposit]] = {}
        for d in s.scalars(select(FundDeposit).where(FundDeposit.fund_id == f.id)):
            if (e := _employer(d.raw)) is not None:
                rows.setdefault(e, []).append(d)
        for emp, deps in rows.items():
            amounts: dict[date, Decimal] = {}
            arrived: dict[date, date] = {}
            salary = all(_salary_month(d) for d in deps)
            for d in deps:
                k = _salary_month(d) if salary else d.date.replace(day=1)
                amounts[k] = amounts.get(k, Decimal(0)) + d.amount
                arrived[k] = max(arrived.get(k, d.date), d.date)
            # Always the 1st = also salary months (Migdal before details were kept).
            if salary or {d.date.day for d in deps} == {1}:
                due = lambda m: _next(m).replace(day=SALARY_DUE_DAY)
            else:
                day = min(int(median(d.date.day for d in deps)), 28)
                due = lambda m, day=day: m.replace(day=day)
            out += [
                DepositAlert(
                    kind, f.id, f.name, f.company, f.product_type, emp, m, amount, usual, late
                )
                for kind, m, amount, usual, late in _check(amounts, arrived, due, as_of)
            ]
    return sorted(out, key=lambda a: a.month, reverse=True)


def ils2(x) -> str:
    return f"₪{Decimal(x):,.2f}"


def message(a: DepositAlert) -> tuple[str, str]:
    """(title, body) in Hebrew; exact amounts."""
    fund = f"{a.fund_name} ({a.company})" if a.company else a.fund_name
    frm = f"מ{a.employer}" if a.employer else "מהמעסיק"
    month = f"{HE_MONTHS[a.month.month - 1]} {a.month.year}"
    if a.kind == "missing":
        return "הפקדה חסרה", f"{fund}: לא הגיעה הפקדה {frm} ב{month}. בדרך כלל {ils2(a.usual)}."
    if a.kind == "late":
        return (
            "הפקדה באיחור",
            (
                f"{fund}: ההפקדה של {month} {frm} הגיעה {a.days_late} ימים אחרי המועד "
                f"({ils2(a.amount)} יחד עם החודש שאחריו). "
                "על איחור מגיעה ריבית פיגורים."
            ),
        )
    if a.kind == "up":
        to = "לפנסיה" if a.product_type == "pension" else "להשתלמות"
        pct = (a.amount / a.usual - 1) * 100
        return (
            f"היי, ההפקדות {to} עלו",
            (
                f"{fund}: ב{month} הגיעו {ils2(a.amount)} {frm}, {pct:.2f}% יותר מהרגיל "
                f"({ils2(a.usual)}). אולי קיבלת העלאה או בונוס?"
            ),
        )
    return (
        "הפקדה נמוכה מהרגיל",
        f"{fund}: ב{month} הגיעו {ils2(a.amount)} {frm}, בדרך כלל {ils2(a.usual)}.",
    )
