from datetime import date, timedelta
from decimal import Decimal

from freerise.health import data_health
from freerise.models import Account, Credential, Transaction


def _acct(session, kind, pid):
    cred = Credential(provider="max", label="l", owner="o", secret_enc=b"s", verified=True)
    a = Account(credential=cred, provider_account_id=pid, kind=kind, display_name=pid)
    session.add(a)
    session.flush()
    return a


def _tx(session, a, d):
    session.add(
        Transaction(
            account_id=a.id,
            txn_key=f"t{a.id}{d}",
            date=d,
            processed_date=d,
            amount=Decimal(-10),
            description="m",
            merchant_key="m",
            status="completed",
            raw={},
        )
    )
    session.flush()


def test_idle_skips_dead_cards_but_flags_quiet_ones(session):
    today = date.today()
    dead = _acct(session, "card", "dead")  # nothing for a year: expired, not a problem
    _tx(session, dead, today - timedelta(days=365))
    quiet = _acct(session, "card", "quiet")  # used 4 months ago, silent since: worth a look
    _tx(session, quiet, today - timedelta(days=120))
    bank = _acct(session, "bank", "bank")  # banks always count
    h = data_health(session, today)
    assert {a.id for a in h.idle_accounts} == {quiet.id, bank.id}
