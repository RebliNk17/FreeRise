import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.models import Setting


@dataclass(frozen=True)
class Cycle:
    start: date
    end: date  # inclusive

    @property
    def label_month(self) -> date:
        return self.start.replace(day=1)


def _start_of(year: int, month: int, start_day: int) -> date:
    return date(year, month, min(start_day, calendar.monthrange(year, month)[1]))


def cycle_by_label(year: int, month: int, start_day: int) -> Cycle:
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    return Cycle(
        _start_of(year, month, start_day),
        _start_of(ny, nm, start_day) - timedelta(days=1),
    )


def day_in_cycle(day: int, c: Cycle) -> date:
    """The date with this day of month inside the cycle (clamped to short months)."""
    for m in (c.start, c.end):
        d = m.replace(day=min(day, calendar.monthrange(m.year, m.month)[1]))
        if c.start <= d <= c.end:
            return d
    return c.start


def cycle_for(d: date, start_day: int) -> Cycle:
    c = cycle_by_label(d.year, d.month, start_day)
    if d >= c.start:
        return c
    return prev_cycle(c, start_day)


def prev_cycle(c: Cycle, start_day: int) -> Cycle:
    m = c.label_month
    py, pm = (m.year - 1, 12) if m.month == 1 else (m.year, m.month - 1)
    return cycle_by_label(py, pm, start_day)


def next_cycle(c: Cycle, start_day: int) -> Cycle:
    m = c.label_month
    ny, nm = (m.year + 1, 1) if m.month == 12 else (m.year, m.month + 1)
    return cycle_by_label(ny, nm, start_day)


HE_MONTHS = (
    "ינואר",
    "פברואר",
    "מרץ",
    "אפריל",
    "מאי",
    "יוני",
    "יולי",
    "אוגוסט",
    "ספטמבר",
    "אוקטובר",
    "נובמבר",
    "דצמבר",
)


def cycle_shift(d: date, cycle_date: date | None, start_day: int) -> tuple[str | None, str | None]:
    """("previous"|"next", "ספטמבר 2026") when a txn is attributed to a neighbour cycle."""
    if cycle_date is None:
        return None, None
    real, eff = cycle_for(d, start_day), cycle_for(cycle_date, start_day)
    if eff.start == real.start:
        return None, None
    m = eff.label_month
    return ("previous" if eff.start < real.start else "next"), f"{HE_MONTHS[m.month - 1]} {m.year}"


def get_start_day(session: Session) -> int:
    v = session.scalar(select(Setting.value).where(Setting.key == "cycle_start_day"))
    return int(v) if v is not None else 10
