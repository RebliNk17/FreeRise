"""Yearly history and Modified Dietz returns for pension / hishtalmut funds."""

import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.models import Fund, FundDeposit, FundSnapshot

CENT = Decimal("0.01")


@dataclass
class YearRow:
    year: int
    start_balance: Decimal
    deposits: Decimal
    profit: Decimal
    end_balance: Decimal
    return_pct: Decimal | None  # fraction, 0.1064 = 10.64 %


@dataclass
class FundOverview:
    fund: Fund
    latest_balance: Decimal
    as_of: date
    ytd_profit: Decimal | None
    ytd_return_pct: Decimal | None
    monthly: list[tuple[date, Decimal]]


@dataclass
class FundsOverview:
    funds: list[FundOverview]
    total: Decimal


def _load(session: Session, fund_id: int):
    snaps = session.execute(
        select(FundSnapshot.as_of, FundSnapshot.balance)
        .where(FundSnapshot.fund_id == fund_id)
        .order_by(FundSnapshot.as_of)
    ).all()
    deps = session.execute(
        select(FundDeposit.date, FundDeposit.amount).where(FundDeposit.fund_id == fund_id)
    ).all()
    return snaps, deps


def _year_row(snaps, deps, year: int) -> YearRow | None:
    """Modified Dietz over Jan 1 (or the year's first snapshot) .. the year's last snapshot."""
    jan1 = date(year, 1, 1)
    before = [s for s in snaps if s.as_of <= jan1]
    in_year = [s for s in snaps if s.as_of.year == year]
    start = before[-1] if before else (in_year[0] if in_year else None)
    if start is None or not in_year or in_year[-1].as_of <= start.as_of:
        return None
    end = in_year[-1]
    period_start = max(jan1, start.as_of)
    days = (end.as_of - period_start).days
    flows = [d for d in deps if d.date >= jan1 and start.as_of < d.date <= end.as_of]
    total = sum((d.amount for d in flows), Decimal(0))
    weighted = sum((d.amount * (end.as_of - d.date).days / days for d in flows), Decimal(0))
    profit = end.balance - start.balance - total
    base = start.balance + weighted
    return YearRow(
        year=year,
        start_balance=start.balance,
        deposits=total.quantize(CENT),
        profit=profit.quantize(CENT),
        end_balance=end.balance,
        return_pct=(profit / base).quantize(Decimal("0.000001")) if base > 0 else None,
    )


def fund_yearly(session: Session, fund_id: int) -> list[YearRow]:
    snaps, deps = _load(session, fund_id)
    years = sorted({s.as_of.year for s in snaps})
    return [r for y in years if (r := _year_row(snaps, deps, y))]


def funds_overview(session: Session) -> FundsOverview:
    out = []
    for fund in session.scalars(select(Fund).order_by(Fund.owner, Fund.id)):
        snaps, deps = _load(session, fund.id)
        if not snaps:
            continue
        last = snaps[-1]
        ytd = _year_row(snaps, deps, last.as_of.year)
        monthly = {(s.as_of.year, s.as_of.month): (s.as_of, s.balance) for s in snaps}
        out.append(
            FundOverview(
                fund=fund,
                latest_balance=last.balance,
                as_of=last.as_of,
                ytd_profit=ytd.profit if ytd else None,
                ytd_return_pct=ytd.return_pct if ytd else None,
                monthly=list(monthly.values()),
            )
        )
    return FundsOverview(out, sum((o.latest_balance for o in out), Decimal(0)).quantize(CENT))


@dataclass
class MonthGain:
    fund_ids: list[int]  # one fund, or a group its provider reports only as a sum (Phoenix)
    month: date  # first of the month
    start_balance: Decimal  # last balance of the month before
    end_balance: Decimal  # last balance of this month (so far, for the current one)
    deposits: Decimal
    gain: Decimal  # balance change minus deposits: after fees and insurance


def _month_end(d: date) -> date:
    return d - timedelta(days=1) if d.day == 1 else d


def _month_pairs(points: list[tuple[date, Decimal]]):
    """(month before, month) pairs of month-end points in consecutive calendar months."""
    ends = list({(d.year, d.month): (d, b) for d, b in sorted(points)}.values())  # last per month
    for a, b in pairwise(ends):
        if (b[0].year * 12 + b[0].month) - (a[0].year * 12 + a[0].month) == 1:
            yield a, b


def _gain(ids: list[int], a, b, deps) -> MonthGain:
    flows = sum((d.amount for d in deps if a[0] < d.date <= b[0]), Decimal(0))
    return MonthGain(
        ids,
        b[0].replace(day=1),
        a[1],
        b[1],
        flows.quantize(CENT),
        (b[1] - a[1] - flows).quantize(CENT),
    )


def monthly_gains(session: Session) -> list[MonthGain]:
    """Per fund and calendar month, wherever that month and the one before have a balance. A group
    with a shared portfolio_history (details) gets one row for months its funds lack their own."""
    out: list[MonthGain] = []
    deps_of: dict[int, list] = {}
    groups: dict[tuple[int, str], list[int]] = {}
    for fund in session.scalars(select(Fund).order_by(Fund.id)):
        snaps, deps_of[fund.id] = _load(session, fund.id)
        out += [
            _gain([fund.id], a, b, deps_of[fund.id])
            for a, b in _month_pairs([(x.as_of, x.balance) for x in snaps])
        ]
        if ph := (fund.details or {}).get("portfolio_history"):
            groups.setdefault((fund.credential_id, json.dumps(ph, sort_keys=True)), []).append(
                fund.id
            )
    for (_, ph), ids in groups.items():
        # Dated the 1st (Phoenix): the balance as the month opens, i.e. the previous month's end.
        points = [
            (_month_end(date.fromisoformat(p["date"][:10])), Decimal(str(p["balance"])))
            for p in json.loads(ph)
        ]
        for a, b in _month_pairs(points):
            month = b[0].replace(day=1)
            own = [
                g for g in out if g.month == month and g.fund_ids[0] in ids and len(g.fund_ids) == 1
            ]
            if len(own) == len(ids):
                continue  # every fund has its own month: keep the detail
            out = [g for g in out if g not in own]
            out.append(_gain(ids, a, b, [d for i in ids for d in deps_of[i]]))
    return out
