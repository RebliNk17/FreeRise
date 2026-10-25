import json
from decimal import Decimal

from israeli_finance_scrapers.models.pension import (
    DepositTransaction,
    FundPolicy,
    InsuranceCover,
    ProductType,
    YearlyMovementSummary,
)
from scraper import ScrapingResult

from freerise.models import Credential, Fund, FundDeposit
from freerise.pension.ingest import ingest_mislaka
from freerise.sync.ips import IpsScraper


def policy(**kw):
    dep = DepositTransaction(
        identifier="d1",
        date="2026-09-01",
        total_amount=6644.0,
        salary_month="2026-08",
        employer_name="אקמה",
        employee_amount=2214.67,
        employer_amount=4429.33,
        insured_salary=21540.0,
    )
    return FundPolicy(
        policy_id="p1",
        raw_policy_id="p1",
        product_type=ProductType.PENSION,
        name="פנסיה משלימה",
        manufacturer="מגדל",
        balance=429860.0,
        balance_date="2026-10-25",
        deposits=[dep],
        yearly_movements=[
            YearlyMovementSummary(
                year="2025",
                deposits=70800.0,
                gains=41207.13,
                management_fees=812.4,
                insurance_costs=1154.0,
            )
        ],
        insurance_covers=[InsuranceCover(title="נכות", monthly_cost=96.15)],
        **kw,
    )


def test_details_reach_fund_and_deposit(session):
    c = Credential(provider="migdal", label="m", owner="shai", secret_enc=b"x")
    session.add(c)
    session.flush()
    acct = IpsScraper("migdal", {})._map_fund(policy())
    ingest_mislaka(session, c.id, ScrapingResult(success=True, accounts=[acct]))
    f = session.query(Fund).one()
    [y] = f.details["yearly_movements"]
    assert (y["year"], y["management_fees"], y["insurance_costs"]) == ("2025", 812.4, 1154.0)
    assert f.details["insurance_covers"][0]["monthly_cost"] == 96.15
    d = session.query(FundDeposit).one()
    assert d.amount == Decimal("6644.00")
    assert d.raw["details"]["salary_month"] == "2026-08"
    assert d.raw["details"]["insured_salary"] == 21540.0
    assert d.raw["memo"] == "עובד: 2214.67 / מעסיק: 4429.33"


def test_backfills_details_on_existing_deposit(session):
    c = Credential(provider="migdal", label="m", owner="shai", secret_enc=b"x")
    session.add(c)
    session.flush()
    acct = IpsScraper("migdal", {})._map_fund(policy())
    acct.metadata["deposit_details"] = {}
    ingest_mislaka(session, c.id, ScrapingResult(success=True, accounts=[acct]))
    assert "details" not in session.query(FundDeposit).one().raw
    acct = IpsScraper("migdal", {})._map_fund(policy())
    ingest_mislaka(session, c.id, ScrapingResult(success=True, accounts=[acct]))
    assert session.query(FundDeposit).one().raw["details"]["salary_month"] == "2026-08"


def test_portfolio_history_shared_by_funds_is_dropped(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from israeli_finance_scrapers.models.pension import BalancePoint

    from freerise.sync import ips

    shared = [
        BalancePoint(date="2026-09-01", balance=206787.0),
        BalancePoint(date="2026-10-01", balance=206868.0),
    ]
    a = policy(balance_history=shared)
    b = policy(balance_history=list(shared))
    b.policy_id = "p2"
    own = policy(balance_history=[BalancePoint(date="2026-09-01", balance=429000.0)])
    own.policy_id = "p3"
    res = SimpleNamespace(success=True, funds=[a, b, own], accounts=[], long_term_token=None)

    class Inner:
        on_otp_request = on_progress = None

        async def scrape(self):
            return res

    monkeypatch.setattr(ips, "create_ifs_scraper", lambda *_: Inner())
    out = asyncio.run(IpsScraper("hafenix", {}).scrape())
    hist = [acct.metadata["balance_history"] for acct in out.accounts]
    assert (
        hist[0] == hist[1] == [{"date": "2026-10-25", "balance": 429860.0}]
    )  # only its own balance
    assert hist[2] == [{"date": "2026-09-01", "balance": 429000.0}]
    portfolio = json.loads(out.accounts[0].metadata["details"])["portfolio_history"]
    assert portfolio == [
        {"date": "2026-09-01", "balance": 206787.0},
        {"date": "2026-10-01", "balance": 206868.0},
    ]
    assert json.loads(out.accounts[2].metadata["details"])["portfolio_history"] is None
