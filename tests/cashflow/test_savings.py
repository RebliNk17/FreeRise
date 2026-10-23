from datetime import date
from decimal import Decimal

from sqlalchemy import select

from freerise.cashflow.cycles import cycle_by_label
from freerise.cashflow.plan import cycle_plan, set_goal
from freerise.cashflow.savings import contribute, monthly_total, plan_statuses, status
from freerise.models import (
    Account,
    Category,
    Credential,
    PlanContribution,
    SavingsPlan,
    Transaction,
)

OCT = cycle_by_label(2026, 10, 10)  # 10.10 - 9.11


def _tx(session, a, d, amount, cat):
    cid = session.scalar(select(Category.id).where(Category.name == cat))
    session.add(
        Transaction(
            account_id=a.id,
            txn_key=f"s{d}{amount}",
            date=d,
            processed_date=d,
            amount=Decimal(amount),
            description=cat,
            merchant_key=cat,
            category_id=cid,
            status="completed",
            raw={},
        )
    )


def _plan(target, d, saved=0, override=None, active=True):
    return SavingsPlan(
        name="p",
        target_amount=Decimal(target),
        target_date=d,
        saved_amount=Decimal(saved),
        monthly_override=None if override is None else Decimal(override),
        active=active,
    )


def test_monthly_needed_math():
    # Oct..May cycles = 8; ceil(6000 / 8) = 750
    s = status(_plan(6000, date(2027, 5, 20)), OCT, 10, None)
    assert (s.months_left, s.monthly_needed, s.completed) == (8, 750, False)
    assert status(_plan(1000, date(2027, 1, 15), saved=1), OCT, 10, None).monthly_needed == 250
    # override wins, capped at what's left
    assert status(_plan(6000, date(2027, 5, 20), override=900), OCT, 10, None).monthly_needed == 900
    assert status(_plan(6000, date(2027, 5, 20), 5800, 900), OCT, 10, None).monthly_needed == 200
    # last cycle / past date: whole remainder now
    assert status(_plan(500, date(2026, 11, 1), 100), OCT, 10, None).months_left == 1
    assert status(_plan(500, date(2025, 1, 1), 100), OCT, 10, None).monthly_needed == 400
    done = status(_plan(500, date(2027, 1, 1), 500), OCT, 10, None)
    assert (done.monthly_needed, done.completed) == (0, True)


def test_amount_stays_after_funding_this_cycle():
    # saved 750 includes this cycle's 750 -> still 750 for this cycle, completed at target
    s = status(_plan(6000, date(2027, 5, 20), saved=750), OCT, 10, Decimal(750))
    assert (s.monthly_needed, s.funded_this_cycle) == (750, True)
    s = status(_plan(750, date(2026, 11, 1), saved=750), OCT, 10, Decimal(750))
    assert (s.monthly_needed, s.completed) == (750, True)


def test_goal_includes_active_plans(session):
    a = Account(
        credential=Credential(provider="x", label="l", owner="o", secret_enc=b"s"),
        provider_account_id="1",
        kind="bank",
        display_name="a",
    )
    session.add(a)
    session.flush()
    _tx(session, a, date(2026, 10, 11), 20000, "משכורת")
    _tx(session, a, date(2026, 10, 12), -12000, "משכנתא")
    set_goal(session, OCT, Decimal(1000))
    before = cycle_plan(session, date(2026, 10, 23)).variable_allowance
    session.add_all([_plan(6000, date(2027, 5, 20)), _plan(9999, date(2027, 5, 20), active=False)])
    session.flush()
    p = cycle_plan(session, date(2026, 10, 23))
    assert (p.goal_personal, p.goal_plans, p.goal) == (1000, 750, 1750)
    assert p.variable_allowance == before - 750 == Decimal(6250)


def test_contribute_once_per_cycle(session):
    p = _plan(6000, date(2027, 5, 20))
    session.add(p)
    session.flush()
    contribute(session, p, OCT, 10)
    contribute(session, p, OCT, 10)
    assert p.saved_amount == 750
    assert session.query(PlanContribution).filter_by(plan_id=p.id).count() == 1
    st = plan_statuses(session, OCT, 10)
    assert st[0].funded_this_cycle and monthly_total(st) == 750
    nov = cycle_by_label(2026, 11, 10)
    contribute(session, p, nov, 10)  # 5250 left over 7 cycles
    assert p.saved_amount == 1500


def test_overdue_plan_stops_feeding_the_goal():
    # target 15.9 -> cycle 10.9-9.10, before OCT; 400 still missing
    s = status(_plan(500, date(2026, 9, 15), 100), OCT, 10, None)
    assert s.overdue and s.monthly_needed == 400 and monthly_total([s]) == 0
    on_time = status(_plan(500, date(2026, 10, 20), 100), OCT, 10, None)
    assert not on_time.overdue and monthly_total([on_time]) == 400
    assert not status(_plan(500, date(2026, 9, 15), 500), OCT, 10, None).overdue  # completed
