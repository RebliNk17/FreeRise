from datetime import date
from decimal import Decimal

from freerise.cashflow.cycles import cycle_by_label
from freerise.forecast.next_cycle import expected_in_cycle, installments_ending, next_cycle_forecast
from freerise.models import Account, Credential, RecurringItem, Transaction

TODAY = date(2026, 10, 23)  # current cycle 10.10-9.11
OCT, NOV = cycle_by_label(2026, 10, 10), cycle_by_label(2026, 11, 10)
_n = 0


def _acct(session):
    cred = Credential(provider="max", label="l", owner="o", secret_enc=b"s")
    a = Account(credential=cred, provider_account_id="1", kind="card", display_name="c")
    session.add(a)
    session.flush()
    return a


def _tx(session, a, d, amount, key, n=None, total=None):
    global _n
    _n += 1
    session.add(
        Transaction(
            account_id=a.id,
            txn_key=f"nc{_n}",
            date=d,
            processed_date=d,
            amount=Decimal(str(amount)),
            description=key,
            merchant_key=key,
            installment_number=n,
            installment_total=total,
            status="completed",
            raw={},
        )
    )
    session.flush()


def _item(session, key, cadence, amount, next_date, direction="expense", status="confirmed"):
    session.add(
        RecurringItem(
            merchant_key=key,
            direction=direction,
            label=key,
            cadence=cadence,
            amount_kind="fixed",
            expected_amount=Decimal(amount),
            last_date=next_date,
            next_expected_date=next_date,
            status=status,
            basis=f"{key} basis",
        )
    )
    session.flush()


def test_bimonthly_lands_alternate_cycles(session):
    _item(session, "ארנונה", "bimonthly", "600", date(2026, 11, 15))
    _item(session, "pending", "monthly", "50", date(2026, 11, 15), status="pending")
    totals = []
    for m, y in ((11, 2026), (12, 2026), (1, 2027), (2, 2027)):
        ec = expected_in_cycle(session, cycle_by_label(y, m, 10), TODAY)
        totals.append(ec.fixed_total)
    assert totals == [Decimal(600), Decimal(0), Decimal(600), Decimal(0)]
    line = expected_in_cycle(session, NOV, TODAY).fixed_items[0]
    assert (line.source, line.charged, line.basis) == ("recurring", False, "ארנונה basis")


def test_recurring_already_charged_uses_actual(session):
    a = _acct(session)
    _item(session, "netflix", "monthly", "50", date(2026, 11, 5))
    _tx(session, a, date(2026, 10, 12), -55, "netflix")
    [line] = expected_in_cycle(session, OCT, TODAY).fixed_items
    assert (line.charged, line.amount) == (True, Decimal(55))


def test_installments_ending_sum(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 15), -120, "tv", 3, 3)
    _tx(session, a, date(2026, 10, 20), -200, "sofa", 12, 12)
    _tx(session, a, date(2026, 10, 20), -80, "phone", 2, 6)
    _tx(session, a, date(2026, 9, 20), -999, "old", 6, 6)
    lines = installments_ending(session, OCT)
    assert sum(x.amount for x in lines) == Decimal(320)
    assert all(x.basis for x in lines)


def test_installment_projection_into_next_cycle(session):
    a = _acct(session)
    _tx(session, a, date(2026, 9, 15), -100, "laptop", 2, 6)
    _tx(session, a, date(2026, 10, 15), -100.5, "laptop", 3, 6)  # same series (±1)
    _tx(session, a, date(2026, 10, 16), -300, "bed", 4, 4)  # ends now
    nov = expected_in_cycle(session, NOV, TODAY)
    [line] = nov.fixed_items
    assert (line.source, line.amount, line.date) == (
        "installment",
        Decimal("100.5"),
        date(2026, 11, 15),
    )
    assert "4" in line.basis and "6" in line.basis
    f = next_cycle_forecast(session, TODAY)
    assert f.cycle == NOV
    assert f.installments_stopping_total == Decimal(300)
    assert f.fixed_total == Decimal("100.5")
    # current cycle: laptop 100.5 + bed 300 charged
    assert f.delta_fixed_vs_current == Decimal("100.5") - Decimal("400.5")


def test_stale_confirmed_item_not_projected(session):
    _item(session, "gym", "monthly", "200", date(2026, 10, 1))  # stopped: > 7 days before TODAY
    _item(session, "late", "monthly", "70", date(2026, 10, 18))  # within 7 days: still expected
    ec = expected_in_cycle(session, OCT, TODAY)
    assert [x.label for x in ec.fixed_items] == ["late"]
    assert expected_in_cycle(session, NOV, TODAY).fixed_total == Decimal(70)


def test_lines_carry_account_labels(session):
    from freerise.accounts import account_label

    old, new = _acct(session), _acct(session)
    _item(session, "gym", "monthly", "200", date(2026, 11, 15))
    item = session.query(RecurringItem).filter_by(merchant_key="gym").one()
    item.account_id, item.previous_account_id = new.id, old.id
    item.account_changed_on = date(2026, 10, 1)
    _tx(session, old, date(2026, 9, 15), -300, "ikea", 4, 6)
    session.flush()
    lines = {x.label: x for x in expected_in_cycle(session, NOV, TODAY).fixed_items}
    assert lines["gym"].account_id == new.id
    assert lines["gym"].account_label == account_label(new)
    assert lines["gym"].previous_account_label == account_label(old)
    assert lines["ikea"].account_label == account_label(old)
    assert lines["ikea"].previous_account_label is None
    item.account_changed_on = date(2026, 7, 1)  # switched long ago: no note
    assert expected_in_cycle(session, NOV, TODAY).fixed_items[0].previous_account_label is None


def test_lines_sorted_by_date(session):
    a = _acct(session)
    _item(session, "late-month", "monthly", "10", date(2026, 12, 3))
    _item(session, "early", "monthly", "10", date(2026, 11, 12))
    _tx(session, a, date(2026, 10, 11), -100, "laptop", 2, 6)  # projected 11.11
    labels = [x.label for x in expected_in_cycle(session, NOV, TODAY).fixed_items]
    assert labels == ["laptop", "early", "late-month"]
