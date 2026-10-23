from datetime import UTC, datetime, timedelta

import pyotp
from sqlalchemy import select

from freerise import auth
from freerise.crypto import decrypt_str
from freerise.models import User, UserSession


def test_password_roundtrip():
    assert auth.verify_password(auth.hash_password("pw1"), "pw1")


def test_wrong_password_rejected():
    assert not auth.verify_password(auth.hash_password("pw1"), "nope")


def test_totp_current_code_ok():
    s = auth.new_totp_secret()
    assert auth.verify_totp(s, pyotp.TOTP(s).now())


def test_totp_stale_code_rejected():
    s = auth.new_totp_secret()
    stale = pyotp.TOTP(s).at(datetime.now(UTC) - timedelta(minutes=10))
    assert not auth.verify_totp(s, stale)


def _user(session):
    u = User(username="u", password_hash=auth.hash_password("x"))
    session.add(u)
    session.flush()
    return u


def test_session_lookup_and_expiry(session):
    u = _user(session)
    tok = auth.create_session(session, u.id)
    assert auth.user_for_token(session, tok).id == u.id
    assert auth.user_for_token(session, "bogus") is None
    row = session.scalars(select(UserSession)).one()
    assert row.token_hash != tok
    assert timedelta(days=29) < row.expires_at - datetime.now(UTC) <= timedelta(days=30)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.flush()
    assert auth.user_for_token(session, tok) is None


def test_revoked_session_invalid(session):
    u = _user(session)
    tok = auth.create_session(session, u.id)
    auth.revoke(session, tok)
    assert auth.user_for_token(session, tok) is None


def test_create_user_stores_hash_and_encrypted_totp(session):
    u, uri = auth.create_user(session, "shai", "secret-pw")
    assert u.password_hash != "secret-pw" and auth.verify_password(u.password_hash, "secret-pw")
    secret = decrypt_str(u.totp_secret_enc)
    assert secret in uri and "issuer=FreeRise" in uri and uri.startswith("otpauth://totp/")
    assert auth.verify_user_totp(u, pyotp.TOTP(secret).now())
