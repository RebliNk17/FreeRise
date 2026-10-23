import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fakes import account, fake_factory, ok, txn
from scraper import ScrapingResult
from scraper.models.transaction import TransactionStatus
from sqlalchemy import func, select

from freerise.crypto import decrypt_json, encrypt_json
from freerise.models import Account, Balance, Credential, OtpRequest, Transaction
from freerise.sync.otp import answer_otp
from freerise.sync.service import _scrub, failure_kind, run_credential


def count(sf, model):
    with sf() as s:
        return s.scalar(select(func.count()).select_from(model))


def three_txns():
    return ok(
        account("1111", txn(-10, "A", identifier="a1"), txn(-20, "B", identifier="b1")),
        account("2222", txn(-30, "C")),
    )


async def test_first_sync_inserts_accounts_and_transactions(sf, credential):
    run = await run_credential(
        sf, credential.id, "manual", scraper_factory=fake_factory(three_txns())
    )
    assert run.status == "success" and run.failure_kind is None
    assert run.added == 3
    assert count(sf, Account) == 2
    assert count(sf, Transaction) == 3
    with sf() as s:
        acc = s.scalar(select(Account).where(Account.provider_account_id == "1111"))
        assert acc.kind == "card"
        assert acc.display_name == "Max 1111"
        assert s.get(Credential, credential.id).last_success_at is not None


async def test_resync_is_idempotent(sf, credential):
    await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(three_txns()))
    run = await run_credential(
        sf, credential.id, "schedule", scraper_factory=fake_factory(three_txns())
    )
    assert run.status == "success"
    assert run.added == 0
    assert run.updated == 0
    assert count(sf, Transaction) == 3


async def test_pending_becomes_completed(sf, credential):
    pending = ok(account("1111", txn(-50, "Cafe", status=TransactionStatus.PENDING)))
    done = ok(account("1111", txn(-50, "Cafe", identifier="x9")))
    await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(pending))
    run = await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(done))
    assert run.added == 0
    assert run.updated == 1
    with sf() as s:
        rows = s.scalars(select(Transaction)).all()
        assert len(rows) == 1
        assert rows[0].status == "completed"
        assert rows[0].identifier == "x9"


async def test_login_failure_records_error(sf, credential):
    bad = ScrapingResult(success=False, error_type="invalid_password", error_message="nope")
    run = await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(bad))
    assert run.status == "failed" and run.failure_kind == "auth_failed"
    assert "invalid_password" in run.error
    with sf() as s:
        assert "invalid_password" in s.get(Credential, credential.id).last_error
    assert count(sf, Account) == 0
    assert count(sf, Transaction) == 0


async def test_otp_answered(sf, credential):
    factory = fake_factory(three_txns(), ask_otp=True)

    async def answer():
        while True:
            await asyncio.sleep(0.05)
            with sf() as s:
                req = s.scalar(select(OtpRequest).where(OtpRequest.status == "waiting"))
                if req:
                    answer_otp(s, req.id, "123456")
                    return

    run, _ = await asyncio.gather(
        run_credential(sf, credential.id, "manual", scraper_factory=factory, otp_poll_s=0.05),
        answer(),
    )
    assert run.status == "success"
    assert factory.created[0][0].otp_code == "123456"
    with sf() as s:
        assert s.scalar(select(OtpRequest)).status == "answered"


async def test_otp_timeout(sf, credential):
    factory = fake_factory(three_txns(), ask_otp=True)
    run = await run_credential(
        sf, credential.id, "manual", scraper_factory=factory, otp_timeout_s=1, otp_poll_s=0.1
    )
    assert run.status == "otp_timeout" and run.failure_kind == "otp_timeout"
    assert count(sf, Transaction) == 0
    with sf() as s:
        assert s.scalar(select(OtpRequest)).status == "expired"


async def test_long_term_token_persisted(sf, credential):
    factory = fake_factory(three_txns(), mutate={"otpLongTermToken": "tok"})
    await run_credential(sf, credential.id, "manual", scraper_factory=factory)
    with sf() as s:
        creds = decrypt_json(s.get(Credential, credential.id).secret_enc)
    assert creds == {"username": "u", "password": "p", "otpLongTermToken": "tok"}


async def test_amount_sign_and_installments_stored(sf, credential):
    result = ok(account("1111", txn(-120.5, "TV", installments=(3, 12))))
    await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(result))
    with sf() as s:
        t = s.scalar(select(Transaction))
    assert t.amount == Decimal("-120.50")
    assert t.installment_number == 3
    assert t.installment_total == 12
    assert t.raw["installments"] == {"number": 3, "total": 12}


async def test_refreshed_long_term_token_attribute_persisted(sf, credential):
    factory = fake_factory(three_txns(), refreshed_token="fresh")
    await run_credential(sf, credential.id, "manual", scraper_factory=factory)
    with sf() as s:
        creds = decrypt_json(s.get(Credential, credential.id).secret_enc)
    assert creds["otpLongTermToken"] == "fresh"


async def test_identical_transactions_both_kept(sf, credential):
    def result():
        return ok(account("1111", txn(-12, "Aroma"), txn(-12.0, "Aroma")))

    run = await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(result()))
    assert run.added == 2
    run = await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(result()))
    assert run.added == 0
    assert run.updated == 0
    assert count(sf, Transaction) == 2


async def test_pending_becomes_completed_without_identifier(sf, credential):
    pending = ok(account("1111", txn(-50, "Cafe", status=TransactionStatus.PENDING)))
    done = ok(account("1111", txn(-50.0, "Cafe")))
    await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(pending))
    run = await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(done))
    assert (run.added, run.updated) == (0, 1)
    with sf() as s:
        rows = s.scalars(select(Transaction)).all()
    assert [r.status for r in rows] == ["completed"]


