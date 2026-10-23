"""The israeli-bank-scrapers adapter, against a fake bridge (tests/sync/fake_bridge.py)."""

import asyncio
import json
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest
from scraper import PROVIDER_CONFIGS, ScraperOptions
from sqlalchemy import select

from freerise.crypto import decrypt_json, encrypt_json
from freerise.models import Account, Credential, OtpRequest, SyncRun, Transaction
from freerise.sync import ibs
from freerise.sync.dedup import txn_key
from freerise.sync.demo_provider import make_scraper
from freerise.sync.otp import OtpTimeout, answer_otp
from freerise.sync.service import failure_kind, run_credential

FAKE = [sys.executable, str(Path(__file__).with_name("fake_bridge.py"))]


def fake(username, password="s3cret-pw", **kw):
    creds = {"username": username, "password": password, "id": "000000018"}
    return ibs.IbsScraper("max", creds, ScraperOptions(start_date=date(2026, 9, 1)), cmd=FAKE, **kw)


async def test_success_maps_onto_vendored_models():
    s = fake("ok")
    stages = []
    s.on_progress = stages.append
    r = await s.scrape()
    assert r.success, r.error_message
    assert stages == ["initializing", "logging in", "fetching data"]
    (a,) = r.accounts
    assert (a.account_number, a.balance, a.card_frame) == ("1234", -100.5, 5000)
    (t,) = a.transactions
    # UTC instants become Israel-local dates, like the vendored engine's.
    assert (t.date, t.processed_date) == ("2026-10-01", "2026-11-02")
    assert (t.identifier, t.memo, t.charged_amount) == ("arn1", None, -42.5)


async def test_otp_flow():
    s = fake("otp")

    async def code():
        return "123456"

    s.on_otp_request = code
    assert (await s.scrape()).success
    assert s.refreshed_otp_long_term_token == "fresh-token"  # service.py stores it in creds


async def test_otp_timeout_propagates_and_kills_bridge():
    s = fake("otp")

    async def never():
        raise OtpTimeout("late")

    s.on_otp_request = never
    with pytest.raises(OtpTimeout):
        await s.scrape()


async def test_wrong_password_is_auth_failure():
    r = await fake("wrong").scrape()
    assert (r.success, r.error_type) == (False, "INVALID_PASSWORD")
    assert failure_kind(r.error_type, r.error_message) == "auth_failed"


async def test_crash_reports_stderr_tail():
    r = await fake("crash").scrape()
    assert not r.success and r.error_type == "GENERAL_ERROR"
    assert "exited (3)" in r.error_message and "chrome not found" in r.error_message


async def test_garbage_output_fails_fast():
    t0 = time.monotonic()
    r = await fake("garbage").scrape()
    assert not r.success and "unreadable output" in r.error_message
    assert time.monotonic() - t0 < 15  # the child was terminated, not waited out


async def test_timeout_kills_bridge():
    r = await fake("hang", timeout_s=1).scrape()
    assert (r.success, r.error_type) == (False, "TIMEOUT")
    assert failure_kind(r.error_type, r.error_message) == "timeout"


async def test_credentials_only_on_stdin(monkeypatch):
    monkeypatch.setenv("DEBUG", "*")  # stripped for the child: debug() dumps account data
    r = await fake("ok", password="pw-must-stay-on-stdin").scrape()
    assert r.success, r.error_message  # the fake reports "leak" if it sees it in argv/env


async def test_cancel_kills_bridge():
    task = asyncio.create_task(fake("hang").scrape())
    await asyncio.sleep(0.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 15)


