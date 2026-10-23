"""Per-cycle totals of one group (or one category) over past cycles: home "חודשים קודמים"
sheets and the /progress history charts."""

from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.cashflow.cycles import Cycle, get_start_day, prev_cycle
from freerise.cashflow.plan import CENT
from freerise.cashflow.summary import CycleSummary, cycle_summary
from freerise.models import CategoryBudget

EXPECTED_BASIS = (
    "צפוי = חציון 6 המחזורים שלפני אותו חודש (מחזורים בלי נתונים לא נספרים); "
    "לקטגוריה עם סכום שקבעתם לאותו חודש, הסכום שקבעתם."
)


@dataclass
class Point:
    cycle: Cycle
    value: Decimal  # positive: spent / received
    has_data: bool  # the cycle has any income or spending at all


@dataclass
class HistoryRow:
    label_year: int
    label_month: int
    spent: Decimal
    expected: Decimal


def cycles_before(session: Session, cycle: Cycle, n: int) -> list[Cycle]:
    """The n cycles before `cycle`, oldest first."""
    start_day = get_start_day(session)
    out, c = [], cycle
    for _ in range(n):
        c = prev_cycle(c, start_day)
        out.append(c)
    return out[::-1]


def value_of(s: CycleSummary, group: str, category_id: int | None = None) -> Decimal:
    g = next(x for x in s.groups if x.group == group)
    if category_id is None:
        return g.total
    return sum((c.total for c in g.categories if c.category_id == category_id), Decimal(0))


def points(
    session: Session, cycles: list[Cycle], group: str, category_id: int | None = None
) -> list[Point]:
    out = []
    for c in cycles:
        s = cycle_summary(session, c)
        out.append(Point(c, value_of(s, group, category_id), bool(s.income or s.spending)))
    return out


def spent_vs_expected(
    session: Session, cycle: Cycle, group: str, category_id: int | None = None, n: int = 6
) -> list[HistoryRow]:
    """The n cycles before `cycle`: spent, and what was expected then (median of the 6 before
    each, or the user's own amount for a tracked category)."""
    pts = points(session, cycles_before(session, cycle, n + 6), group, category_id)
    budgets = {}
    if category_id is not None:
        budgets = dict(
            session.execute(
                select(CategoryBudget.cycle_start, CategoryBudget.amount).where(
                    CategoryBudget.category_id == category_id
                )
            ).all()
        )
    rows = []
    for i in range(6, len(pts)):
        p = pts[i]
        prior = [x.value for x in pts[i - 6 : i] if x.has_data]
        exp = budgets.get(p.cycle.start)
        if exp is None:
            exp = Decimal(median(prior)).quantize(CENT) if prior else Decimal(0)
        m = p.cycle.label_month
        rows.append(HistoryRow(m.year, m.month, p.value, exp))
    return rows
