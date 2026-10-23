import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from scraper import PROVIDER_CONFIGS
from sqlalchemy import delete, exists, select, text
from sqlalchemy.orm import sessionmaker

from freerise.categorize.pipeline import categorize_pending
from freerise.config import get_settings
from freerise.db import SessionLocal
from freerise.forecast.attribution import attribute_income
from freerise.forecast.recurring import detect_recurring
from freerise.models import Credential, Setting, SyncRun
from freerise.notify.rules import generate_notifications
from freerise.notify.senders import build_senders, deliver_pending
from freerise.sync import demo_provider
from freerise.sync.demo_provider import make_scraper
from freerise.sync.service import login_paused, run_credential

log = logging.getLogger("freerise.worker")
STALE = timedelta(minutes=30)
# A new connection nobody verified (check failed, tab closed) is dropped, secrets and all.
ABANDONED = timedelta(hours=1)

CLAIM = text(
    """UPDATE sync_runs SET status = 'running'
       WHERE id = (SELECT id FROM sync_runs WHERE status = 'requested'
                   ORDER BY trigger = 'verify' DESC, id  -- someone is waiting on those
                   FOR UPDATE SKIP LOCKED LIMIT 1)
       RETURNING id, credential_id"""
)


def _is_running(s, credential_id: int, exclude_id: int | None = None) -> bool:
    q = select(SyncRun.id).where(
        SyncRun.credential_id == credential_id,
        SyncRun.status == "running",
        SyncRun.started_at > datetime.now(UTC) - STALE,
    )
    if exclude_id:
        q = q.where(SyncRun.id != exclude_id)
    return s.scalar(q.limit(1)) is not None


async def run_all(
    session_factory: sessionmaker,
    trigger: str = "schedule",
    scraper_factory=make_scraper,
    *,
    stagger: tuple[float, float] = (30, 120),
    sleep=asyncio.sleep,
) -> list[SyncRun]:
    with session_factory.begin() as s:
        recent = SyncRun.created_at > datetime.now(UTC) - ABANDONED
        s.execute(
            delete(Credential).where(
                ~Credential.verified,
                ~exists().where(SyncRun.credential_id == Credential.id, recent),
            )
        )
    with session_factory() as s:
        creds = list(
            s.scalars(
                select(Credential)
                .where(Credential.enabled, Credential.verified)
                .order_by(Credential.provider, Credential.id)
            )
        )
    known = []
    for c in creds:
        cfg = PROVIDER_CONFIGS.get(c.provider)
        if cfg is None or (c.provider == demo_provider.KEY and not demo_provider.demo_enabled()):
            log.warning("skip credential %s: unknown provider %s", c.id, c.provider)
        elif not (trigger == "schedule" and cfg.service == "insurances"):  # Mislaka is manual-only
            known.append(c)
    creds = known

    results: list[SyncRun] = []
    prev = None
    for c in creds:
        with session_factory() as s:
            running = _is_running(s, c.id)
        if not running and prev == c.provider:
            await sleep(random.uniform(*stagger))
            with session_factory() as s:  # a manual run may have started while we slept
                running = _is_running(s, c.id)
        if running:
            log.info("skip credential %s: already running", c.id)
            continue
        if trigger == "schedule":
            with session_factory() as s:
                paused = login_paused(s, c.id)
            if paused:  # retrying could lock the account; the owner was notified (rules.py)
                log.warning("skip credential %s: login failed repeatedly, paused", c.id)
                continue
        prev = c.provider
        try:
            run = await run_credential(session_factory, c.id, trigger, scraper_factory)
        except Exception as e:  # noqa: BLE001 - one credential must not stop the rest
            log.error("credential %s crashed: %s", c.id, type(e).__name__)
            continue
        if run.status != "success":
            log.warning("credential %s sync %s", c.id, run.status)
        results.append(run)
    await after_sync(session_factory)
    return results


async def process_requested(session_factory: sessionmaker, scraper_factory=make_scraper) -> int:
    done = 0
    while True:
        with session_factory.begin() as s:
            row = s.execute(CLAIM).first()
        if row is None:
            break
        run_id, cred_id = row
        with session_factory.begin() as s:
            dup = _is_running(s, cred_id, exclude_id=run_id)
            if dup:
                r = s.get(SyncRun, run_id)
                r.status, r.error, r.finished_at = "failed", "already running", datetime.now(UTC)
                r.failure_kind = "other"
        if dup:
            continue
        try:
            await run_credential(session_factory, cred_id, "manual", scraper_factory, run_id=run_id)
        except Exception as e:  # noqa: BLE001
            log.error("requested run %s crashed: %s", run_id, type(e).__name__)
            with session_factory.begin() as s:
                if r := s.get(SyncRun, run_id):  # gone if its credential was deleted
                    r.status, r.error, r.failure_kind = "failed", type(e).__name__, "other"
                    r.finished_at = datetime.now(UTC)
        done += 1
    if done:
        await after_sync(session_factory)
    return done


async def after_sync(session_factory: sessionmaker) -> None:
    with session_factory.begin() as s:
        categorize_pending(s)
        today = datetime.now(ZoneInfo(get_settings().tz)).date()
        detect_recurring(s, today)
        attribute_income(s)
    try:  # a notification failure must not roll back categorization/detection
        with session_factory.begin() as s:
            generate_notifications(s, today)
            deliver_pending(s, build_senders(s))
    except Exception as e:  # noqa: BLE001
        log.error("notifications failed: %s", type(e).__name__)


async def daily_notifications(session_factory: sessionmaker) -> None:
    with session_factory.begin() as s:
        generate_notifications(s, datetime.now(ZoneInfo(get_settings().tz)).date())
        deliver_pending(s, build_senders(s))


def _hour_setting(session_factory: sessionmaker, key: str, default):
    with session_factory() as s:
        v = s.scalar(select(Setting.value).where(Setting.key == key))
    return default if v is None else v


async def scheduled_sync(session_factory: sessionmaker, now: datetime | None = None) -> None:
    now = now or datetime.now(ZoneInfo(get_settings().tz))
    if now.hour in _hour_setting(session_factory, "sync_hours", [7, 14, 21]):
        await run_all(session_factory)


async def scheduled_digest(session_factory: sessionmaker, now: datetime | None = None) -> None:
    now = now or datetime.now(ZoneInfo(get_settings().tz))
    if now.hour == _hour_setting(session_factory, "digest_hour", 9):
        await daily_notifications(session_factory)


async def main() -> None:
    load_dotenv()  # FREERISE_SCRAPER_PROXY from .env must reach os.environ (vendored code reads it)
    logging.basicConfig(level=logging.INFO)
    for name in ("httpx", "httpcore"):  # INFO logs full request URLs
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)  # a line per 5s poll otherwise
    try:  # attribution rule may have changed since the last sync
        with SessionLocal.begin() as s:
            attribute_income(s)
    except Exception as e:  # noqa: BLE001 - e.g. fresh install before migrations
        log.error("income attribution failed: %s", type(e).__name__)
    sched = AsyncIOScheduler(timezone="Asia/Jerusalem")
    for job in (scheduled_sync, scheduled_digest):  # hours come from settings, checked hourly
        sched.add_job(job, "cron", minute=0, args=[SessionLocal], max_instances=1, coalesce=True)
    sched.add_job(
        process_requested,
        "interval",
        seconds=5,
        args=[SessionLocal],
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    await asyncio.Event().wait()
