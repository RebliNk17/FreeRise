import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from freerise.crypto import decrypt_str, encrypt_str
from freerise.models import Invite, User, UserSession

_ph = PasswordHasher()
SESSION_TTL = timedelta(days=30)
INVITE_TTL = timedelta(days=7)


def hash_password(p: str) -> str:
    return _ph.hash(p)


def verify_password(h: str, p: str) -> bool:
    try:
        return _ph.verify(h, p)
    except VerifyMismatchError, InvalidHashError:
        return False


def new_totp_secret() -> str:
    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def verify_user_totp(user: User, code: str) -> bool:
    return user.totp_secret_enc is not None and verify_totp(decrypt_str(user.totp_secret_enc), code)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(session: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            token_hash=_hash_token(token),
            user_id=user_id,
            expires_at=datetime.now(UTC) + SESSION_TTL,
        )
    )
    session.flush()
    return token


def user_for_token(session: Session, token: str) -> User | None:
    return session.scalars(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.token_hash == _hash_token(token))
        .where(UserSession.expires_at > datetime.now(UTC))
    ).first()


def revoke(session: Session, token: str) -> None:
    session.execute(delete(UserSession).where(UserSession.token_hash == _hash_token(token)))
    session.flush()


def set_password(session: Session, user: User, password: str, keep_token: str) -> None:
    """New password; signs out the user's other sessions (keep_token's stays)."""
    user.password_hash = hash_password(password)
    session.execute(
        delete(UserSession)
        .where(UserSession.user_id == user.id)
        .where(UserSession.token_hash != _hash_token(keep_token))
    )
    session.flush()


def create_invite(session: Session, user_id: int) -> str:
    """A one-time join link token (expired ones are dropped). Only the hash is stored, so
    a token nobody sent can't be used."""
    now = datetime.now(UTC)
    session.execute(delete(Invite).where(Invite.expires_at <= now))
    token = secrets.token_urlsafe(32)
    session.add(
        Invite(token_hash=_hash_token(token), created_by=user_id, expires_at=now + INVITE_TTL)
    )
    session.flush()
    return token


def invite_for_token(session: Session, token: str) -> Invite | None:
    return session.scalars(
        select(Invite)
        .where(Invite.token_hash == _hash_token(token))
        .where(Invite.expires_at > datetime.now(UTC))
    ).first()


def claim_invite(session: Session, token: str) -> bool:
    """Spends a live invite; one DELETE, so two joins racing on a link can't both win."""
    spent = session.execute(
        delete(Invite)
        .where(Invite.token_hash == _hash_token(token))
        .where(Invite.expires_at > datetime.now(UTC))
        .returning(Invite.id)
    ).first()
    return spent is not None


def create_user(
    session: Session, username: str, password: str, name: str | None = None
) -> tuple[User, str]:
    secret = new_totp_secret()
    user = User(
        username=username,
        name=name,
        password_hash=hash_password(password),
        totp_secret_enc=encrypt_str(secret),
    )
    session.add(user)
    session.flush()
    return user, pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="FreeRise")
