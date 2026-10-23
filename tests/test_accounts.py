from freerise.accounts import account_label, account_labels
from freerise.models import Account, Credential


def _a(session, provider, kind, pid, label="ראשי", display=None):
    cred = Credential(provider=provider, label=label, owner="o", secret_enc=b"s")
    a = Account(
        credential=cred,
        provider_account_id=pid,
        kind=kind,
        display_name=display or f"{label} {pid[-4:]}",
    )
    session.add(a)
    session.flush()
    return a


def test_account_label(session):
    assert (
        account_label(_a(session, "isracard", "card", "4580-1234")) == "ישראכרט \u2066••1234\u2069"
    )
    assert (
        account_label(_a(session, "onezero", "bank", "125678"))
        == "עו״ש וואן זירו \u2066••5678\u2069"
    )
    assert account_label(_a(session, "visa cal", "card", "9999")) == "כאל \u2066••9999\u2069"
    assert (
        account_label(_a(session, "weird", "card", "1111", label="שלי")) == "שלי \u2066••1111\u2069"
    )
    renamed = _a(session, "max", "card", "2222", display="הכרטיס של שי")
    assert account_label(renamed) == "הכרטיס של שי"
    assert account_labels(session)[renamed.id] == "הכרטיס של שי"
    # credential renamed after the account was created: still the default name
    moved = _a(session, "max", "card", "3333", display="Max ישן 3333")
    assert account_label(moved) == "מקס \u2066••3333\u2069"


def test_active_card_ids(session):
    from datetime import UTC, date, datetime, timedelta

    from freerise.accounts import active_card_ids
    from freerise.models import Balance, Transaction

    used, stale, owing, idle, bank = (
        _a(session, "visa cal", "card", "1111"),
        _a(session, "visa cal", "card", "2222"),
        _a(session, "visa cal", "card", "3333"),
        _a(session, "visa cal", "card", "4444"),
        _a(session, "onezero", "bank", "5555"),
    )
    for a, days in ((used, 10), (stale, 400)):
        d = date.today() - timedelta(days=days)
        session.add(
            Transaction(
                account_id=a.id,
                txn_key=f"k{a.id}",
                date=d,
                processed_date=d,
                amount=-5,
                description="x",
                status="completed",
                raw={},
            )
        )
    session.add(Balance(account_id=owing.id, as_of=datetime.now(UTC), balance=-120))
    session.add(Balance(account_id=idle.id, as_of=datetime.now(UTC), balance=0))
    session.flush()
    assert active_card_ids(session, [used, stale, owing, idle, bank]) == {
        used.id,
        owing.id,
        bank.id,
    }
