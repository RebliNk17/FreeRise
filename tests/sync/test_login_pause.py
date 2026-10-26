"""Repeated login-stage failures pause scheduled syncs (service.login_paused) until a success."""

import asyncio
from datetime import UTC, date, datetime

from fakes import fake_factory, ok
from scraper import ScrapingResult
from sqlalchemy import select

from freerise.api.routes_credentials import _out
from freerise.models import Credential, Notification, SyncRun
from freerise.notify.rules import generate_notifications
from freerise.sync.scheduler import run_all
from freerise.sync.service import PAUSE_AFTER, login_paused, run_credential

NO_WAIT = {"stagger": (0, 0), "retry_gap": (0, 0)}
# What Max's lock screen looks like through the package: no auth error type, just a timeout.
LOCKED = ScrapingResult(success=False, error_type="TIMEOUT", error_message="30000 ms exceeded")


class Scraper:
    """Fails after reaching `stage` ("logging in" or "fetching data"), or succeeds."""

    def __init__(self, stage=None, result=LOCKED):
        self.stage, self.result = stage, result
        self.on_progress = self.on_otp_request = None

    async def scrape(self):
        if self.stage:
            self.on_progress(self.stage)
        return self.result


def factory(**kw):
    return lambda provider, creds, options: Scraper(**kw)


def paused(sf, cred_id):
    with sf() as s:
        return login_paused(s, cred_id)


def scheduled(sf, **kw):
    return asyncio.run(run_all(sf, scraper_factory=factory(**kw), **NO_WAIT))


def once(sf, cred_id, **kw):
    """One scheduled attempt, without run_all's retries."""
    return asyncio.run(run_credential(sf, cred_id, "schedule", factory(**kw)))


def test_login_failures_pause_schedule_until_manual_success(sf, credential):
    assert PAUSE_AFTER == 2
    once(sf, credential.id, stage="logging in")
    assert not paused(sf, credential.id)  # one failure may be a slow site
    once(sf, credential.id, stage="logging in")
    assert paused(sf, credential.id)
    with sf() as s:
        c = s.get(Credential, credential.id)
        assert c.enabled  # not disabled: a manual retry is still allowed
        assert _out(c).sync_paused

    assert scheduled(sf) == []  # skipped: no third login attempt
    with sf() as s:
        assert s.scalar(select(SyncRun.id).order_by(SyncRun.id.desc())) == 2

    # A manual retry that still cannot log in keeps it paused.
    asyncio.run(run_credential(sf, credential.id, "manual", factory(stage="logging in")))
    assert paused(sf, credential.id)
    # One that works resumes scheduling.
    asyncio.run(run_credential(sf, credential.id, "manual", fake_factory(ok())))
    assert not paused(sf, credential.id)
    assert len(scheduled(sf, result=ok())) == 1


def test_fetch_stage_failures_do_not_pause(sf, credential):
    for _ in range(3):
        scheduled(sf, stage="fetching data")  # logged in fine: not a credentials problem
    assert not paused(sf, credential.id)


def test_failure_before_any_progress_counts(sf, credential):
    # e.g. the login page never loaded (timeout / general error before LOGGING_IN)
    scheduled(sf)
    scheduled(sf, result=ScrapingResult(success=False, error_type="GENERAL_ERROR"))
    assert paused(sf, credential.id)


def test_successful_verify_clears(sf, credential):
    scheduled(sf, stage="logging in")
    scheduled(sf, stage="logging in")
    asyncio.run(run_credential(sf, credential.id, "verify", fake_factory(ok())))
    assert not paused(sf, credential.id)


def test_scheduled_retries_stop_at_the_pause(sf, credential):
    scheduled(sf, stage="logging in")  # tried, retried once, then paused: no third login
    assert paused(sf, credential.id)
    with sf() as s:
        assert len(s.scalars(select(SyncRun.id)).all()) == PAUSE_AFTER


def test_failed_verify_and_otp_timeout_are_not_counted(sf, credential):
    once(sf, credential.id, stage="logging in")
    asyncio.run(run_credential(sf, credential.id, "verify", factory(stage="logging in")))
    assert not paused(sf, credential.id)  # verify tried new details, not this connection's own
    now = datetime.now(UTC)
    with sf() as s:
        s.add(
            SyncRun(
                credential_id=credential.id,
                trigger="schedule",
                status="otp_timeout",
                started_at=now,
                finished_at=now,
            )
        )
        s.commit()
    once(sf, credential.id, stage="logging in")
    assert not paused(sf, credential.id)  # the code was not typed in; the login itself may work


def test_paused_notification_in_hebrew_once_per_streak(sf, credential):
    scheduled(sf, stage="logging in")
    scheduled(sf, stage="logging in")
    with sf.begin() as s:
        generate_notifications(s, date.today())
        generate_notifications(s, date.today())  # the daily run must not repeat it
    with sf() as s:
        (n,) = s.scalars(select(Notification).where(Notification.kind == "sync_paused"))
    assert n.severity == "critical" and n.link == f"/accounts?edit={credential.id}"
    assert n.title == "הסנכרון האוטומטי הושהה: מקס · Max"
    assert "היכנסו לאתר הספק" in n.body and "״סנכרון״" in n.body
