"""Yearly history and Modified Dietz returns for pension / hishtalmut funds."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

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
