import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from freerise.config import get_settings

# Tests cover login TOTP; a local .env may turn it off for dev.
os.environ["FREERISE_LOGIN_TOTP"] = "true"


@pytest.fixture(scope="session")
def db_engine():
    url = make_url(get_settings().test_database_url)
    # The fixture below drops the whole schema: never let it point at the real database.
    real = make_url(get_settings().database_url)
    if (url.host, url.port, url.database) == (real.host, real.port, real.database):
        pytest.exit("TEST_DATABASE_URL points at DATABASE_URL; refusing to wipe it", 2)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config("alembic.ini")
    cfg.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session(db_engine):
    conn = db_engine.connect()
    trans = conn.begin()
    s = Session(bind=conn, join_transaction_mode="create_savepoint")
    yield s
    s.close()
    trans.rollback()
    conn.close()
