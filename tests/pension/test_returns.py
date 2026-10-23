from datetime import date
from decimal import Decimal

from freerise.models import Credential, Fund, FundDeposit, FundSnapshot
from freerise.pension.returns import fund_yearly, funds_overview


def mk_fund(session, snaps, deposits=(), pid="1"):
    c = Credential(provider="mislaka", label="m", owner="shai", secret_enc=b"x")
    session.add(c)
    session.flush()
    f = Fund(credential_id=c.id, policy_id=pid, product_type="pension", name="פנסיה", owner="shai")
    session.add(f)
    session.flush()
    session.add_all(FundSnapshot(fund_id=f.id, as_of=d, balance=Decimal(b)) for d, b in snaps)
    session.add_all(FundDeposit(fund_id=f.id, date=d, amount=Decimal(a)) for d, a in deposits)
    session.flush()
    return f


def test_modified_dietz(session):
    deps = [(date(2026, m, 4), "1571.2") for m in range(1, 9)] + [(date(2026, 9, 6), "1571.2")]
    end = 20817 + 9 * Decimal("1571.2") + 2629
    f = mk_fund(session, [(date(2026, 1, 1), "20817"), (date(2026, 9, 30), end)], deps)
    [row] = fund_yearly(session, f.id)
    assert row.year == 2026 and row.profit == Decimal("2629.00")
    assert row.deposits == Decimal("14140.80")
    assert abs(float(row.return_pct) - 0.092) < 0.001


def test_no_deposit_return_equals_simple(session):
    f = mk_fund(session, [(date(2025, 12, 31), "104284"), (date(2026, 12, 31), "115375")])
    rows = fund_yearly(session, f.id)
    assert [r.year for r in rows] == [2026]  # 2025 has only its start snapshot
    assert abs(float(rows[0].return_pct) - 0.1064) < 0.001


def test_funds_overview_ytd_monthly_and_total(session):
    f = mk_fund(
        session,
        [
            (date(2025, 12, 31), "1000"),
            (date(2026, 1, 15), "1010"),
            (date(2026, 1, 31), "1020"),
            (date(2026, 2, 28), "1100"),
        ],
        [(date(2026, 2, 10), "50")],
    )
    mk_fund(session, [(date(2026, 2, 28), "500")], pid="2")
    ov = funds_overview(session)
    assert ov.total == Decimal("1600.00")
    mine = next(o for o in ov.funds if o.fund.id == f.id)
    assert (mine.latest_balance, mine.as_of) == (Decimal("1100.00"), date(2026, 2, 28))
    assert mine.ytd_profit == Decimal("50.00")
    assert mine.monthly == [
        (date(2025, 12, 31), Decimal("1000.00")),
        (date(2026, 1, 31), Decimal("1020.00")),
        (date(2026, 2, 28), Decimal("1100.00")),
    ]