@pytest.mark.parametrize(
    ("msg", "et", "kind"),
    [
        (
            {"errorType": "GENERIC", "errorMessage": "Navigation timeout of 30000 ms exceeded"},
            "TIMEOUT",
            "timeout",
        ),
        (
            {"errorType": "GENERIC", "errorMessage": "Automation detected and blocked by server."},
            "AUTOMATION_BLOCKED",
            "provider_changed",
        ),
        (
            {"errorType": "GENERIC", "errorMessage": "Unknown transaction type X"},
            "GENERAL_ERROR",
            "other",
        ),
        ({"errorType": "CHANGE_PASSWORD"}, "CHANGE_PASSWORD", "auth_failed"),
        ({"errorType": "INVALID_PASSWORD"}, "INVALID_PASSWORD", "auth_failed"),
        ({"errorType": "ACCOUNT_BLOCKED"}, "ACCOUNT_BLOCKED", "auth_failed"),
        # BaseScraperWithBrowser throws on results its switch lacks (Leumi's blocked account).
        (
            {"errorType": "GENERIC", "errorMessage": 'unexpected login result "ACCOUNT_BLOCKED"'},
            "ACCOUNT_BLOCKED",
            "auth_failed",
        ),
        ({"errorType": "TWO_FACTOR_RETRIEVER_MISSING"}, "TWO_FACTOR_RETRIEVER_MISSING", "other"),
        ({"errorType": "INVALID_OTP"}, "INVALID_OTP", "auth_failed"),
        ({"errorType": "GENERAL_ERROR", "errorMessage": "x"}, "GENERAL_ERROR", "other"),
        ({}, "GENERAL_ERROR", "other"),
        ({"errorType": "TIMEOUT", "errorMessage": "x"}, "TIMEOUT", "timeout"),
    ],
)
def test_error_types(msg, et, kind):
    r = ibs.to_result("visa cal", {"success": False, **msg})
    assert r.error_type == et
    assert failure_kind(r.error_type, r.error_message) == kind


def test_nan_amount_fails_instead_of_storing_a_guess():
    t = {
        "type": "normal",
        "status": "completed",
        "date": "2026-10-01T00:00:00.000Z",
        "chargedAmount": None,
        "originalAmount": None,
        "description": "x",
    }
    with pytest.raises(ValueError):
        ibs.to_result("max", {"success": True, "accounts": [{"accountNumber": "1", "txns": [t]}]})


def test_engine_selection(monkeypatch):
    creds = {"username": "u", "password": "p"}
    monkeypatch.delenv("FREERISE_IBS_PROVIDERS", raising=False)
    for provider in ibs.COMPANIES:  # default "all": every provider the package has
        assert isinstance(make_scraper(provider, creds), ibs.IbsScraper), provider
    assert not ibs.enabled("mislaka") and not ibs.enabled("hafenix")
    monkeypatch.setenv("FREERISE_IBS_PROVIDERS", "all,-max")  # one provider back on Python
    assert not isinstance(make_scraper("max", creds), ibs.IbsScraper)
    assert isinstance(make_scraper("leumi", creds), ibs.IbsScraper)
    monkeypatch.setenv("FREERISE_IBS_PROVIDERS", "visa cal")
    assert not isinstance(make_scraper("max", creds), ibs.IbsScraper)
    assert isinstance(make_scraper("visa cal", creds), ibs.IbsScraper)
    monkeypatch.setenv("FREERISE_IBS_PROVIDERS", "")
    assert not isinstance(make_scraper("visa cal", creds), ibs.IbsScraper)
    monkeypatch.setenv("FREERISE_IBS_PROVIDERS", "all,mislaka")  # never for Python-only providers
    assert not ibs.enabled("mislaka")


