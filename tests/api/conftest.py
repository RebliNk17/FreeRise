import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import sessionmaker

from freerise.api import routes_auth
from freerise.api.main import app
from freerise.auth import create_user
from freerise.categorize.default_rules import apply_defaults
from freerise.crypto import decrypt_str
from freerise.db import get_session
from freerise.models import Base, Setting

SEEDED = {"categories", "settings", "merchant_rules"}  # populated by migrations 0002/0007/0021


@pytest.fixture
def sf(db_engine):
    yield sessionmaker(db_engine, expire_on_commit=False)
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables if t.name not in SEEDED)
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        conn.execute(
            text(
                "DELETE FROM merchant_rules "
                "WHERE NOT (source IN ('seed', 'default') AND match = 'contains')"
            )
        )
        apply_defaults(conn)  # restore any default rule a test deleted or re-pointed


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


@pytest.fixture
def restore_settings(sf):
    """settings survives the per-test truncate (seeded); put it back as it was."""
    with sf() as s:
        saved = {x.key: x.value for x in s.scalars(select(Setting))}
    yield
    with sf() as s:
        s.execute(delete(Setting).where(Setting.key.not_in(saved)))
        for k, v in saved.items():
            s.execute(update(Setting).where(Setting.key == k).values(value=v))
        s.commit()
