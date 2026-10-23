from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from freerise.models import Account, Credential, Transaction

TABLES = {
    "users",
    "user_sessions",
    "credentials",
    "accounts",
    "transactions",
    "balances",
    "sync_runs",
    "otp_requests",
    "recurring_items",
}


def test_migration_creates_tables(db_engine):
    assert TABLES <= set(inspect(db_engine).get_table_names())


def test_txn_unique_per_account(session):
    cred = Credential(provider="x", label="l", owner="o", secret_enc=b"s")
    acct = Account(credential=cred, provider_account_id="1", kind="bank", display_name="a")
    session.add(acct)
    session.flush()

    def txn():
        return Transaction(
            account_id=acct.id,
            txn_key="k",
            date=date(2026, 1, 1),
            processed_date=date(2026, 1, 1),
            amount=Decimal("1.00"),
            description="d",
            status="completed",
            raw={},
        )

    session.add(txn())
    session.flush()
    session.add(txn())
    with pytest.raises(IntegrityError):
        session.flush()


def test_default_categories_seeded(session):
    from sqlalchemy import select

    from freerise.models import Category

    g = {c.name: c.group for c in session.scalars(select(Category))}
    assert g["כלכלה"] == "variable"
    assert g["חיוב כרטיס אשראי"] == "card_bill"
