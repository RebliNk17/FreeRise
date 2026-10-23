from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from freerise.categorize.normalize import normalize_merchant
from freerise.models import Account, Category, Credential, Transaction


@pytest.fixture
def cat(session):
    def get(name):
        c = session.scalar(select(Category).where(Category.name == name))
        if c is None:
            c = Category(name=name, group="variable")
            session.add(c)
            session.flush()
        return c

    return get


@pytest.fixture
def mk_txn(session):
    cred = Credential(provider="max", label="m", owner="s", secret_enc=b"x")
    session.add(cred)
    session.flush()
    acct = Account(credential_id=cred.id, provider_account_id="1", kind="card", display_name="c")
    session.add(acct)
    session.flush()
    n = [0]

    def make(description, amount="-10", **kw):
        n[0] += 1
        t = Transaction(
            account_id=acct.id,
            txn_key=f"k{n[0]}",
            date=date(2026, 10, 1),
            processed_date=date(2026, 10, 1),
            raw={},
            amount=Decimal(amount),
            description=description,
            status="completed",
            merchant_key=normalize_merchant(description),
            **kw,
        )
        session.add(t)
        session.flush()
        return t

    return make