def test_every_package_provider_is_mapped():
    """Python-only = no package equivalent; stored field names = the package's loginFields."""
    assert set(PROVIDER_CONFIGS) - set(ibs.COMPANIES) == {"hafenix", "mislaka", "demo"}
    for key, (_, fields) in ibs.COMPANIES.items():
        cfg = PROVIDER_CONFIGS[key]
        stored = {
            *cfg.required_fields,
            *cfg.optional_fields,
            "otpLongTermToken",
        }  # last: by FreeRise
        assert set(fields) <= stored, key
        assert set(cfg.required_fields) <= set(fields), key  # nothing stored is left behind


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
@pytest.mark.skipif(not (ibs.BRIDGE.parent / "node_modules").is_dir(), reason="no node_modules")
def test_mapping_matches_package_definitions():
    p = subprocess.run(
        [
            "node",
            "-e",
            "const d = require('israeli-bank-scrapers/lib/definitions');"
            + "console.log(JSON.stringify({c: d.CompanyTypes, s: d.SCRAPERS}))",
        ],
        cwd=ibs.BRIDGE.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    defs = json.loads(p.stdout)
    assert {c for c, _ in ibs.COMPANIES.values()} == set(defs["c"].values())
    for key, (company, fields) in ibs.COMPANIES.items():
        login = set(defs["s"][company]["loginFields"]) - {"otpCodeRetriever"}  # the bridge's
        assert set(fields) == login, key


def test_generic_mapping():
    """Normalized package output -> vendored models, the same way for every provider."""
    t = {
        "type": "installments",
        "status": "pending",
        "date": "2026-10-11T21:00:00.000Z",  # 2026-10-12 00:00 in Israel
        "processedDate": "2026-11-02",  # date-only / naive: already local
        "originalAmount": -300,
        "originalCurrency": "USD",
        "chargedAmount": -100.25,
        "chargedCurrency": "ILS",
        "description": "חנות",
        "memo": "תשלום 1 מתוך 3",
        "identifier": 987654,  # numeric (e.g. bank reference numbers)
        "installments": {"number": 1, "total": 3},
        "category": "מזון",
    }
    acc = {
        "accountNumber": "12-345-678",
        "balance": 1500.5,
        "balanceDate": "2026-10-12",
        "savingsAccount": True,
        "txns": [t, {**t, "identifier": "", "status": "completed", "chargedAmount": 0}],
    }
    for provider in ibs.COMPANIES:
        (a,) = ibs.to_result(provider, {"success": True, "accounts": [acc]}).accounts
        assert (a.account_number, a.balance, a.balance_date, a.savings_account) == (
            "12-345-678",
            1500.5,
            "2026-10-12",
            True,
        )
        x, y = a.transactions
        assert (x.date, x.processed_date) == ("2026-10-12", "2026-11-02")
        assert (x.type.value, x.status.value) == ("installments", "pending")
        assert (x.installments.number, x.installments.total) == (1, 3)
        assert (x.identifier, x.charged_amount, x.original_amount) == ("987654", -100.25, -300)
        assert (x.original_currency, x.charged_currency, x.category) == ("USD", "ILS", "מזון")
        assert txn_key(x) == "987654"
        assert y.identifier is None and str(y.charged_amount) == "-0.0"  # as both vendored mappers


async def test_run_credential_through_bridge(sf, credential):
    def factory(provider, creds, options):
        return ibs.IbsScraper(provider, {**creds, "username": "ok"}, options, cmd=FAKE)

    run = await run_credential(sf, credential.id, "manual", scraper_factory=factory)
    assert run.status == "success", run.error
    again = await run_credential(sf, credential.id, "manual", scraper_factory=factory)
    assert (again.added, again.updated) == (0, 0)
    with sf() as s:
        assert s.scalar(select(Account.provider_account_id)) == "1234"
        assert s.scalar(select(Transaction.txn_key)) == "arn1"
        assert s.get(SyncRun, run.id).progress == "fetch"


BRIDGE_READY = shutil.which("node") and (ibs.BRIDGE.parent / "node_modules").is_dir()


@pytest.mark.skipif(not BRIDGE_READY, reason="node / bridge/node_modules not installed")
def test_real_bridge_protocol_without_a_browser(tmp_path):
    """run.mjs end to end with no Chrome: a clean failed result, no secret on stdout."""
    req = {
        "companyId": "max",
        "credentials": {"username": "u", "password": "pw-xyz-123"},
        "startDate": "2026-09-01",
        "futureMonths": 1,
    }
    p = subprocess.run(
        ["node", str(ibs.BRIDGE)],
        input=json.dumps(req) + "\n",
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": str(Path(shutil.which("node")).parent),
            "FREERISE_CHROME_PATH": str(tmp_path / "no-chrome"),
            "TZ": "Asia/Jerusalem",
        },
    )
    lines = [json.loads(x) for x in p.stdout.splitlines()]
    assert lines[-1]["type"] == "result" and lines[-1]["success"] is False
    assert {x["type"] for x in lines} <= {"progress", "result"}
    assert "pw-xyz-123" not in p.stdout + p.stderr


