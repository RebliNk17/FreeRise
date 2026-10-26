import threading
import time
from collections import deque
from typing import Annotated

import segno
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.api.deps import COOKIE, DB, current_user, get_or_404
from freerise.auth import (
    SESSION_TTL,
    claim_invite,
    create_invite,
    create_session,
    create_user,
    invite_for_token,
    revoke,
    set_password,
    verify_password,
    verify_user_totp,
)
from freerise.config import get_settings
from freerise.models import User

router = APIRouter(prefix="/auth")

MAX_FAILURES, WINDOW_S = 5, 15 * 60
# ponytail: in-memory per-username sliding window; fine for one process, move to DB/Redis if
# the API ever runs multiple workers/replicas.
_failures: dict[str, deque[float]] = {}
_lock = threading.Lock()


def _claim_attempt(username: str) -> bool:
    """Prune old entries, then record a provisional failure for `username` before the
    (slow) password check so concurrent guesses can't all slip under the limit.
    Returns False when the limit is already reached."""
    now = time.monotonic()
    with _lock:
        for k in list(_failures):  # also drops idle usernames so the dict stays bounded
            q = _failures[k]
            while q and q[0] < now - WINDOW_S:
                q.popleft()
            if not q:
                del _failures[k]
        fails = _failures.setdefault(username, deque())
        if len(fails) >= MAX_FAILURES:
            return False
        fails.append(now)
        return True


class Login(BaseModel):
    username: str
    password: str
    totp: str = ""


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class Me(BaseModel):
    id: int
    username: str
    name: str  # what the app shows; the username until they pick one

    @classmethod
    def of(cls, u: User) -> Me:
        return cls(id=u.id, username=u.username, name=u.name or u.username)


class NewName(BaseModel):
    name: Name


class NewPassword(BaseModel):
    current: str
    new: str = Field(min_length=8, max_length=200)


class Confirm(BaseModel):
    current: str  # the caller's own password


class Joining(BaseModel):
    token: str
    username: str = Field(min_length=1, max_length=50, pattern=r"^\S+$")
    password: str = Field(min_length=8, max_length=200)
    name: Name | None = None


class TotpSetup(BaseModel):
    otpauth: str  # shown once: the new member's authenticator setup
    qr: str  # otpauth as an SVG data URI


class Code(BaseModel):
    code: str


def totp_required() -> bool:
    s = get_settings()
    return s.login_totp or s.env == "production"


@router.get("/config")
def auth_config() -> dict[str, bool]:
    return {"totp": totp_required()}


@router.post("/login", status_code=204)
def login(body: Login, db: DB, response: Response) -> None:
    if not _claim_attempt(body.username):
        raise HTTPException(429, "too many attempts")
    user = db.scalars(select(User).where(User.username == body.username)).first()
    if not (
        user
        and verify_password(user.password_hash, body.password)
        and (not totp_required() or verify_user_totp(user, body.totp))
    ):
        raise HTTPException(401, "invalid credentials")  # provisional failure stays
    with _lock:
        _failures.pop(body.username, None)
    _start_session(db, user.id, response)


def _start_session(db: Session, user_id: int, response: Response) -> None:
    token = create_session(db, user_id)
    db.commit()
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
        httponly=True,
        samesite="lax",
        secure=get_settings().env == "production",
    )


@router.post("/logout", status_code=204, dependencies=[Depends(current_user)])
def logout(db: DB, request: Request, response: Response) -> None:
    revoke(db, request.cookies.get(COOKIE, ""))
    db.commit()
    response.delete_cookie(COOKIE, path="/")


@router.get("/me")
def me(user: Annotated[User, Depends(current_user)]) -> Me:
    return Me.of(user)


@router.patch("/me")
def rename(body: NewName, db: DB, user: Annotated[User, Depends(current_user)]) -> Me:
    """Your own display name only; the login username never changes."""
    user.name = body.name
    db.commit()
    return Me.of(user)


@router.post("/password", status_code=204)
def change_password(
    body: NewPassword, db: DB, request: Request, user: Annotated[User, Depends(current_user)]
) -> None:
    _require_password(user, body.current)
    set_password(db, user, body.new, keep_token=request.cookies.get(COOKIE, ""))
    db.commit()


def _require_password(user: User, password: str) -> None:
    """Account changes need the caller's password, so a stolen session alone can't lock anyone
    out. Wrong guesses count toward the login limit; 403, not 401, so the app doesn't log out."""
    if not _claim_attempt(user.username):
        raise HTTPException(429, "too many attempts")
    if not verify_password(user.password_hash, password):
        raise HTTPException(403, "wrong password")  # provisional failure stays
    with _lock:
        _failures.pop(user.username, None)


# Household members: every login sees and does everything; the data isn't per user.
@router.get("/users", dependencies=[Depends(current_user)])
def members(db: DB) -> list[Me]:
    return [Me.of(u) for u in db.scalars(select(User).order_by(User.id))]


@router.post("/invites", status_code=201)
def invite(db: DB, user: Annotated[User, Depends(current_user)]) -> dict[str, str]:
    token = create_invite(db, user.id)
    db.commit()
    return {"token": token}


@router.get("/invites/{token}")
def invite_info(token: str, db: DB) -> dict[str, str]:
    inv = invite_for_token(db, token)
    if inv is None:
        raise HTTPException(404, "invite expired or used")
    return {"invited_by": Me.of(db.get(User, inv.created_by)).name}


@router.post("/join", status_code=201)
def join(body: Joining, db: DB, response: Response) -> TotpSetup:
    """Open to whoever holds a live invite: it makes one login, signs it in, and is spent."""
    if db.scalars(select(User).where(User.username == body.username)).first():
        raise HTTPException(409, "username taken")
    if not claim_invite(db, body.token):
        raise HTTPException(404, "invite expired or used")
    member, uri = create_user(db, body.username, body.password, body.name)
    _start_session(db, member.id, response)
    qr = segno.make(uri).svg_data_uri(scale=5, border=2, light="white")  # scannable in dark mode
    return TotpSetup(otpauth=uri, qr=qr)


@router.post("/totp/check", status_code=204)
def check_totp(body: Code, user: Annotated[User, Depends(current_user)]) -> None:
    """A new member confirms their authenticator works before they need it to log in."""
    if not verify_user_totp(user, body.code):
        raise HTTPException(400, "wrong code")


@router.delete("/users/{user_id}", status_code=204)
def remove_member(
    user_id: int, body: Confirm, db: DB, user: Annotated[User, Depends(current_user)]
) -> None:
    """Not yourself, so the household always keeps a login. Their sessions go with them."""
    if user_id == user.id:
        raise HTTPException(400, "can't remove yourself")
    _require_password(user, body.current)
    db.delete(get_or_404(db, User, user_id))
    db.commit()
