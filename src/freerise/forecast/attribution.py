"""Which cycle a late/early fixed income belongs to (transactions.cycle_date).

A fixed income (confirmed monthly income item, or the detected salary stream) has a usual
day of month (the user's expected_day, else the median day of its occurrences). Each
occurrence belongs to whichever cycle - its own, the previous or the next - has that usual
day nearest to it. It is moved there only when that cycle is a neighbour, the distance is
within GRACE days and the neighbour has no occurrence of its own; otherwise it stays.
Late moves are settled oldest first, early ones newest first, so a run of late (or early)
payments fills each cycle once instead of piling up. Recomputed from scratch on every run;
manual attributions are never touched and count where they sit.
"""

from collections import Counter
from datetime import date

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from freerise.cashflow.cycles import (
    Cycle,
    cycle_for,
    day_in_cycle,
    get_start_day,
    next_cycle,
    prev_cycle,
)
from freerise.forecast.recurring import usual_day
from freerise.models import Account, Category, RecurringItem, Setting, Transaction

GRACE_DEFAULT = 10
SALARY = "משכורת"


def grace_days(session: Session) -> int:
    v = session.scalar(select(Setting.value).where(Setting.key == "income_grace_days"))
    return int(v) if v is not None else GRACE_DEFAULT


def _streams(session: Session) -> dict[str, int | None]:
    """merchant_key -> the user's expected_day (None: use the median day)."""
    salary = select(Category.id).where(Category.name == SALARY).scalar_subquery()
    return dict(
        session.execute(
            select(RecurringItem.merchant_key, RecurringItem.expected_day).where(
                RecurringItem.direction == "income",
                RecurringItem.cadence == "monthly",
                or_(
                    RecurringItem.status == "confirmed",
                    (RecurringItem.status == "pending") & (RecurringItem.category_id == salary),
                ),
            )
        ).all()
    )


def _attribute(
    txns: list[Transaction], day: int, start_day: int, grace: int
) -> dict[int, date | None]:
    """New automatic cycle_date per non-manual txn id."""
    eff = {t.id: t.cycle_date if t.cycle_date_source == "manual" else t.date for t in txns}
    count = Counter(cycle_for(d, start_day).start for d in eff.values())
    out: dict[int, date | None] = {}
    moves: dict[str, list[tuple[Transaction, Cycle, Cycle]]] = {"prev": [], "next": []}
    for t in txns:
        if t.cycle_date_source == "manual":
            continue
        out[t.id] = None
        own = cycle_for(t.date, start_day)
        near = {
            "own": own,
            "prev": prev_cycle(own, start_day),
            "next": next_cycle(own, start_day),
        }
        dist = {k: abs((day_in_cycle(day, c) - t.date).days) for k, c in near.items()}
        best = min(dist, key=lambda k: (dist[k], k != "own"))  # ties stay home
        if best != "own" and dist[best] <= grace:
            moves[best].append((t, own, near[best]))
    for t, own, to in [*moves["prev"], *reversed(moves["next"])]:
        if count[to.start]:
            continue  # the neighbour has its own occurrence
        count[own.start] -= 1
        count[to.start] += 1
        out[t.id] = to.end if to.start < own.start else to.start
    return out


def attribute_income(session: Session) -> int:
    """Recompute automatic attributions (flush only; caller commits). Returns rows changed."""
    start_day, grace = get_start_day(session), grace_days(session)
    streams = _streams(session)
    keys = set(streams)
    stale = update(Transaction).where(Transaction.cycle_date_source == "auto")
    if keys:
        stale = stale.where(Transaction.merchant_key.not_in(keys))
    changed = session.execute(
        stale.values(cycle_date=None, cycle_date_source=None),
        execution_options={"synchronize_session": "fetch"},
    ).rowcount
    for key in keys:
        txns = list(
            session.scalars(
                select(Transaction)
                .join(Account, Account.id == Transaction.account_id)
                .where(
                    Account.excluded.is_(False),
                    Transaction.merchant_key == key,
                    Transaction.amount > 0,
                )
                .order_by(Transaction.date, Transaction.id)
            )
        )
        if not txns:
            continue
        by_id = {t.id: t for t in txns}
        day = usual_day(streams[key], [t.date.day for t in txns])
        for tid, new in _attribute(txns, day, start_day, grace).items():
            t = by_id[tid]
            if t.cycle_date != new:
                t.cycle_date, t.cycle_date_source = new, "auto" if new else None
                changed += 1
    session.flush()
    return changed
