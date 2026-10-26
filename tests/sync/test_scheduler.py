import asyncio
from datetime import UTC, datetime

from fakes import fake_factory, ok
from scraper import ScrapingResult
from sqlalchemy import select

from freerise.crypto import encrypt_json
from freerise.models import Credential, SyncRun
from freerise.sync.scheduler import process_requested, run_all

NO_WAIT = {"stagger": (0, 0), "retry_gap": (0, 0)}


def add_creds(sf, *specs):
    with sf() as s:
        for provider, enabled in specs:
            s.add(
                Credential(
                    provider=provider,
                    label=provider,
                    owner="shai",
                    secret_enc=encrypt_json({"username": "u"}),
                    enabled=enabled,
                )
            )
        s.commit()


def runs(sf):
    with sf() as s:
        return list(s.scalars(select(SyncRun).order_by(SyncRun.id)))


def test_one_failure_does_not_block_others(sf):
    add_creds(sf, ("max", True), ("max", True), ("max", True))
    calls = []

    def factory(provider, credentials, options):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return fake_factory(ok())(provider, credentials, options)

    asyncio.run(run_all(sf, scraper_factory=factory, **NO_WAIT))
    # the failed one is tried again after the others
    assert [r.status for r in runs(sf)] == ["success", "failed", "success", "success"]


def test_disabled_credential_skipped(sf):
    add_creds(sf, ("max", False), ("max", True))
    f = fake_factory(ok())
    asyncio.run(run_all(sf, scraper_factory=f, **NO_WAIT))
    assert len(f.created) == 1 and len(runs(sf)) == 1


def test_insurances_skipped_on_schedule(sf):
    add_creds(sf, ("mislaka", True))
    f = fake_factory(ok())
    asyncio.run(run_all(sf, scraper_factory=f, **NO_WAIT))
    assert f.created == []
    asyncio.run(run_all(sf, "manual", scraper_factory=f, **NO_WAIT))
    assert len(f.created) == 1


def test_stagger_only_between_same_provider(sf):
    add_creds(sf, ("max", True), ("max", True), ("isracard", True))
    sleeps = []

    async def sleep(n):
        sleeps.append(n)

    asyncio.run(run_all(sf, scraper_factory=fake_factory(ok()), stagger=(5, 5), sleep=sleep))
    assert sleeps == [5]


def test_running_credential_skipped(sf, credential):
    with sf() as s:
        s.add(
            SyncRun(
                credential_id=credential.id,
                trigger="manual",
                status="running",
                started_at=datetime.now(UTC),
            )
        )
        s.commit()
    f = fake_factory(ok())
    asyncio.run(run_all(sf, scraper_factory=f, **NO_WAIT))
    assert f.created == []


def test_requested_run_processed_once(sf, credential):
    with sf() as s:
        s.add(SyncRun(credential_id=credential.id, trigger="manual", status="requested"))
        s.commit()
    f = fake_factory(ok())

    async def both():
        return await asyncio.gather(process_requested(sf, f), process_requested(sf, f))

    assert sorted(asyncio.run(both())) == [0, 1]
    assert len(f.created) == 1
    assert [r.status for r in runs(sf)] == ["success"]


def test_duplicate_request_marked_failed(sf, credential):
    with sf() as s:
        s.add(
            SyncRun(
                credential_id=credential.id,
                trigger="manual",
                status="running",
                started_at=datetime.now(UTC),
            )
        )
        s.add(SyncRun(credential_id=credential.id, trigger="manual", status="requested"))
        s.commit()
    f = fake_factory(ok())
    asyncio.run(process_requested(sf, f))
    assert f.created == []
    r = runs(sf)[1]
    assert (r.status, r.error, r.failure_kind) == ("failed", "already running", "other")


def test_unknown_provider_does_not_block_others(sf):
    add_creds(sf, ("bogus", True), ("max", True))
    f = fake_factory(ok())
    asyncio.run(run_all(sf, scraper_factory=f, **NO_WAIT))
    assert len(f.created) == 1


