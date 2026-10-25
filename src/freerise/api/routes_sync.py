from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from scraper import PROVIDER_CONFIGS
from sqlalchemy import select

from freerise.api.deps import DB, get_or_404
from freerise.models import Credential, OtpRequest, SyncRun
from freerise.sync.otp import answer_otp
from freerise.sync.service import active_run_id

router = APIRouter(prefix="/sync")


class SyncIn(BaseModel):
    credential_id: int | None = None


class RunRef(BaseModel):
    credential_id: int
    run_id: int
    already_running: bool  # the connection had a sync going; this request joined it


class SyncOut(BaseModel):
    run_ids: list[int]  # the syncs this request started
    runs: list[RunRef] = []  # every connection asked, started or already running


class RunOut(BaseModel):
    id: int
    credential_id: int
    credential_label: str
    provider: str
    trigger: str
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    failure_kind: str | None
    added: int
    updated: int


class OtpOut(BaseModel):
    id: int
    sync_run_id: int
    credential_label: str
    provider: str
    expires_at: datetime


class OtpAnswer(BaseModel):
    code: str


@router.post("")
def request_sync(body: SyncIn, db: DB) -> SyncOut:
    if body.credential_id is not None:
        creds = [get_or_404(db, Credential, body.credential_id)]
        if not creds[0].enabled or not creds[0].verified:
            raise HTTPException(409, "credential disabled")
    else:
        creds = [
            c
            for c in db.scalars(
                select(Credential)
                .where(Credential.enabled, Credential.verified)
                .order_by(Credential.id)
            )
            if PROVIDER_CONFIGS[c.provider].service != "insurances"
        ]
    busy = {c.id: active_run_id(db, c.id) for c in creds}
    # One sync per connection at a time: a second click joins the one already going.
    new = [
        SyncRun(credential_id=c.id, trigger="manual", status="requested")
        for c in creds
        if busy[c.id] is None
    ]
    db.add_all(new)
    db.commit()
    started = {r.credential_id: r.id for r in new}
    return SyncOut(
        run_ids=[r.id for r in new],
        runs=[
            RunRef(
                credential_id=c.id,
                run_id=busy[c.id] or started[c.id],
                already_running=bool(busy[c.id]),
            )
            for c in creds
        ],
    )


@router.get("/runs")
def list_runs(db: DB, limit: Annotated[int, Query(ge=1, le=200)] = 20) -> list[RunOut]:
    rows = db.execute(
        select(SyncRun, Credential.label, Credential.provider)
        .join(Credential)
        .where(SyncRun.trigger != "verify")  # those live on the connecting screen
        .order_by(SyncRun.id.desc())
        .limit(limit)
    )
    return [
        RunOut(
            credential_label=label,
            provider=provider,
            **{
                f: getattr(r, f)
                for f in RunOut.model_fields
                if f not in ("credential_label", "provider")
            },
        )
        for r, label, provider in rows
    ]


@router.get("/otp")
def waiting_otp(db: DB) -> list[OtpOut]:
    rows = db.execute(
        select(OtpRequest, Credential.label, Credential.provider)
        .join(SyncRun, SyncRun.id == OtpRequest.sync_run_id)
        .join(Credential, Credential.id == SyncRun.credential_id)
        .where(OtpRequest.status == "waiting", OtpRequest.expires_at > datetime.now(UTC))
        .where(SyncRun.trigger != "verify")  # answered on the connecting screen, by its user
        .order_by(OtpRequest.id)
    )
    return [
        OtpOut(
            id=o.id,
            sync_run_id=o.sync_run_id,
            credential_label=label,
            provider=provider,
            expires_at=o.expires_at,
        )
        for o, label, provider in rows
    ]


@router.post("/otp/{id}", status_code=204)
def submit_otp(id: int, body: OtpAnswer, db: DB) -> None:
    otp = db.get(OtpRequest, id)
    if otp and db.get(SyncRun, otp.sync_run_id).trigger == "verify":
        raise HTTPException(400, "OTP request is not waiting")  # see /credentials/{id}/verify/otp
    try:
        answer_otp(db, id, body.code)
    except ValueError:
        raise HTTPException(400, "OTP request is not waiting") from None
