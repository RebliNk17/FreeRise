import threading
import time
from collections import deque
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select

from freerise.api.deps import COOKIE, DB, current_user
from freerise.auth import SESSION_TTL, create_session, revoke, verify_password, verify_user_totp
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


class Me(BaseModel):
    id: int
    username: str


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
    token = create_session(db, user.id)
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
    return Me(id=user.id, username=user.username)