async def test_balance_rows_written(sf, credential):
    result = ok(account("1111", balance=1234.5), account("2222"))
    await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(result))
    with sf() as s:
        rows = s.scalars(select(Balance)).all()
    assert [r.balance for r in rows] == [Decimal("1234.50")]
    assert rows[0].as_of is not None


async def test_merchant_key_set(sf, credential):
    res = ok(account("1111", txn(-10, "SPOTIFY P420ECF50D", identifier="a1")))
    await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(res))
    with sf() as s:
        assert s.scalar(select(Transaction.merchant_key)) == "spotify"


async def test_login_failure_disables_credential(sf, credential):
    bad = ScrapingResult(success=False, error_type="INVALID_PASSWORD", error_message="nope")
    run = await run_credential(sf, credential.id, "schedule", scraper_factory=fake_factory(bad))
    assert run.status == "failed"
    with sf() as s:
        c = s.get(Credential, credential.id)
        assert c.enabled is False
        assert c.last_error.startswith("הושבת אוטומטית — יש לעדכן סיסמה")


async def test_general_failure_keeps_credential_enabled(sf, credential):
    bad = ScrapingResult(success=False, error_type="TIMEOUT", error_message="slow")
    await run_credential(sf, credential.id, "schedule", scraper_factory=fake_factory(bad))
    with sf() as s:
        assert s.get(Credential, credential.id).enabled is True


async def test_error_text_scrubs_secrets(sf):
    with sf() as s:
        c = Credential(
            provider="max",
            label="Max",
            owner="shai",
            secret_enc=encrypt_json({"username": "shai123", "password": "hunter22", "pin": "1"}),
        )
        s.add(c)
        s.commit()
    msg = "login failed for shai123 with hunter22 (1)"
    bad = ScrapingResult(success=False, error_type="GENERAL_ERROR", error_message=msg)
    run = await run_credential(sf, c.id, "manual", scraper_factory=fake_factory(bad))
    assert "shai123" not in run.error and "hunter22" not in run.error
    assert "•••• with ••••" in run.error and "(1)" in run.error
    with sf() as s:
        assert "hunter22" not in s.get(Credential, c.id).last_error


def test_scrub_overlapping_encoded_and_proxy_secrets(monkeypatch):
    monkeypatch.setenv("FREERISE_SCRAPER_PROXY", "http://pu:prox%40pw@proxy.example:8080")
    secrets = {"id": "1234", "password": "p@ss 123456"}
    text = "x 1234567 p@ss 123456 p%40ss%20123456 http://pu:prox%40pw@proxy.example:8080 prox@pw"
    out = _scrub(text, secrets)
    for leak in ("1234", "p@ss", "p%40ss", "prox", "123456"):
        assert leak not in out, out


def _recent(days_ago=0):
    return (date.today() - timedelta(days=days_ago)).isoformat() + "T00:00:00.000Z"


async def test_pending_replaced_by_completed_with_different_amount(sf, credential):
    d = _recent(2)
    pending = ok(account("1111", txn(-50, "Cafe", d, status=TransactionStatus.PENDING)))
    done = ok(account("1111", txn(-52.5, "Cafe", d, identifier="x9")))
    await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(pending))
    await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(done))
    with sf() as s:
        rows = s.scalars(select(Transaction)).all()
    assert [(r.status, r.amount) for r in rows] == [("completed", Decimal("-52.50"))]


async def test_cancelled_pending_removed(sf, credential):
    d = _recent(1)
    first = ok(
        account(
            "1111",
            txn(-10, "Keep", d, identifier="k1"),
            txn(-99, "Hold", d, status=TransactionStatus.PENDING),
        )
    )
    second = ok(account("1111", txn(-10, "Keep", d, identifier="k1")))
    await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(first))
    await run_credential(sf, credential.id, "manual", scraper_factory=fake_factory(second))
    with sf() as s:
        assert [r.description for r in s.scalars(select(Transaction))] == ["Keep"]


async def test_first_sync_window_is_two_years(sf, credential):
    factory = fake_factory(ok())
    await run_credential(sf, credential.id, "manual", scraper_factory=factory)
    start = factory.created[0][1].start_date
    assert 729 <= (date.today() - start).days <= 731


@pytest.mark.parametrize(
    ("error_type", "error", "kind"),
    [
        ("INVALID_PASSWORD", "INVALID_PASSWORD: nope", "auth_failed"),
        ("change_password", "x", "auth_failed"),
        ("INVALID_OTP", "x", "auth_failed"),
        ("TIMEOUT", "TIMEOUT: slow", "timeout"),
        (None, "TimeoutError: page.goto exceeded", "timeout"),
        ("AUTOMATION_BLOCKED", "AUTOMATION_BLOCKED: blocked", "provider_changed"),
        ("AUTOMATION_BLOCKED", "AUTOMATION_BLOCKED: request timeout", "provider_changed"),
        ("TIMEOUT", "TIMEOUT: unexpected page", "timeout"),
        ("GENERAL_ERROR", "GENERAL_ERROR: unexpected page after login", "provider_changed"),
        (None, "Error: waiting for selector #balance", "provider_changed"),
        ("GENERAL_ERROR", "GENERAL_ERROR: boom", "other"),
    ],
)
def test_failure_kind(error_type, error, kind):
    assert failure_kind(error_type, error) == kind


async def test_exception_timeout_recorded(sf, credential):
    def factory(provider, credentials, options):
        raise TimeoutError("scrape took too long")

    run = await run_credential(sf, credential.id, "manual", scraper_factory=factory)
    assert run.status == "failed" and run.failure_kind == "timeout"
