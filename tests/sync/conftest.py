import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from freerise.categorize.default_rules import apply_defaults
from freerise.crypto import encrypt_json
from freerise.models import Base, Credential

SEEDED = {"categories", "settings", "merchant_rules"}  # populated by migrations 0002/0007/0021


@pytest.fixture
def sf(db_engine):
    """Real-commit sessionmaker on the test DB (sync code uses its own sessions)."""
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
def credential(sf):
    with sf() as s:
        c = Credential(
            provider="max",
            label="Max",
            owner="shai",
            secret_enc=encrypt_json({"username": "u", "password": "p"}),
        )
        s.add(c)
        s.commit()
        return c
