from datetime import date
from decimal import Decimal

from freerise.models import Credential, Fund, FundDeposit, FundSnapshot
from freerise.pension.deposits import deposit_alerts, message


def mk(session, deposits, as_of=date(2026, 9, 30)):
    """deposits: (month, amount[, employer]) in 2026, deposited on the 10th."""
    c = Credential(provider="mislaka", label="m", owner="shai", secret_enc=b"x")
    session.add(c)
    session.flush()
    f = Fund(
        credential_id=c.id,
        policy_id="1",
        product_type="pension",
        name="פנסיה",
        owner="shai",
        company="מגדל",
    )
    session.add(f)
    session.flush()
    session.add(FundSnapshot(fund_id=f.id, as_of=as_of, balance=Decimal(1000)))
    for m, a, *e in deposits:
        raw = {"description": f"הפקדה - {e[0] if e else 'אקמה'}"}
        session.add(FundDeposit(fund_id=f.id, date=date(2026, m, 10), amount=Decimal(a), raw=raw))
    session.flush()


def kinds(session):
    return [(a.kind, a.month.month, a.employer) for a in deposit_alerts(session)]


def test_regular_deposits_no_alerts(session):
    mk(session, [(m, "4812.40") for m in range(1, 10)])
    assert kinds(session) == []


def test_missing_month(session):
    mk(session, [(m, "4812.40") for m in range(1, 10) if m != 5])
    [a] = deposit_alerts(session)
    assert (a.kind, a.month, a.amount, a.usual) == (
        "missing",
        date(2026, 5, 1),
        0,
        Decimal("4812.40"),
    )
    assert message(a) == (
        "הפקדה חסרה",
        "פנסיה (מגדל): לא הגיעה הפקדה מאקמה במאי 2026. בדרך כלל ₪4,812.40.",
    )


def test_last_month_missing_is_reported(session):
    mk(session, [(m, "1000") for m in range(1, 9)], as_of=date(2026, 10, 30))
    assert kinds(session) == [("missing", 9, "אקמה")]  # due 10.9, 45 days passed on 25.10


def test_within_45_days_is_not_missing(session):
    mk(session, [(m, "1000") for m in range(1, 9)], as_of=date(2026, 10, 20))
    assert kinds(session) == []  # September's was due 10.9: 40 days, still in time


def test_catch_up_within_45_days_is_fine(session):
    mk(session, [(m, "1000") for m in range(1, 10) if m not in (4, 5)] + [(5, "2000.50")])
    assert kinds(session) == []  # April's came with May's on 10.5: 30 days after 10.4


def test_catch_up_after_45_days_is_late(session):
    mk(session, [(m, "1000") for m in range(1, 10) if m not in (4, 5)])
    f = session.query(Fund).one()
    raw = {"description": "הפקדה - אקמה"}
    session.add(
        FundDeposit(fund_id=f.id, date=date(2026, 5, 28), amount=Decimal("2000.50"), raw=raw)
    )
    session.flush()
    [a] = deposit_alerts(session)
    assert (a.kind, a.month.month, a.amount, a.days_late) == ("late", 4, Decimal("2000.50"), 48)
    assert "48 ימים אחרי המועד" in message(a)[1]


def test_short_deposit(session):
    mk(session, [(m, "1000") for m in range(1, 7)] + [(7, "600.25"), (8, "1000"), (9, "1000")])
    assert kinds(session) == [("short", 7, "אקמה")]


def test_job_ended_and_new_employer(session):
    deps = [(m, "1000", "ישנה") for m in range(1, 5)] + [(m, "1200", "חדשה") for m in range(5, 10)]
    mk(session, deps)
    assert kinds(session) == []  # 5 empty months at the old employer: left, not missed


def test_month_not_due_yet(session):
    mk(session, [(m, "1000") for m in range(1, 10)], as_of=date(2026, 10, 12))
    assert kinds(session) == []  # October isn't due until the 20th


def test_transfers_ignored(session):
    mk(session, [(m, "1000") for m in range(1, 10)])
    f = session.query(Fund).one()
    session.add(
        FundDeposit(
            fund_id=f.id,
            date=date(2026, 3, 2),
            amount=Decimal(50000),
            raw={"description": "העברה - הראל"},
        )
    )
    session.flush()
    assert kinds(session) == []


def test_notifies_recent_months_once(session):
    from freerise.models import Notification
    from freerise.notify.rules import _pension_deposits

    mk(session, [(m, "1000") for m in range(1, 10) if m not in (2, 8)])
    _pension_deposits(session, date(2026, 10, 25))
    _pension_deposits(session, date(2026, 10, 26))
    [n] = session.query(Notification).all()  # February is too old to notify
    assert (n.kind, n.severity, n.link) == ("pension_deposit", "warning", "/pension")
    assert "באוגוסט 2026" in n.body


def test_early_deposit_is_not_missing(session):
    mk(session, [(m, "1571.20") for m in range(1, 10) if m != 4])
    f = session.query(Fund).one()
    raw = {"description": "הפקדה - אקמה"}
    session.add(
        FundDeposit(fund_id=f.id, date=date(2026, 3, 30), amount=Decimal("1571.20"), raw=raw)
    )
    session.flush()
    assert kinds(session) == []  # two in March, none in April


def test_salary_month_dates_lag_a_month(session):
    c = Credential(provider="migdal", label="m", owner="shai", secret_enc=b"x")
    session.add(c)
    session.flush()
    f = Fund(credential_id=c.id, policy_id="9", product_type="pension", name="פנסיה", owner="shai")
    session.add(f)
    session.flush()
    session.add(FundSnapshot(fund_id=f.id, as_of=date(2026, 10, 25), balance=Decimal(1000)))
    raw = {"description": "הפקדה - אקמה"}
    session.add_all(
        FundDeposit(fund_id=f.id, date=date(2026, m, 1), amount=Decimal(5646), raw=raw)
        for m in range(1, 10)
    )
    session.flush()
    assert kinds(session) == []  # September's salary is the newest due by 25.10


def test_raise_reported_once(session):
    mk(session, [(m, "5811") for m in range(1, 6)] + [(m, "6644") for m in range(6, 10)])
    [a] = deposit_alerts(session)
    assert (a.kind, a.month.month) == ("up", 6)
    title, body = message(a)
    assert title == "היי, ההפקדות לפנסיה עלו"
    assert "₪6,644.00" in body and "14.33%" in body and "₪5,811.00" in body


def test_lasting_cut_reported_once(session):
    mk(session, [(m, "1000") for m in range(1, 6)] + [(m, "600") for m in range(6, 10)])
    assert kinds(session) == [("short", 6, "אקמה")]


def test_salary_month_from_details(session):
    c = Credential(provider="migdal", label="m", owner="shai", secret_enc=b"x")
    session.add(c)
    session.flush()
    f = Fund(credential_id=c.id, policy_id="9", product_type="pension", name="פנסיה", owner="shai")
    session.add(f)
    session.flush()
    session.add(FundSnapshot(fund_id=f.id, as_of=date(2026, 10, 25), balance=Decimal(1000)))
    for m in range(2, 11):  # paid on the 5th of the next month; July's salary never came
        if m == 7:
            continue
        raw = {"description": "הפקדה - אקמה", "details": {"salary_month": f"2026-{m - 1:02d}"}}
        session.add(FundDeposit(fund_id=f.id, date=date(2026, m, 5), amount=Decimal(1000), raw=raw))
    session.flush()
    # deposit months would call it July; by salary month it's June
    assert kinds(session) == [("missing", 6, "אקמה")]
