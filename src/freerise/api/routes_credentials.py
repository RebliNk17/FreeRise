import re
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from scraper import PROVIDER_CONFIGS
from sqlalchemy import select, update
from sqlalchemy.orm import Session, object_session

from freerise.accounts import account_holder, account_label, active_card_ids
from freerise.api.deps import DB, current_user, get_or_404
from freerise.crypto import decrypt_json, encrypt_json, mask
from freerise.models import Account, Credential, OtpRequest, SyncRun, User
from freerise.sync import demo_provider, ips
from freerise.sync.otp import answer_otp
from freerise.sync.service import active_run_id, login_paused

router = APIRouter()
Me = Annotated[User, Depends(current_user)]

# Registry order is banks, credit cards, insurances.
REAL_PROVIDERS = tuple(k for k in PROVIDER_CONFIGS if k != demo_provider.KEY)


def providers_offered() -> tuple[str, ...]:
    return ((demo_provider.KEY,) if demo_provider.demo_enabled() else ()) + REAL_PROVIDERS


# No status change for this long (and not waiting for a code) fails the verify.
STALL = timedelta(minutes=3)
# Logged in and fetching: a 2FA provider pulls its full history here with no further progress.
FETCH_STALL = timedelta(minutes=20)
OTP_RE = re.compile(r"\d{4,8}")
OTP_MAX, OTP_WINDOW_S = 5, 10 * 60
# ponytail: in-memory per-user window like routes_auth; one API process.
_otp_tries: dict[int, deque[float]] = {}
_otp_lock = threading.Lock()


class Provider(BaseModel):
    key: str
    name: str
    service: str
    required_fields: list[str]
    optional_fields: list[str]
    login_methods: list[list[str]]  # each a complete login; the first is required_fields
    requires_2fa: bool


class AccountBrief(BaseModel):
    label: str  # account_label(): "מקס ••1234"
    holder: str
    kind: str
    active: bool  # cards: used in the last 6 months or carrying a balance


def _accounts(c: Credential) -> list[AccountBrief]:
    s = object_session(c)
    accounts = list(
        s.scalars(select(Account).where(Account.credential_id == c.id).order_by(Account.id))
    )
    active = active_card_ids(s, accounts)
    return [
        AccountBrief(
            label=account_label(a), holder=account_holder(a), kind=a.kind, active=a.id in active
        )
        for a in accounts
    ]


class CredentialOut(BaseModel):
    id: int
    provider: str
    label: str
    owner: str
    enabled: bool
    last_success_at: datetime | None
    last_error: str | None
    last_failure_kind: str | None  # of the latest finished run; null after a success
    # Scheduled syncs stopped after repeated login failures; a successful manual sync resumes.
    sync_paused: bool = False
    syncing: bool = False  # a sync is queued or running now
    fields: dict[str, str | None]
    accounts: list[AccountBrief] = []
    verify_run_id: int | None = None  # set when this request started a verify run


class CredentialIn(BaseModel):
    provider: str
    label: str
    owner: str
    fields: dict[str, str]


class CredentialPatch(BaseModel):
    label: str | None = None
    owner: str | None = None
    enabled: bool | None = None
    fields: dict[str, str] | None = None
    method: int | None = None  # index into login_methods: drops the other methods' stored fields


def _out(c: Credential) -> CredentialOut:
    return CredentialOut(
        id=c.id,
        provider=c.provider,
        label=c.label,
        owner=c.owner,
        enabled=c.enabled,
        last_success_at=c.last_success_at,
        last_error=c.last_error,
        # ponytail: one query per credential; a household has a handful
        last_failure_kind=object_session(c).scalar(
            select(SyncRun.failure_kind)
            .where(
                SyncRun.credential_id == c.id,
                SyncRun.finished_at.is_not(None),
                SyncRun.trigger != "verify",  # a failed re-verify leaves the connection as it was
            )
            .order_by(SyncRun.id.desc())
            .limit(1)
        ),
        sync_paused=login_paused(object_session(c), c.id),
        syncing=active_run_id(object_session(c), c.id) is not None,
        # Only what the forms ask for: not a stored device token, nor a field this engine ignores.
        fields=mask(
            {k: v for k, v in decrypt_json(c.secret_enc).items() if k in _form_fields(c.provider)}
        ),
        accounts=_accounts(c),
    )


