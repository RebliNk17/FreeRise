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