def test_skipped_credential_costs_no_stagger(sf, credential):
    add_creds(sf, ("max", True))
    with sf() as s:
        s.add(
            SyncRun(
                credential_id=2, trigger="manual", status="running", started_at=datetime.now(UTC)
            )
        )
        s.commit()
    sleeps = []

    async def sleep(n):
        sleeps.append(n)

    asyncio.run(run_all(sf, scraper_factory=fake_factory(ok()), stagger=(5, 5), sleep=sleep))
    assert sleeps == []


def test_crashed_requested_run_marked_failed(sf, credential):
    with sf() as s:
        s.add(SyncRun(credential_id=credential.id, trigger="manual", status="requested"))
        s.commit()
    import freerise.sync.scheduler as sch

    async def boom(*a, **k):
        raise RuntimeError("x")

    orig, sch.run_credential = sch.run_credential, boom
    try:
        asyncio.run(process_requested(sf))
    finally:
        sch.run_credential = orig
    r = runs(sf)[0]
    assert (r.status, r.error, r.failure_kind) == ("failed", "RuntimeError", "other")


def test_after_sync_categorizes_pending(sf):
    from datetime import date

    from sqlalchemy import select

    from freerise.models import Account, Category, MerchantRule, Transaction
    from freerise.sync.scheduler import after_sync

    add_creds(sf, ("max", True))
    with sf() as s:
        cred = s.scalar(select(Credential))
        a = Account(credential_id=cred.id, provider_account_id="1", kind="card", display_name="c")
        s.add(a)
        s.flush()
        cid = s.scalar(select(Category.id).where(Category.name == "כלכלה"))
        s.add(MerchantRule(pattern="שופרסל", match="exact", category_id=cid, source="seed"))
        s.add(
            Transaction(
                account_id=a.id,
                txn_key="k",
                date=date(2026, 10, 1),
                processed_date=date(2026, 10, 1),
                raw={},
                amount=-5,
                description="שופרסל",
                status="completed",
                merchant_key="שופרסל",
            )
        )
        s.commit()
    asyncio.run(after_sync(sf))
    with sf() as s:
        assert s.scalar(select(Transaction.category_id)) == cid


def test_after_sync_detects_recurring(sf):
    from datetime import date, timedelta

    from sqlalchemy import select

    from freerise.models import Account, RecurringItem, Transaction
    from freerise.sync.scheduler import after_sync

    add_creds(sf, ("max", True))
    today = date.today()
    with sf() as s:
        cred = s.scalar(select(Credential))
        a = Account(credential_id=cred.id, provider_account_id="1", kind="card", display_name="c")
        s.add(a)
        s.flush()
        for i in range(6):
            d = today - timedelta(days=5 + 30 * i)
            s.add(
                Transaction(
                    account_id=a.id,
                    txn_key=f"r{i}",
                    date=d,
                    processed_date=d,
                    raw={},
                    amount=-49,
                    description="spotify",
                    status="completed",
                    merchant_key="spotify",
                )
            )
        s.commit()
    asyncio.run(after_sync(sf))
    with sf() as s:
        assert s.scalar(select(RecurringItem.merchant_key)) == "spotify"


def test_mislaka_not_scheduled(sf):
    from scraper.models.account import AccountResult

    from freerise.models import Account, Fund

    add_creds(sf, ("mislaka", True))
    fund = AccountResult(
        account_number="P1",
        balance=100.0,
        balance_date="2026-09-30",
        metadata={"policy_type": "pension", "account_name": "פנסיה"},
    )
    f = fake_factory(ok(fund))
    asyncio.run(run_all(sf, scraper_factory=f, **NO_WAIT))
    assert f.created == [] and runs(sf) == []
    asyncio.run(run_all(sf, "manual", scraper_factory=f, **NO_WAIT))
    assert [r.status for r in runs(sf)] == ["success"]
    with sf() as s:
        assert s.scalars(select(Fund.policy_id)).all() == ["P1"]
        assert s.scalars(select(Account)).all() == []


