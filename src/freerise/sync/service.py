import dataclasses
import logging
import os
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import quote, unquote, urlsplit
from zoneinfo import ZoneInfo

from scraper import PROVIDER_CONFIGS, ScraperOptions
from scraper.models.account import AccountResult
from scraper.models.transaction import Transaction as ScrapedTxn
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from freerise.categorize.normalize import normalize_merchant
from freerise.config import get_settings
from freerise.crypto import decrypt_json, encrypt_json
from freerise.models import Account, Balance, Credential, SyncRun, Transaction
from freerise.pension.ingest import ingest_mislaka
from freerise.sync.dedup import txn_key
from freerise.sync.demo_provider import make_scraper
from freerise.sync.otp import OtpTimeout, wait_for_otp

log = logging.getLogger("freerise.sync")

KINDS = {"banks": "bank", "credit_cards": "card", "insurances": "fund"}
# Retrying a wrong password on schedule gets the bank account locked.
LOGIN_FAILURES = {"invalid_password", "change_password", "account_blocked"}
DISABLED_NOTE = "הושבת אוטומטית — יש לעדכן סיסמה"
# Not every lockout is reported as one (Max's lock screen ends as a timeout / general error), so
# this many failed runs in a row that never got past login pause scheduled syncs until a run
# (a manual retry, a verify) succeeds.
PAUSE_AFTER = 2
# ponytail: substring heuristics over the scraper's error text; extend as new messages show up.
PROVIDER_CHANGED_HINTS = ("unexpected", "selector", "waf", "parse")
FIRST_SYNC_DAYS = 730
# A new connection's verify run fetches a short window so the user isn't kept waiting; the
# full history follows in a background run.
VERIFY_DAYS = 30
STAGES = {"logging in": "login", "fetching data": "fetch"}  # BaseScraper progress messages
STALE = timedelta(minutes=30)  # a run queued or started longer ago than this is dead


def _scrub(text: str, secrets: dict) -> str:
    vals = {str(v) for v in secrets.values() if v}
    if proxy := os.environ.get("FREERISE_SCRAPER_PROXY"):  # may carry user:pass
        vals |= {proxy, unquote(urlsplit(proxy).password or "")}
    vals |= {quote(v, safe="") for v in vals}  # as it appears inside URLs / form bodies
    # Longest first, so a secret that contains a shorter one is never left half-masked.
    for v in sorted((v for v in vals if len(v) >= 4), key=len, reverse=True):
        text = text.replace(v, "••••")
    return text


def failure_kind(error_type: str | None, error: str) -> str:
    """Bucket a failed run: auth_failed | timeout | provider_changed | other (spec §6.1)."""
    et, text = (error_type or "").lower(), error.lower()
    if et in LOGIN_FAILURES or et == "invalid_otp":
        return "auth_failed"
    if et == "timeout":
        return "timeout"
    if et == "automation_blocked":
        return "provider_changed"
    if "timeout" in text:
        return "timeout"
    if any(h in text for h in PROVIDER_CHANGED_HINTS):
        return "provider_changed"
    return "other"


def active_run_id(s: Session, credential_id: int) -> int | None:
    """The connection's sync that is queued or in progress, if any. Older than STALE = dead
    (worker restarted or crashed), so it can't block the next sync forever."""
    fresh = datetime.now(UTC) - STALE
    return s.scalar(
        select(SyncRun.id)
        .where(
            SyncRun.credential_id == credential_id,
            ((SyncRun.status == "requested") & (SyncRun.created_at > fresh))
            | ((SyncRun.status == "running") & (SyncRun.started_at > fresh)),
        )
        .order_by(SyncRun.id.desc())
        .limit(1)
    )