def login_methods(provider: str) -> list[list[str]]:
    alt = ips.LOGIN_METHODS.get(provider) if ips.enabled(provider) else None
    return alt or [PROVIDER_CONFIGS[provider].required_fields]


def optional_fields(provider: str) -> list[str]:
    """Max's `id` answers the vendored browser engine's ID challenge; the app API never asks."""
    return [] if ips.enabled(provider) else PROVIDER_CONFIGS[provider].optional_fields


def _form_fields(provider: str) -> set[str]:
    return {f for m in login_methods(provider) for f in m} | set(optional_fields(provider))


def _check_fields(
    provider: str, new: dict[str, str], full: dict[str, str], method: int | None = None
) -> None:
    """`new` = submitted keys (must be known); `full` = resulting secret (must hold the chosen
    login method, else any one; `missing` lists what the nearest one lacks)."""
    if provider not in providers_offered():
        raise HTTPException(422, "unknown provider")
    methods = login_methods(provider)
    unknown = set(new) - _form_fields(provider)
    if method is not None:  # checked by _for_method
        methods = [methods[method]]
    missing = min(([f for f in m if not full.get(f)] for m in methods), key=len)
    if unknown or missing:
        raise HTTPException(422, {"missing": missing, "unknown": sorted(unknown)})


def _for_method(provider: str, method: int | None, fields: dict) -> dict:
    """`fields` without what only the other login methods use (the engine prefers a stored
    password, so switching to an SMS login has to drop it)."""
    if method is None:
        return fields
    methods = login_methods(provider)
    if not 0 <= method < len(methods):
        raise HTTPException(422, "unknown login method")
    keep = {*methods[method], *optional_fields(provider)}
    other = {f for m in methods for f in m} - keep
    return {k: v for k, v in fields.items() if k not in other}


@router.get("/providers")
def providers() -> list[Provider]:
    return [
        Provider(
            key=k,
            name=(c := PROVIDER_CONFIGS[k]).name,
            service=c.service,
            required_fields=c.required_fields,
            optional_fields=optional_fields(k),
            login_methods=login_methods(k),
            requires_2fa=c.requires_2fa,
        )
        for k in providers_offered()
    ]


@router.get("/credentials")
def list_credentials(db: DB) -> list[CredentialOut]:
    q = select(Credential).where(Credential.verified).order_by(Credential.id)
    return [_out(c) for c in db.scalars(q)]


def _cancel_verify(db: Session, c: Credential, why: str = "VERIFY_CANCELED: canceled") -> None:
    """Fail the credential's open verify runs; the worker then drops their outcome."""
    open_runs = select(SyncRun.id).where(
        SyncRun.credential_id == c.id,
        SyncRun.trigger == "verify",
        SyncRun.status.in_(("requested", "running")),
    )
    db.execute(
        update(OtpRequest)
        .where(OtpRequest.sync_run_id.in_(open_runs), OtpRequest.status == "waiting")
        .values(status="expired")
    )
    db.execute(
        update(SyncRun)
        .where(SyncRun.id.in_(open_runs))
        .values(status="failed", failure_kind="other", error=why, finished_at=datetime.now(UTC))
    )


def _start_verify(db: Session, c: Credential, user: User) -> int:
    _cancel_verify(db, c)
    run = SyncRun(credential_id=c.id, trigger="verify", status="requested", user_id=user.id)
    db.add(run)
    db.flush()
    return run.id