def test_after_sync_generates_notifications(sf):
    from sqlalchemy import select

    from freerise.models import Notification
    from freerise.sync.scheduler import after_sync

    add_creds(sf, ("max", True))
    with sf() as s:
        cred = s.scalar(select(Credential))
        s.add(
            SyncRun(
                credential_id=cred.id,
                trigger="manual",
                status="failed",
                failure_kind="auth_failed",  # never retried, so it alerts at once
                finished_at=datetime.now(UTC),
                error="x",
            )
        )
        s.commit()
    asyncio.run(after_sync(sf))
    with sf() as s:
        assert s.scalar(select(Notification.kind)) == "sync_failed"


def test_recheck_running_after_stagger_sleep(sf):
    add_creds(sf, ("max", True), ("max", True))
    with sf() as s:
        second = s.scalars(select(Credential.id).order_by(Credential.id)).all()[1]

    async def sleep(n):  # a manual run of the second credential starts during the stagger
        with sf() as s:
            s.add(
                SyncRun(
                    credential_id=second,
                    trigger="manual",
                    status="running",
                    started_at=datetime.now(UTC),
                )
            )
            s.commit()

    f = fake_factory(ok())
    asyncio.run(run_all(sf, scraper_factory=f, stagger=(1, 1), sleep=sleep))
    assert len(f.created) == 1


def test_pension_with_token_syncs_once_a_day(sf):
    with sf() as s:
        for provider, secret in (
            ("migdal", {"id": "1", "otpLongTermToken": "t"}),
            ("hafenix", {"id": "1"}),  # no token: login would send an SMS
            ("mislaka", {"id": "1", "otpLongTermToken": "t"}),  # SMS every time: manual
        ):
            s.add(
                Credential(
                    provider=provider, label=provider, owner="shai", secret_enc=encrypt_json(secret)
                )
            )
        s.commit()
    f = fake_factory(ok())
    asyncio.run(run_all(sf, scraper_factory=f, **NO_WAIT))
    assert len(f.created) == 1
    asyncio.run(run_all(sf, scraper_factory=f, **NO_WAIT))
    assert len(f.created) == 1  # already synced today


class FailsFetching:
    """Logged in, then the site broke: retried on schedule, never paused (not a login problem)."""

    on_progress = on_otp_request = None

    async def scrape(self):
        self.on_progress("fetching data")
        return ScrapingResult(success=False, error_type="GENERIC", error_message="site down")


def test_failed_sync_retried_then_alerts_once(sf):
    from freerise.models import Notification
    from freerise.sync.service import SYNC_TRIES

    add_creds(sf, ("max", True))
    gaps = []

    async def sleep(n):
        gaps.append(n)

    asyncio.run(
        run_all(
            sf,
            scraper_factory=lambda *a: FailsFetching(),
            stagger=(0, 0),
            retry_gap=(300, 900),
            sleep=sleep,
        )
    )
    assert [r.status for r in runs(sf)] == ["failed"] * SYNC_TRIES
    assert len(gaps) == SYNC_TRIES - 1 and all(300 <= g <= 900 for g in gaps)
    with sf() as s:  # one alert, after the last try, opening that connection's edit sheet
        (n,) = s.scalars(select(Notification)).all()
        assert n.kind == "sync_failed" and n.link == f"/accounts?edit={runs(sf)[0].credential_id}"


def test_no_alert_before_the_last_try_and_no_retry_once_it_works(sf):
    from freerise.models import Notification

    add_creds(sf, ("max", True))
    results = [ScrapingResult(success=False, error_type="GENERIC", error_message="slow"), ok()]
    alerts = []

    def factory(provider, credentials, options):
        with sf() as s:
            alerts.append(s.scalar(select(Notification.kind)))
        return fake_factory(results.pop(0))(provider, credentials, options)

    asyncio.run(run_all(sf, scraper_factory=factory, **NO_WAIT))
    assert [r.status for r in runs(sf)] == ["failed", "success"]  # no third try
    assert alerts == [None, None]  # the first failure alerted nobody