def login_paused(s: Session, credential_id: int) -> bool:
    """The last PAUSE_AFTER runs all failed before fetching data (wrong details, lock screen…)."""
    rows = s.execute(
        select(SyncRun.status, SyncRun.progress)
        .where(
            SyncRun.credential_id == credential_id,
            SyncRun.started_at.is_not(None),  # not a duplicate request refused before it ran
            SyncRun.finished_at.is_not(None),
            # A failed verify tried new details, not this connection's own; a success counts.
            (SyncRun.trigger != "verify") | (SyncRun.status == "success"),
        )
        .order_by(SyncRun.id.desc())
        .limit(PAUSE_AFTER)
    ).all()
    return len(rows) == PAUSE_AFTER and all(st == "failed" and p != "fetch" for st, p in rows)


def _now() -> datetime:
    return datetime.now(UTC)


def _date(s: str) -> date:
    return datetime.fromisoformat(s).date()


def _money(x) -> Decimal | None:
    return None if x is None else Decimal(str(x)).quantize(Decimal("0.01"))


def _fields(t: ScrapedTxn) -> dict:
    return {
        "date": _date(t.date),
        "processed_date": _date(t.processed_date or t.date),
        "amount": _money(t.charged_amount),
        "original_amount": _money(t.original_amount),
        "original_currency": t.original_currency,
        "description": t.description,
        "merchant_key": normalize_merchant(t.description),
        "memo": t.memo,
        "identifier": t.identifier,
        "installment_number": t.installments.number if t.installments else None,
        "installment_total": t.installments.total if t.installments else None,
        "provider_category": t.category,
        "status": t.status.value if hasattr(t.status, "value") else t.status,
        # Enums are str subclasses, so json serialises them as their values.
        "raw": dataclasses.asdict(t),
    }


# ponytail: no vendored card scraper fills these yet; picked up once one does.
HOLDER_KEYS = ("cardHolderName", "ownerName", "holder_name", "owner_name")


def _upsert_account(s: Session, cred: Credential, a: AccountResult) -> Account:
    acc = s.scalar(
        select(Account).where(
            Account.credential_id == cred.id, Account.provider_account_id == a.account_number
        )
    )
    if acc is None:
        acc = Account(
            credential_id=cred.id,
            provider_account_id=a.account_number,
            kind=KINDS[PROVIDER_CONFIGS[cred.provider].service],
            display_name=f"{cred.label} {a.account_number[-4:]}",
        )
        s.add(acc)
        s.flush()
    meta = a.metadata or {}
    holder = next((meta[k] for k in HOLDER_KEYS if meta.get(k)), None)
    if holder and acc.holder is None:  # never overwrite (or refill) the user's own value
        acc.holder = str(holder).strip()
    return acc


def _upsert_txn(
    s: Session, acc: Account, t: ScrapedTxn, key: str, fresh: set[str]
) -> tuple[str | None, Transaction]:
    """Returns ("added" | "updated" | None (unchanged), row)."""
    f = _fields(t)
    row = s.scalar(
        select(Transaction).where(Transaction.account_id == acc.id, Transaction.txn_key == key)
    )
    if row is None and t.identifier:
        # Completed version gained an identifier: adopt its identifier-less pending twin.
        row = s.scalar(
            select(Transaction)
            .where(
                Transaction.account_id == acc.id,
                Transaction.identifier.is_(None),
                Transaction.status == "pending",
                Transaction.date == f["date"],
                Transaction.amount == f["amount"],
                Transaction.description == f["description"],
            )
            .limit(1)
        )
    if row is None:
        # Same charge under another identity (the provider or engine renumbered it, e.g. Isracard
        # web vs mobile voucher numbers): adopt the row this scrape no longer reports by its key.
        # Descriptions differ too ("SHOP COM" / "SHOP.COM", 20-char cuts), so they only rank.
        row = s.scalar(
            select(Transaction)
            .where(
                Transaction.account_id == acc.id,
                Transaction.txn_key.not_in(fresh),
                Transaction.date == f["date"],
                Transaction.processed_date == f["processed_date"],
                Transaction.amount == f["amount"],
                Transaction.installment_number.is_not_distinct_from(f["installment_number"]),
            )
            .order_by(
                Transaction.description != f["description"],
                Transaction.merchant_key != f["merchant_key"],
                Transaction.id,
            )
            .limit(1)
        )
    if row is None:
        row = Transaction(account_id=acc.id, txn_key=key, **f)
        s.add(row)
        return "added", row
    f["txn_key"] = key
    changed = False
    for k, v in f.items():
        if getattr(row, k) != v:
            setattr(row, k, v)
            changed = True
    return ("updated" if changed else None), row


