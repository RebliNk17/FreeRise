import json
from datetime import date
from decimal import Decimal

from scraper import ScrapingResult
from scraper.models.account import AccountResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from sqlalchemy import func, select

from freerise.models import ClearingHouseReport, Credential, Fund, FundDeposit, FundSnapshot
from freerise.pension.ingest import ingest_mislaka


def deposit(d, amount):
    return Transaction(
        type=TransactionType.NORMAL,
        status=TransactionStatus.COMPLETED,
        date=d,
        processed_date=d,
        original_amount=amount,
        original_currency="ILS",
        charged_amount=amount,
        description="הפקדה - אקמי",
        identifier=f"p_{d}_{amount}",
    )


def policy(history, deposits=(), pid="123", ptype="hishtalmut"):
    last_date, last_bal = history[-1]
    return AccountResult(
        account_number=pid,
        transactions=list(deposits),
        balance=last_bal,
        balance_date=last_date,
        metadata={
            "policy_id": pid,
            "policy_type": ptype,
            "pension_type": None,
            "account_name": "קרן השתלמות",
            "investment_tracks": json.dumps([{"name": "כללי", "share": 1}], ensure_ascii=False),
            "commission_deposits_pct": None,
            "commission_savings_pct": "0.7",
            "liquidity_date": "2028-05-01",
            "details": json.dumps({"manufacturer": "מגדל"}, ensure_ascii=False),
            "balance_history": [{"date": d, "balance": b} for d, b in history],
        },
    )


def result(*accounts, reports=()):
    return ScrapingResult(
        success=True,
        accounts=list(accounts),
        extras={"clearing_house_reports": list(reports)},
    )


def cred(session):
    c = Credential(provider="mislaka", label="מסלקה", owner="shai", secret_enc=b"x")
    session.add(c)
    session.flush()
    return c


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_ingest_creates_funds_snapshots_deposits(session):
    c = cred(session)
    r = result(
        policy(
            [("2026-06-30", 100.0), ("2026-09-30", 250.5)],
            [deposit("2026-07-04", 50.0), deposit("2026-08-04", 50.0)],
        ),
        reports=[{"calc_date": "2026-09-30", "total_savings": 250.5}],
    )
    stats = ingest_mislaka(session, c.id, r)
    f = session.scalar(select(Fund))
    assert (f.policy_id, f.product_type, f.owner, f.company) == (
        "123",
        "hishtalmut",
        "shai",
        "מגדל",
    )
    assert f.liquidity_date == date(2028, 5, 1)
    assert f.fee_deposit_pct is None and f.fee_savings_pct == Decimal("0.7")
    assert f.tracks == [{"name": "כללי", "share": 1}]
    snaps = session.scalars(select(FundSnapshot).order_by(FundSnapshot.as_of)).all()
    assert [(s.as_of, s.balance) for s in snaps] == [
        (date(2026, 6, 30), Decimal("100.00")),
        (date(2026, 9, 30), Decimal("250.50")),
    ]
    assert count(session, FundDeposit) == 2
    rep = session.scalar(select(ClearingHouseReport))
    assert rep.report_month == date(2026, 9, 1) and rep.data["total_savings"] == 250.5
    assert (stats.funds, stats.snapshots, stats.deposits, stats.reports) == (1, 2, 2, 1)


def test_ingest_is_idempotent_and_keeps_history(session):
    c = cred(session)
    first = result(policy([("2026-03-31", 10.0), ("2026-06-30", 20.0)], [deposit("2026-04-04", 5)]))
    ingest_mislaka(session, c.id, first)
    ingest_mislaka(session, c.id, first)
    assert (count(session, Fund), count(session, FundSnapshot), count(session, FundDeposit)) == (
        1,
        2,
        1,
    )
    newer = result(policy([("2026-09-30", 30.0)], [deposit("2026-07-04", 5)]))
    stats = ingest_mislaka(session, c.id, newer)
    assert stats.snapshots == 1 and stats.deposits == 1
    assert count(session, FundSnapshot) == 3 and count(session, FundDeposit) == 2
