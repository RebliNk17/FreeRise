"""New / updated connections: pending -> verified | failed, OTP handoff, schedule exclusion."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from scraper import ScrapingResult
from scraper.models.account import AccountResult
from sqlalchemy import select

from freerise.api import routes_credentials
from freerise.crypto import decrypt_json, encrypt_json
from freerise.models import Credential, SyncRun, User
from freerise.sync import demo_provider
from freerise.sync.scheduler import process_requested, run_all
from freerise.sync.service import run_credential

BODY = {
    "provider": "max",
    "label": "מקס",
    "owner": "שי",
    "fields": {"username": "u", "password": "pw-1"},
}
OK = ScrapingResult(success=True, accounts=[AccountResult(account_number="1234", transactions=[])])
WRONG = ScrapingResult(
    success=False, error_type="INVALID_PASSWORD", error_message="login invalid_password: x"
)


class Fake:
    def __init__(self, credentials, result, ask_otp):
        self.credentials, self.result, self.ask_otp = credentials, result, ask_otp
        self.on_otp_request = self.on_progress = None
        self.code = None

    async def scrape(self):
        self.on_progress("logging in")
        if self.ask_otp:
            try:
                self.code = await self.on_otp_request()
            except Exception as e:  # noqa: BLE001 - like BaseScraper
                return ScrapingResult(success=False, error_type="GENERAL", error_message=str(e))
        self.on_progress("fetching data")
        return self.result


def factory(result=OK, ask_otp=False):
    def f(provider, credentials, options):
        s = Fake(credentials, result, ask_otp)
        f.created.append((s, credentials, options))
        return s

    f.created = []
    return f


@pytest.fixture(autouse=True)
def _reset_otp_limit():
    routes_credentials._otp_tries.clear()


def status(client, cid):
    return client.get(f"/api/credentials/{cid}/verify").json()


async def test_new_connection_pending_until_verified(authed, sf):
    r = authed.post("/api/credentials", json=BODY)
    cid, rid = r.json()["id"], r.json()["verify_run_id"]
    assert rid and status(authed, cid)["stage"] == "sending"
    # hidden and never synced while pending
    assert authed.get("/api/credentials").json() == []
    assert authed.post("/api/sync", json={}).json() == {"run_ids": []}
    assert authed.post("/api/sync", json={"credential_id": cid}).status_code == 409
    sched = factory()
    await run_all(sf, scraper_factory=sched, stagger=(0, 0))
    assert sched.created == []

    f = factory()
    await process_requested(sf, scraper_factory=f)
    st = status(authed, cid)
    card = ("מקס \u2066••1234\u2069", "card")
    assert st["stage"] == "success" and [(a["label"], a["kind"]) for a in st["accounts"]] == [card]
    listed = authed.get("/api/credentials").json()
    assert [c["id"] for c in listed] == [cid]
    assert [(a["label"], a["kind"]) for a in listed[0]["accounts"]] == [card]
    # quick verify window, then the full history in a background run (also processed above)
    verify_opts, full_opts = f.created[0][2], f.created[1][2]
    assert verify_opts.start_date > full_opts.start_date
    with sf() as s:
        runs = s.scalars(select(SyncRun).order_by(SyncRun.id)).all()
        assert [(x.trigger, x.status) for x in runs] == [
            ("verify", "success"),
            ("manual", "success"),
        ]
        assert s.get(Credential, cid).verified
    assert [x["trigger"] for x in authed.get("/api/sync/runs").json()] == ["manual"]


async def test_failed_verify_stays_hidden_then_retry_and_cancel(authed, sf):
    cid = authed.post("/api/credentials", json=BODY).json()["id"]
    await process_requested(sf, scraper_factory=factory(WRONG))
    st = status(authed, cid)
    assert st["stage"] == "failed" and st["failure_kind"] == "auth_failed"
    assert "pw-1" not in str(st) and st["credential"]["label"] == "מקס"
    assert st["prefill"] == {"username": "u"}  # to fix the form; never the password
    assert authed.get("/api/credentials").json() == []
    with sf() as s:
        assert s.get(Credential, cid).enabled  # a failed verify never auto-disables
    # fix the details: the same pending credential, verified again
    r = authed.patch(f"/api/credentials/{cid}", json={"fields": {"password": "pw-2"}})
    assert r.json()["verify_run_id"] and status(authed, cid)["stage"] == "sending"
    with sf() as s:
        assert decrypt_json(s.get(Credential, cid).secret_enc)["password"] == "pw-2"
    assert authed.post(f"/api/credentials/{cid}/verify").status_code == 200
    assert authed.delete(f"/api/credentials/{cid}/verify").status_code == 204
    with sf() as s:
        assert s.get(Credential, cid) is None


async def test_otp_handoff_only_for_the_requesting_user(authed, sf):
    cid = authed.post("/api/credentials", json=BODY).json()["id"]
    with sf() as s:
        rid = s.scalar(select(SyncRun.id))
    f = factory(ask_otp=True)
    task = asyncio.create_task(
        run_credential(sf, cid, "manual", scraper_factory=f, run_id=rid, otp_poll_s=0.05)
    )
    for _ in range(100):
        await asyncio.sleep(0.05)
        if (st := status(authed, cid))["stage"] == "otp":
            break
    assert st["stage"] == "otp" and st["otp_expires_at"]
    url = f"/api/credentials/{cid}/verify/otp"
    # not on the household-wide prompt, and not answerable through it
    assert authed.get("/api/sync/otp").json() == []
    assert authed.post("/api/sync/otp/1", json={"code": "123456"}).status_code == 400
    r = authed.post(url, json={"code": "12ab56"})
    assert r.status_code == 422 and "12ab56" not in r.text
    with sf() as s:
        other = User(username="other", password_hash="x")
        s.add(other)
        s.flush()
        s.get(SyncRun, rid).user_id = other.id
        s.commit()
        owner = other.id
    assert authed.post(url, json={"code": "123456"}).status_code == 404
    with sf() as s:
        s.get(SyncRun, rid).user_id = s.scalar(select(User.id).where(User.id != owner))
        s.commit()
    assert authed.post(url, json={"code": "123456"}).status_code == 204
    run = await task
    assert run.status == "success" and f.created[0][0].code == "123456"
    assert authed.post(url, json={"code": "123456"}).status_code == 409  # answered already
    assert status(authed, cid)["stage"] == "success"


def test_otp_rate_limited(authed):
    cid = authed.post("/api/credentials", json=BODY).json()["id"]
    codes = [
        authed.post(f"/api/credentials/{cid}/verify/otp", json={"code": "123456"}).status_code
        for _ in range(6)
    ]
    assert codes == [409] * 5 + [429]


def test_stalled_verify_times_out(authed, sf):
    cid = authed.post("/api/credentials", json=BODY).json()["id"]
    with sf() as s:
        run = s.scalar(select(SyncRun))
        run.created_at = datetime.now(UTC) - timedelta(minutes=4)  # worker never picked it up
        s.commit()
    st = status(authed, cid)
    assert st["stage"] == "failed" and st["failure_kind"] == "timeout"


async def test_abandoned_new_connection_dropped(authed, sf):
    old = authed.post("/api/credentials", json=BODY).json()["id"]
    fresh = authed.post("/api/credentials", json=BODY).json()["id"]
    with sf() as s:
        run = s.scalar(select(SyncRun).where(SyncRun.credential_id == old))
        run.created_at = datetime.now(UTC) - timedelta(hours=2)
        s.commit()
    await run_all(sf, scraper_factory=factory(), stagger=(0, 0))
    with sf() as s:
        assert s.get(Credential, old) is None and s.get(Credential, fresh) is not None


def test_fetching_verify_gets_longer_before_timing_out(authed, sf):
    cid = authed.post("/api/credentials", json=BODY).json()["id"]
    with sf() as s:
        run = s.scalar(select(SyncRun))
        run.status, run.progress = "running", "fetch"
        run.progress_at = datetime.now(UTC) - timedelta(minutes=4)
        s.commit()
    assert status(authed, cid)["stage"] == "verifying"


async def test_2fa_verify_fetches_full_history_in_one_run(authed, sf):
    body = {**BODY, "provider": "hapoalim", "fields": {"userCode": "u", "password": "p"}}
    cid = authed.post("/api/credentials", json=body).json()["id"]
    f = factory()
    await process_requested(sf, scraper_factory=f)
    assert len(f.created) == 1  # no second run that would ask for another code
    assert status(authed, cid)["stage"] == "success"
    with sf() as s:
        assert s.get(Credential, cid).last_success_at is not None


async def test_update_verifies_before_replacing_old_details(authed, sf):
    with sf() as s:
        c = Credential(
            provider="max",
            label="Max",
            owner="a",
            secret_enc=encrypt_json({"username": "u", "password": "old"}),
            last_error="earlier",
        )
        s.add(c)
        s.commit()
        cid = c.id
    patch = {"fields": {"password": "new"}}
    assert authed.patch(f"/api/credentials/{cid}", json=patch).json()["verify_run_id"]
    f = factory(WRONG)
    await process_requested(sf, scraper_factory=f)
    assert f.created[0][1]["password"] == "new"
    with sf() as s:
        c = s.get(Credential, cid)
        assert decrypt_json(c.secret_enc)["password"] == "old" and c.enabled
        assert c.last_error == "earlier"  # the connection card is untouched
    assert authed.get("/api/credentials").json()[0]["last_failure_kind"] is None

    authed.post(f"/api/credentials/{cid}/verify")
    # while staged, scheduled syncs keep using the old details
    sched = factory()
    await run_all(sf, scraper_factory=sched, stagger=(0, 0))
    assert sched.created[0][1]["password"] == "old"
    await process_requested(sf, scraper_factory=factory())
    with sf() as s:
        c = s.get(Credential, cid)
        assert decrypt_json(c.secret_enc)["password"] == "new" and c.pending_secret_enc is None


async def test_canceled_update_drops_the_runs_outcome(authed, sf):
    with sf() as s:
        c = Credential(
            provider="max",
            label="Max",
            owner="a",
            secret_enc=encrypt_json({"username": "u", "password": "old"}),
        )
        s.add(c)
        s.commit()
        cid = c.id
    rid = authed.patch(f"/api/credentials/{cid}", json={"fields": {"password": "new"}}).json()[
        "verify_run_id"
    ]
    task = asyncio.create_task(
        run_credential(
            sf, cid, "manual", scraper_factory=factory(ask_otp=True), run_id=rid, otp_poll_s=0.05
        )
    )
    for _ in range(100):
        await asyncio.sleep(0.05)
        if status(authed, cid)["stage"] == "otp":
            break
    assert authed.delete(f"/api/credentials/{cid}/verify").status_code == 204
    await task
    with sf() as s:
        c = s.get(Credential, cid)
        assert decrypt_json(c.secret_enc)["password"] == "old" and c.pending_secret_enc is None
        assert s.get(SyncRun, rid).status == "failed"


def test_demo_provider_only_in_demo_mode(authed, monkeypatch):
    monkeypatch.delenv("FREERISE_ALLOW_DEMO", raising=False)
    keys = [p["key"] for p in authed.get("/api/providers").json()]
    assert "demo" not in keys
    body = {**BODY, "provider": "demo"}
    assert authed.post("/api/credentials", json=body).status_code == 422
    with pytest.raises(ValueError):
        demo_provider.make_scraper("demo", {}, None)
    monkeypatch.setenv("FREERISE_ALLOW_DEMO", "1")
    assert "demo" in [p["key"] for p in authed.get("/api/providers").json()]
    assert authed.post("/api/credentials", json=body).status_code == 201


@pytest.mark.parametrize(
    ("username", "code", "status_", "error"),
    [
        ("ok", None, "success", None),
        ("otp", "123456", "success", None),
        ("otp", "000000", "failed", "INVALID_OTP"),
        ("wrong", None, "failed", "INVALID_PASSWORD"),
        ("blocked", None, "failed", "AUTOMATION_BLOCKED"),
    ],
)
async def test_demo_scenarios(sf, monkeypatch, username, code, status_, error):
    monkeypatch.setenv("FREERISE_ALLOW_DEMO", "1")
    monkeypatch.setattr(demo_provider, "STEP_S", 0)
    with sf() as s:
        c = Credential(
            provider="demo",
            label="D",
            owner="a",
            secret_enc=encrypt_json({"username": username, "password": "x"}),
            verified=False,
        )
        s.add(c)
        s.flush()
        run = SyncRun(credential_id=c.id, trigger="verify", status="requested")
        s.add(run)
        s.commit()
        cid, rid = c.id, run.id

    async def answer():
        from freerise.models import OtpRequest
        from freerise.sync.otp import answer_otp

        while code:
            await asyncio.sleep(0.02)
            with sf() as s:
                if req := s.scalar(select(OtpRequest).where(OtpRequest.status == "waiting")):
                    return answer_otp(s, req.id, code)

    run, _ = await asyncio.gather(
        run_credential(sf, cid, "manual", run_id=rid, otp_poll_s=0.02), answer()
    )
    assert run.status == status_
    assert (run.error or "").split(":")[0] == (error or "")