def _no_money_moved(t: ScrapedTxn) -> bool:
    """₪0 rows (waived fees, CashCal placeholders) are noise. A pending foreign charge
    can show ₪0 before conversion, so only drop it once completed or in shekels."""
    if _money(t.charged_amount) != 0:
        return False
    status = getattr(t.status, "value", t.status)
    return status != "pending" or (t.original_currency or "ILS") in ("ILS", "₪")


def _store(
    s: Session, cred: Credential, accounts: list[AccountResult], start: date
) -> tuple[int, int]:
    added = updated = 0
    for a in accounts:
        acc = _upsert_account(s, cred, a)
        seen: Counter[str] = Counter()
        touched: set[int] = set()
        keyed = []
        for t in a.transactions:
            if _no_money_moved(t):
                continue
            key = txn_key(t)
            seen[key] += 1
            if not t.identifier and seen[key] > 1:
                # ponytail: identical identifier-less txns keyed by occurrence order;
                # assumes the provider returns them in a stable order.
                key = f"{key}|#{seen[key]}"
            keyed.append((t, key))
        fresh = {k for _, k in keyed}
        for t, key in keyed:
            r, row = _upsert_txn(s, acc, t, key, fresh)
            added += r == "added"
            updated += r == "updated"
            s.flush()
            touched.add(row.id)
        # A pending row this scrape no longer reports was cancelled or completed under a
        # different amount/description; keeping it would double count.
        s.execute(
            delete(Transaction).where(
                Transaction.account_id == acc.id,
                Transaction.status == "pending",
                Transaction.date >= start,
                Transaction.id.not_in(touched),
            )
        )
        if a.balance is not None:
            as_of = datetime.fromisoformat(a.balance_date) if a.balance_date else _now()
            if as_of.tzinfo is None:
                as_of = as_of.replace(tzinfo=UTC)
            s.add(Balance(account_id=acc.id, as_of=as_of, balance=_money(a.balance)))
    return added, updated