@router.post("/credentials", status_code=201)
def create_credential(body: CredentialIn, db: DB, me: Me) -> CredentialOut:
    """Saved unverified (hidden, never scheduled) until its verify run succeeds."""
    _check_fields(body.provider, body.fields, body.fields)
    if dup := _duplicate_of(db, body.provider, body.fields):
        if dup.verified:
            _refuse_duplicate(dup)
        db.delete(dup)  # an abandoned, never-verified attempt for the same login: replace it
        db.flush()
    c = Credential(
        provider=body.provider,
        label=body.label,
        owner=body.owner,
        secret_enc=encrypt_json(body.fields),
        verified=False,
    )
    db.add(c)
    db.flush()
    run_id = _start_verify(db, c, me)
    db.commit()
    return _out(c).model_copy(update={"verify_run_id": run_id})


def _identity(fields: dict) -> dict[str, str]:
    """Who the login is for: every non-secret field (id, username, card digits...)."""
    return {k: str(v).strip().lower() for k, v in fields.items() if v and not _secret(k)}


def _duplicate_of(db: Session, provider: str, fields: dict, exclude: int | None = None):
    """An existing connection to the same provider for the same login, else None."""
    mine = _identity(fields)
    for c in db.scalars(select(Credential).where(Credential.provider == provider)):
        other = _identity(decrypt_json(c.secret_enc))
        shared = mine.keys() & other.keys()
        if c.id != exclude and shared and all(mine[k] == other[k] for k in shared):
            return c
    return None


def _refuse_duplicate(dup: Credential) -> None:
    raise HTTPException(409, {"code": "duplicate", "credential_id": dup.id, "label": dup.label})


@router.get("/credentials/{id}/details")
def credential_details(id: int, db: DB) -> dict[str, str]:
    """Non-secret fields in clear (id, card digits, username) to prefill the edit form;
    passwords and tokens are never sent back."""
    c = get_or_404(db, Credential, id)
    return {
        k: v
        for k, v in decrypt_json(c.pending_secret_enc or c.secret_enc).items()
        if v and not _secret(k)
    }


@router.patch("/credentials/{id}")
def update_credential(id: int, body: CredentialPatch, db: DB, me: Me) -> CredentialOut:
    c = get_or_404(db, Credential, id)
    for k in ("label", "owner", "enabled"):
        if (v := getattr(body, k)) is not None:
            setattr(c, k, v)
    run_id = None
    stored = decrypt_json(c.secret_enc)
    kept = _for_method(c.provider, body.method, stored)
    # omitted or empty-string fields keep their stored value
    new = {k: v for k, v in (body.fields or {}).items() if v}
    if new or kept != stored:
        merged = kept | new
        _check_fields(c.provider, body.fields or {}, merged, body.method)
        if dup := _duplicate_of(db, c.provider, merged, exclude=c.id):
            _refuse_duplicate(dup)
        if c.verified:  # the old details stay in use until the new ones verify
            c.pending_secret_enc = encrypt_json(merged)
        else:
            c.secret_enc = encrypt_json(merged)
        run_id = _start_verify(db, c, me)
    db.commit()
    return _out(c).model_copy(update={"verify_run_id": run_id})


@router.delete("/credentials/{id}", status_code=204)
def delete_credential(id: int, db: DB) -> None:
    db.delete(get_or_404(db, Credential, id))
    db.commit()


class VerifyOut(BaseModel):
    run_id: int
    # sending | connecting | otp | verifying | success | failed
    stage: str
    otp_expires_at: datetime | None
    failure_kind: str | None
    error: str | None  # scrubbed scraper text, for the collapsed technical details
    accounts: list[AccountBrief]
    credential: CredentialOut  # non-secret details to prefill a fix
    # A new connection's non-secret fields in clear (the user just typed them), to prefill a fix.
    prefill: dict[str, str] = {}


class OtpIn(BaseModel):
    code: str


def _latest_verify(db: Session, c: Credential) -> SyncRun:
    run = db.scalar(
        select(SyncRun)
        .where(SyncRun.credential_id == c.id, SyncRun.trigger == "verify")
        .order_by(SyncRun.id.desc())
        .limit(1)
    )
    if run is None:
        raise HTTPException(404, "no verification")
    return run


def _waiting_otp(db: Session, run: SyncRun) -> OtpRequest | None:
    return db.scalar(
        select(OtpRequest)
        .where(OtpRequest.sync_run_id == run.id, OtpRequest.status == "waiting")
        .order_by(OtpRequest.id.desc())
        .limit(1)
    )


