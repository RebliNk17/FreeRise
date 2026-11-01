from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from freerise.models import RecurringItem, RecurringSkip


def test_skip_and_unskip_recurring(authed, sf):
    with sf() as s:
        r = RecurringItem(
            merchant_key="gym",
            direction="expense",
            label="gym",
            cadence="monthly",
            amount_kind="fixed",
            expected_amount=Decimal(250),
            last_date=date(2026, 9, 18),
            next_expected_date=date(2026, 10, 18),
            status="confirmed",
            basis="b",
        )
        s.add(r)
        s.commit()
        rid = r.id
    body = {"cycle_start": "2026-10-10"}
    assert authed.post(f"/api/recurring/{rid}/skip", json=body).status_code == 204
    assert authed.post(f"/api/recurring/{rid}/skip", json=body).status_code == 204  # idempotent
    with sf() as s:
        assert s.scalar(select(func.count()).select_from(RecurringSkip)) == 1
    r = authed.delete(f"/api/recurring/{rid}/skip", params={"cycle_start": "2026-10-10"})
    assert r.status_code == 204
    with sf() as s:
        assert s.scalar(select(func.count()).select_from(RecurringSkip)) == 0
    assert authed.post("/api/recurring/99999/skip", json={}).status_code == 404


def test_expected_amount_this_cycle_or_from_now_on(authed, sf):
    with sf() as s:
        r = RecurringItem(
            merchant_key="insurance",
            direction="expense",
            label="insurance",
            cadence="monthly",
            amount_kind="variable",
            expected_amount=Decimal(968),
            last_date=date(2026, 9, 28),
            next_expected_date=date(2026, 11, 27),
            status="pending",
            basis="b",
        )
        s.add(r)
        s.commit()
        rid = r.id
    oct_ = {"cycle_start": "2026-10-10"}
    body = {"amount": 900, "scope": "cycle", **oct_}
    assert authed.put(f"/api/recurring/{rid}/expected", json=body).status_code == 204
    with sf() as s:  # this cycle only: the item itself is untouched
        assert s.scalar(select(RecurringSkip.amount)) == 900
        assert s.get(RecurringItem, rid).expected_amount == 968
    # "won't happen this month" replaces the amount; still one row
    assert authed.post(f"/api/recurring/{rid}/skip", json=oct_).status_code == 204
    with sf() as s:
        assert s.scalars(select(RecurringSkip.amount)).all() == [None]

    body = {"amount": 1000, "scope": "forward"}
    assert authed.put(f"/api/recurring/{rid}/expected", json=body).status_code == 204
    with sf() as s:
        it = s.get(RecurringItem, rid)
        got = (it.expected_amount, it.amount_kind, it.user_defined, it.status)
        assert got == (1000, "fixed", True, "confirmed")
    bad = {"amount": 0, "scope": "cycle"}
    assert authed.put(f"/api/recurring/{rid}/expected", json=bad).status_code == 422
