""" "My progress": how the last complete cycles went, and which categories moved."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from freerise.cashflow.cycles import Cycle, cycle_for, get_start_day, next_cycle
from freerise.cashflow.summary import UNCATEGORIZED, CycleSummary, cycle_summary
from freerise.insights.engine import group_total, history
from freerise.models import Account, Transaction

SPENDING = ("fixed", "variable")


@dataclass
class CategoryChange:
    category_id: int | None
    name: str
    previous: Decimal  # monthly average, previous 3 cycles
    current: Decimal  # monthly average, latest 3 cycles
    change_pct: Decimal  # (current − previous) ÷ previous


@dataclass
class Progress:
    cycles: list[tuple[Cycle, Decimal]]  # last complete cycles with data, oldest first
    avg_net: Decimal
    positive_cycles: int
    savings_total: Decimal
    savings_avg: Decimal
    increases: list[CategoryChange]  # top 2 by ₪ change
    decreases: list[CategoryChange]
    cumulative_net: Decimal  # all complete cycles since the first transaction
    since: date | None


def _avg(xs) -> Decimal:
    xs = list(xs)
    return sum(xs, Decimal(0)) / len(xs) if xs else Decimal(0)


def _cat_avgs(sums: list[CycleSummary]) -> dict[int | None, tuple[str, Decimal]]:
    tot: dict[int | None, Decimal] = defaultdict(Decimal)
    names = {}
    for s in sums:
        for g in s.groups:
            if g.group in SPENDING:
                for c in g.categories:
                    tot[c.category_id] += c.total
                    names[c.category_id] = c.name or UNCATEGORIZED
    return {k: (names[k], v / len(sums)) for k, v in tot.items()}


def _changes(hist: list[CycleSummary]) -> list[CategoryChange]:
    cur, prev = hist[:3], hist[3:6]
    if not cur or not prev:
        return []
    a, b = _cat_avgs(cur), _cat_avgs(prev)
    out = []
    for cid in a.keys() | b.keys():
        p = b.get(cid, ("", Decimal(0)))[1]
        if p <= 0:
            continue  # nothing to compare a new category to
        name, c = a.get(cid, (b[cid][0], Decimal(0)))
        out.append(CategoryChange(cid, name, p, c, (c - p) / p))
    return out


def progress(session: Session, today: date) -> Progress:
    start_day = get_start_day(session)
    cycle = cycle_for(today, start_day)
    hist = history(session, cycle)  # newest first
    nets = [s.net for s in hist]
    savings = [group_total(s, "savings") for s in hist]
    changes = _changes(hist)
    ups = sorted(
        (x for x in changes if x.current > x.previous), key=lambda x: x.previous - x.current
    )
    downs = sorted(
        (x for x in changes if x.current < x.previous), key=lambda x: x.current - x.previous
    )

    first = session.scalar(
        select(func.min(Transaction.effective_date))
        .join(Account, Account.id == Transaction.account_id)
        .where(Account.excluded.is_(False))
    )
    cumulative = Decimal(0)
    if first:
        c = cycle_for(first, start_day)
        while c.start < cycle.start:
            cumulative += cycle_summary(session, c).net
            c = next_cycle(c, start_day)
    return Progress(
        [(s.cycle, s.net) for s in reversed(hist)],
        _avg(nets),
        sum(n > 0 for n in nets),
        sum(savings, Decimal(0)),
        _avg(savings),
        ups[:2],
        downs[:2],
        cumulative,
        first,
    )