async def run_credential(
    session_factory: sessionmaker,
    credential_id: int,
    trigger: str,
    scraper_factory=make_scraper,
    *,
    run_id: int | None = None,
    otp_timeout_s: int = 300,
    otp_poll_s: float = 2,
) -> SyncRun:
    with session_factory() as s:
        cred = s.get(Credential, credential_id)
        run = s.get(SyncRun, run_id) if run_id else SyncRun(credential_id=cred.id, trigger=trigger)
        verify = run.trigger == "verify"
        first = verify and not cred.verified
        run.status, run.started_at = "running", _now()
        run.progress_at = run.started_at
        s.add(run)
        s.commit()
        run_id = run.id
        staged = verify and cred.pending_secret_enc is not None  # new details for a live one
        original = decrypt_json(cred.pending_secret_enc if staged else cred.secret_enc)
        since = cred.last_success_at
        today = datetime.now(ZoneInfo(get_settings().tz)).date()
        # 2FA providers may ask for a fresh code on every login: no second run, full history now.
        quick = first and not PROVIDER_CONFIGS[cred.provider].requires_2fa
        days = VERIFY_DAYS if quick else FIRST_SYNC_DAYS
        start = (since - timedelta(days=14)).date() if since else today - timedelta(days)

    creds = dict(original)
    otp_timed_out = False

    async def on_otp():
        nonlocal otp_timed_out
        try:
            return await wait_for_otp(
                session_factory, run_id, timeout_s=otp_timeout_s, poll_s=otp_poll_s
            )
        except OtpTimeout:
            otp_timed_out = True  # real scrapers swallow this into a failed ScrapingResult
            raise

    def on_progress(message: str) -> None:
        with session_factory() as s:
            if r := s.get(SyncRun, run_id):
                r.progress = STAGES.get(message, r.progress)
                r.progress_at = _now()
                s.commit()

    status, error, result = "failed", None, None
    try:
        # Local debugging only: screenshots can show personal data, so they stay off unless set.
        shots = os.environ.get("FREERISE_FAILURE_SCREENSHOTS")
        shot = os.path.join(shots, f"run{run_id}-{cred.provider}.png") if shots else None
        if shot:
            os.makedirs(shots, exist_ok=True)
        options = ScraperOptions(start_date=start, store_failure_screenshot_path=shot)
        scraper = scraper_factory(cred.provider, creds, options)
        scraper.on_otp_request = on_otp
        scraper.on_progress = on_progress
        result = await scraper.scrape()
        # OneZero exposes a refreshed long-term token on the scraper, not in creds.
        if tok := getattr(scraper, "refreshed_otp_long_term_token", None):
            creds["otpLongTermToken"] = tok
        if result.success:
            status = "success"
        else:
            error = f"{result.error_type}: {result.error_message}"
    except OtpTimeout:
        otp_timed_out = True
    except Exception as e:  # noqa: BLE001 - any failure is recorded on the run
        error = f"{type(e).__name__}: {e}"
    if otp_timed_out:
        status, error = "otp_timeout", "OTP not entered in time"

    with session_factory() as s:
        cred = s.get(Credential, credential_id)
        run = s.get(SyncRun, run_id)
        if cred is None or run is None or run.status != "running":
            return run  # deleted, or a verify that was canceled / timed out meanwhile
        if status == "success":
            try:
                if cred.provider in (
                    "mislaka",
                    "hafenix",
                    "migdal",
                ):  # funds, not bank/card accounts
                    run.added = ingest_mislaka(s, credential_id, result).added
                else:
                    run.added, run.updated = _store(s, cred, result.accounts, start)
            except Exception as e:  # noqa: BLE001 - any failure is recorded on the run
                s.rollback()
                cred, run = s.get(Credential, credential_id), s.get(SyncRun, run_id)
                status, error = "failed", f"{type(e).__name__}: {e}"
        if verify and status == "success":
            cred.secret_enc, cred.pending_secret_enc = encrypt_json(creds), None
            cred.verified = cred.enabled = True
        elif creds != original:
            setattr(cred, "pending_secret_enc" if staged else "secret_enc", encrypt_json(creds))
        run.status, run.finished_at = status, _now()
        if error:
            error = _scrub(error, {**original, **creds})
        run.error = error[:500] if error else None
        log.log(
            logging.WARNING if error else logging.INFO,
            "sync run %s (%s): %s %s",
            run_id,
            cred.provider,
            status,
            run.error or "",
        )
        if status == "otp_timeout":
            run.failure_kind = "otp_timeout"
        elif status == "failed":
            run.failure_kind = failure_kind(getattr(result, "error_type", None), error or "")
        if status == "success":
            cred.last_error = None
            if quick and PROVIDER_CONFIGS[cred.provider].service != "insurances":
                # last_success_at stays unset so this run fetches the full history.
                s.add(SyncRun(credential_id=cred.id, trigger="manual", status="requested"))
            else:
                cred.last_success_at = run.finished_at
        elif verify:
            pass  # a failed verify never touches the connection (old details stay in use)
        elif (getattr(result, "error_type", None) or "").lower() in LOGIN_FAILURES:
            cred.enabled = False
            cred.last_error = f"{DISABLED_NOTE}: {run.error}"[:500]
        else:
            cred.last_error = run.error
        s.commit()
        return run