# --- OneZero: the real run.mjs and package flow, OneZero's API stubbed (tests/sync/onezero_stub.mjs)


def onezero(**creds):
    stub = Path(__file__).with_name("onezero_stub.mjs")
    base = {"email": "a@b.c", "password": "pw-onezero", "phoneNumber": "050-1234567"}
    return ibs.IbsScraper(
        "onezero",
        base | creds,
        ScraperOptions(start_date=date.today().replace(day=1)),
        cmd=["node", "--import", str(stub), str(ibs.BRIDGE)],
        timeout_s=60,
    )


@pytest.mark.skipif(not BRIDGE_READY, reason="node / bridge/node_modules not installed")
async def test_onezero_sms_login_returns_long_term_token():
    s = onezero()
    asked, stages = [], []

    async def code():
        asked.append(1)
        return "123456"

    s.on_otp_request, s.on_progress = code, stages.append
    r = await s.scrape()
    assert r.success, r.error_message
    assert asked == [1] and "fetching data" in stages  # stage reported by run.mjs for API scrapers
    assert s.refreshed_otp_long_term_token == "fresh-token"
    (a,) = r.accounts
    assert (a.account_number, a.balance) == ("1234567", 1000.5)
    (t,) = a.transactions
    assert (t.identifier, t.charged_amount, t.description) == ("m1", -42.5, "קפה")


@pytest.mark.skipif(not BRIDGE_READY, reason="node / bridge/node_modules not installed")
async def test_onezero_stored_token_needs_no_sms():
    s = onezero(otpLongTermToken="stored-token")

    async def no_sms():
        raise AssertionError("asked for a code although a token is stored")

    s.on_otp_request = no_sms
    r = await s.scrape()
    assert r.success, r.error_message
    assert s.refreshed_otp_long_term_token is None  # unchanged: nothing to store


@pytest.mark.skipif(not BRIDGE_READY, reason="node / bridge/node_modules not installed")
async def test_onezero_wrong_code_is_invalid_otp():
    s = onezero()

    async def wrong():
        return "000000"

    s.on_otp_request = wrong
    r = await s.scrape()
    assert (r.success, r.error_type) == (False, "INVALID_OTP")
    assert failure_kind(r.error_type, r.error_message) == "auth_failed"
    assert s.refreshed_otp_long_term_token is None


async def test_refreshed_token_is_stored(sf):
    with sf() as s:
        c = Credential(
            provider="onezero",
            label="1Z",
            owner="shai",
            secret_enc=encrypt_json({"email": "otp", "password": "pw", "phoneNumber": "+9725"}),
        )
        s.add(c)
        s.commit()

    def factory(provider, creds, options):
        return ibs.IbsScraper(provider, creds, options, cmd=FAKE)

    async def answer():
        for _ in range(100):
            await asyncio.sleep(0.2)
            with sf() as s:
                if req := s.scalar(select(OtpRequest).where(OtpRequest.status == "waiting")):
                    answer_otp(s, req.id, "123456")
                    return

    task = asyncio.create_task(answer())
    run = await run_credential(sf, c.id, "manual", scraper_factory=factory, otp_poll_s=0.1)
    await task
    assert run.status == "success", run.error
    with sf() as s:
        assert decrypt_json(s.get(Credential, c.id).secret_enc)["otpLongTermToken"] == "fresh-token"
