import os
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from freerise.auth import user_for_token
from freerise.config import get_settings
from freerise.db import get_session
from freerise.models import User

# Cookies ignore ports, so a second local stack (demo) needs its own name.
COOKIE = os.environ.get("FREERISE_SESSION_COOKIE", "freerise_session")

DB = Annotated[Session, Depends(get_session)]


def current_user(db: DB, request: Request) -> User:
    token = request.cookies.get(COOKIE)
    user = user_for_token(db, token) if token else None
    if user is None:
        raise HTTPException(401, "not authenticated")
    return user


def get_or_404(db: Session, model, id: int):
    obj = db.get(model, id)
    if obj is None:
        raise HTTPException(404, "not found")
    return obj


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().tz)).date()
