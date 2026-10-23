import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from freerise.api import routes_auth
from freerise.api.main import app
from freerise.auth import create_user
from freerise.crypto import decrypt_str
from freerise.db import get_session
from freerise.models import Base

SEEDED = {"categories", "settings", "merchant_rules"}  # populated by migrations 0002/0007


@pytest.fixture
def sf(db_engine):
    yield sessionmaker(db_engine, expire_on_commit=False)
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables if t.name not in SEEDED)
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        conn.execute(
            text("DELETE FROM merchant_rules WHERE NOT (source = 'seed' AND match = 'contains')")
        )


@pytest.fixture
def client(sf):
    def _session():
        with sf() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    routes_auth._failures.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def user(sf):
    with sf() as s:
        u, _ = create_user(s, "shai", "pw-123456")
        s.commit()
        secret = decrypt_str(u.totp_secret_enc)
        return {"username": "shai", "password": "pw-123456", "totp": pyotp.TOTP(secret).now}


@pytest.fixture
def authed(client, user):
    r = client.post(
        "/api/auth/login",
        json={"username": user["username"], "password": user["password"], "totp": user["totp"]()},
    )
    assert r.status_code == 204
    return client