def _stage(db: Session, run: SyncRun) -> tuple[str, OtpRequest | None]:
    """Derive the screen's stage; fail a stalled run (worker down, code never entered)."""
    if run.status == "success":
        return "success", None
    if run.status in ("failed", "otp_timeout"):
        return "failed", None
    now = datetime.now(UTC)
    otp = _waiting_otp(db, run) if run.status == "running" else None
    if otp and now < otp.expires_at:
        return "otp", otp
    stall = FETCH_STALL if run.progress == "fetch" else STALL
    if otp or now - (run.progress_at or run.created_at) > stall:
        kind = "otp_timeout" if otp else "timeout"
        run.status = "otp_timeout" if otp else "failed"
        run.failure_kind, run.finished_at = kind, now
        run.error = "OTP not entered in time" if otp else "VERIFY_TIMEOUT: no progress"
        if otp:
            otp.status = "expired"
        db.commit()
        return "failed", None
    if run.status == "requested":
        return "sending", None
    return ("verifying" if run.progress == "fetch" else "connecting"), None


@router.get("/credentials/{id}/verify")
def verify_status(id: int, db: DB) -> VerifyOut:
    c = get_or_404(db, Credential, id)
    run = _latest_verify(db, c)
    stage, otp = _stage(db, run)
    accounts = _accounts(c) if stage == "success" else []
    return VerifyOut(
        run_id=run.id,
        stage=stage,
        otp_expires_at=otp.expires_at if otp else None,
        failure_kind=run.failure_kind,
        error=run.error if stage == "failed" else None,
        accounts=accounts,
        credential=_out(c),
        prefill={k: v for k, v in decrypt_json(c.secret_enc).items() if v and not _secret(k)}
        if not c.verified
        else {},
    )


def _secret(field: str) -> bool:
    """Never sent back (same rule as the web's isSecretField)."""
    return "password" in field.lower() or "token" in field.lower()


@router.post("/credentials/{id}/verify")
def retry_verify(id: int, db: DB, me: Me) -> CredentialOut:
    c = get_or_404(db, Credential, id)
    if c.verified and c.pending_secret_enc is None:
        raise HTTPException(409, "nothing to verify")
    run_id = _start_verify(db, c, me)
    db.commit()
    return _out(c).model_copy(update={"verify_run_id": run_id})


@router.delete("/credentials/{id}/verify", status_code=204)
def cancel_verify(id: int, db: DB) -> None:
    """Unverified: delete it. Verified: drop the staged details, keep the connection."""
    c = get_or_404(db, Credential, id)
    _cancel_verify(db, c)
    if c.verified:
        c.pending_secret_enc = None
    else:
        db.delete(c)
    db.commit()


def _claim_otp_try(user_id: int) -> bool:
    now = time.monotonic()
    with _otp_lock:
        q = _otp_tries.setdefault(user_id, deque())
        while q and q[0] < now - OTP_WINDOW_S:
            q.popleft()
        if len(q) >= OTP_MAX:
            return False
        q.append(now)
        return True


@router.post("/credentials/{id}/verify/otp", status_code=204)
def verify_otp(id: int, body: OtpIn, db: DB, me: Me) -> None:
    if not OTP_RE.fullmatch(body.code):
        raise HTTPException(422, "code must be 4-8 digits")  # never echo the code back
    run = _latest_verify(db, get_or_404(db, Credential, id))
    if run.user_id != me.id:  # only whoever started this verify may answer it
        raise HTTPException(404, "no verification")
    if not _claim_otp_try(me.id):
        raise HTTPException(429, "too many attempts")
    otp = _waiting_otp(db, run)
    if otp is None:
        raise HTTPException(409, "not waiting for a code")
    try:
        answer_otp(db, otp.id, body.code)
    except ValueError:
        raise HTTPException(409, "not waiting for a code") from None
    db.execute(update(SyncRun).where(SyncRun.id == run.id).values(progress_at=datetime.now(UTC)))
    db.commit()
