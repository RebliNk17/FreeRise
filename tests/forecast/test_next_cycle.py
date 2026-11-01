from datetime import date
from decimal import Decimal

from sqlalchemy import select

from freerise.cashflow.cycles import cycle_by_label
from freerise.forecast.next_cycle import (
    CADENCE_MONTHS,
    add_months,
    expected_in_cycle,
    installments_ending,
    next_cycle_forecast,
    same_quarter_month,
)
from freerise.forecast.recurring import detect_recurring
from freerise.models import (
    Account,
    Category,
    Credential,
    RecurringItem,
    RecurringSkip,
    Transaction,
)

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
            last_date=add_months(next_date, -CADENCE_MONTHS[cadence]),
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


def test_unconfirmed_charge_in_a_fixed_category_is_expected(session):
    cat = {c.name: c.id for c in session.scalars(select(Category))}
    _item(session, "electric", "monthly", "390", date(2026, 11, 2), status="pending")
    _item(session, "cafe", "monthly", "40", date(2026, 11, 2), status="pending")
    _item(session, "loose", "monthly", "50", date(2026, 11, 2), status="pending")
    for key, name in (("electric", "חשמל"), ("cafe", "אוכל בחוץ")):
        session.query(RecurringItem).filter_by(merchant_key=key).one().category_id = cat[name]
    labels = [x.label for x in expected_in_cycle(session, OCT, TODAY).fixed_items]
    assert labels == ["electric"]  # a variable category or none still needs confirming


def test_this_cycles_amount_or_skip_from_the_user(session):
    _item(session, "gym", "monthly", "250", date(2026, 10, 18))
    rid = session.query(RecurringItem).filter_by(merchant_key="gym").one().id
    session.add(RecurringSkip(recurring_id=rid, cycle_start=OCT.start, amount=Decimal(300)))
    session.flush()
    [line] = expected_in_cycle(session, OCT, TODAY).fixed_items
    assert (line.amount, line.expected_amount, line.overridden) == (300, 300, True)
    [line] = expected_in_cycle(session, NOV, TODAY).fixed_items  # next cycle: back to 250
    assert (line.amount, line.overridden) == (250, False)
    session.query(RecurringSkip).one().amount = None  # "won't happen this month"
    assert expected_in_cycle(session, OCT, TODAY).fixed_items == []


def test_same_quarter_month_salary():
    # Paid at the end of the month (or the 1st-2nd of the next): higher every Jan/Apr/Jul/Oct.
    pay = [
        (date(2026, 2, 2), 39731),  # January's
        (date(2026, 2, 26), 29638),
        (date(2026, 3, 30), 68512),  # a bonus: the median ignores it
        (date(2026, 4, 30), 33644),
        (date(2026, 5, 31), 30558),
        (date(2026, 6, 30), 32069),
        (date(2026, 8, 2), 33814),  # July's
        (date(2026, 9, 1), 32009),
        (date(2026, 10, 1), 33408),
    ]
    occ = [(d, Decimal(a)) for d, a in pay]
    assert same_quarter_month(occ, date(2026, 11, 1)) == Decimal(33814)  # October's
    assert same_quarter_month(occ, date(2026, 10, 28)) == Decimal(33814)
    assert same_quarter_month(occ, date(2026, 11, 30)) == Decimal(30558)  # November's
    assert same_quarter_month(occ[:2], date(2026, 11, 1)) is None  # too little history


def test_user_set_expense_amount_keeps_following_the_charges(session):
    a = _acct(session)
    for m in (6, 7, 8, 9):
        _tx(session, a, date(2026, m, 28), -968, "insurance")
    [it] = [
        r for r in detect_recurring(session, date(2026, 9, 29)) if r.merchant_key == "insurance"
    ]
    it.expected_amount, it.amount_kind, it.user_defined = Decimal(1000), "fixed", True
    _tx(session, a, date(2026, 10, 28), -968, "insurance")
    detect_recurring(session, date(2026, 11, 20))
    assert it.next_expected_date > date(2026, 11, 20)  # dates move on; the amount is the user's
    [line] = expected_in_cycle(session, NOV, date(2026, 11, 20)).fixed_items
    assert (line.amount, line.date) == (1000, date(2026, 11, 28))


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


def test_late_charge_stays_in_its_cycle(session):
    # Charged 28.9; the 28.10 charge is late (or not synced yet), and detection already rolled
    # next_expected_date past today to 27.11. October must still expect it.
    _item(session, "insurance", "monthly", "968", date(2026, 11, 27))
    session.query(RecurringItem).filter_by(merchant_key="insurance").one().last_date = date(
        2026, 9, 28
    )
    [line] = expected_in_cycle(session, OCT, date(2026, 11, 1)).fixed_items
    assert (line.date, line.amount, line.charged) == (date(2026, 10, 28), Decimal(968), False)
    assert expected_in_cycle(session, NOV, date(2026, 11, 1)).fixed_items[0].date == date(
        2026, 11, 28
    )


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
