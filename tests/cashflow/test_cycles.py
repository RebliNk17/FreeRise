from datetime import date

from freerise.cashflow.cycles import (
    Cycle,
    cycle_by_label,
    cycle_for,
    get_start_day,
    next_cycle,
    prev_cycle,
)


def test_cycle_boundaries():
    assert cycle_for(date(2026, 10, 9), 10) == Cycle(date(2026, 9, 10), date(2026, 10, 9))
    c = cycle_for(date(2026, 10, 10), 10)
    assert c == Cycle(date(2026, 10, 10), date(2026, 11, 9))
    assert c.label_month == date(2026, 10, 1)
    assert prev_cycle(c, 10).start == date(2026, 9, 10)
    assert next_cycle(c, 10).start == date(2026, 11, 10)
    assert cycle_for(date(2027, 1, 5), 10).start == date(2026, 12, 10)
    assert next_cycle(cycle_by_label(2026, 12, 10), 10).start == date(2027, 1, 10)


def test_start_day_clamps():
    c = cycle_by_label(2027, 2, 30)
    assert c.start == date(2027, 2, 28)
    assert c.end == date(2027, 3, 29)
    assert prev_cycle(c, 30).end == date(2027, 2, 27)


def test_default_start_day(session):
    assert get_start_day(session) == 10
