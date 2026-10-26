from datetime import date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from freerise.api.deps import DB, get_or_404
from freerise.models import ClearingHouseReport, Credential, Fund, FundDeposit
from freerise.pension.deposits import deposit_alerts, message
from freerise.pension.returns import FundOverview, fund_yearly, funds_overview, monthly_gains

router = APIRouter()


class Point(BaseModel):
    date: date
    balance: float


class FundOut(BaseModel):
    """ytd_return_pct is a fraction (0.1064 = 10.64%); fee_*_pct are percent numbers as stored
    (0.6 = 0.6%)."""

    id: int
    policy_id: str
    name: str
    product_type: str
    owner: str
    company: str | None
    liquidity_date: date | None
    latest_balance: float
    as_of: date
    ytd_profit: float | None
    ytd_return_pct: float | None
    fee_deposit_pct: float | None
    fee_savings_pct: float | None
    forecast_monthly_pension: float | None  # Mislaka's figure, as-is (details JSON)
    monthly: list[Point]
    pension_type: str | None
    track: str | None  # the investment track, when there is just one
    employer: str | None
    liquid_balance: float | None
    investment_expense_pct: float | None  # percent number, like fee_*_pct
    start_date: date | None  # earliest of the policy's start / establishment dates: seniority
    insurance_covers: list[dict]  # {title, description, insured_amount, monthly_cost}
    yearly_movements: list[dict]  # {year, opening_balance, deposits, gains, management_fees,
    #                               insurance_costs, closing_balance}, as the portal gives them


class MislakaCredential(BaseModel):
    id: int
    label: str
    owner: str
    last_success_at: datetime | None


class ForecastOut(BaseModel):
    """Retirement forecast from the latest clearing-house report, as Mislaka gives it."""

    credential_id: int
    owner: str
    report_month: date
    forecast_monthly_pension: float | None
    forecast_lump_sum: float | None
    forecast_total_balance: float | None
    total_savings: float | None


class DepositAlertOut(BaseModel):
    """A missing, late or short employer deposit (freerise.pension.deposits)."""

    kind: str
    fund_id: int
    month: date
    title: str
    body: str


class MonthGainOut(BaseModel):
    fund_ids: list[int]  # several = a provider's portfolio reported only as a whole
    month: date
    start_balance: float
    end_balance: float
    deposits: float
    gain: float


class DepositRowOut(BaseModel):
    """Split, salary month and insured salary only where the portal gives them (Migdal, Phoenix)."""

    fund_id: int
    date: date
    amount: float
    employer: str | None
    salary_month: str | None  # YYYY-MM
    employee_amount: float | None
    employer_amount: float | None
    compensation_amount: float | None
    insured_salary: float | None


class FundsOut(BaseModel):
    total: float
    as_of: date | None
    funds: list[FundOut]
    credentials: list[MislakaCredential]
    forecast: list[ForecastOut]
    deposit_alerts: list[DepositAlertOut]
    gains: list[MonthGainOut]
    deposits: list[DepositRowOut]  # newest first


class YearOut(BaseModel):
    """return_pct is a fraction."""

    year: int
    start_balance: float
    deposits: float
    profit: float
    end_balance: float
    return_pct: float | None


class DepositOut(BaseModel):
    date: date
    amount: float


class FundDetailOut(BaseModel):
    fund: FundOut
    yearly: list[YearOut]
    deposits: list[DepositOut]
    tracks: list


def _num(x) -> float | None:
    """Portal value -> float; None if missing or not a number (never 500 the list)."""
    try:
        return None if x is None or isinstance(x, bool) else float(x)
    except TypeError, ValueError:
        return None


def _iso(x) -> date | None:
    try:
        return date.fromisoformat(str(x)[:10]) if x else None
    except ValueError:
        return None


def _deposit(d: FundDeposit) -> DepositRowOut:
    x = (d.raw or {}).get("details") or {}
    desc = (d.raw or {}).get("description") or ""
    return DepositRowOut(
        fund_id=d.fund_id,
        date=d.date,
        amount=d.amount,
        employer=x.get("employer") or desc.partition(" - ")[2].strip() or None,
        salary_month=x.get("salary_month"),
        employee_amount=_num(x.get("employee_amount")),
        employer_amount=_num(x.get("employer_amount")),
        compensation_amount=_num(x.get("compensation_amount")),
        insured_salary=_num(x.get("insured_salary")),
    )


def _fund(o: FundOverview) -> FundOut:
    f = o.fund
    det = f.details or {}
    return FundOut(
        id=f.id,
        policy_id=f.policy_id,
        name=f.name,
        product_type=f.product_type,
        owner=f.owner,
        company=f.company,
        liquidity_date=f.liquidity_date,
        latest_balance=o.latest_balance,
        as_of=o.as_of,
        ytd_profit=o.ytd_profit,
        ytd_return_pct=o.ytd_return_pct,
        fee_deposit_pct=f.fee_deposit_pct,
        fee_savings_pct=f.fee_savings_pct,
        forecast_monthly_pension=_num((f.details or {}).get("monthly_pension_forecast")),
        monthly=[Point(date=d, balance=b) for d, b in o.monthly],
        pension_type=f.pension_type,
        track=f.tracks[0].get("name") if len(f.tracks or []) == 1 else None,
        employer=det.get("employer"),
        liquid_balance=_num(det.get("liquid_balance")),
        investment_expense_pct=_num(det.get("investment_expense_pct")),
        start_date=min(
            filter(None, (_iso(det.get("start_date")), _iso(det.get("establishment_date")))),
            default=None,
        ),
        insurance_covers=det.get("insurance_covers") or [],
        yearly_movements=det.get("yearly_movements") or [],
    )


@router.get("/pension/funds")
def list_funds(db: DB) -> FundsOut:
    ov = funds_overview(db)
    creds = db.scalars(
        select(Credential)
        .where(Credential.provider.in_(("mislaka", "hafenix", "migdal")), Credential.verified)
        .order_by(Credential.id)
    ).all()
    latest = {
        r.credential_id: r
        for r in db.scalars(
            select(ClearingHouseReport)
            .where(ClearingHouseReport.credential_id.in_([c.id for c in creds]))
            .order_by(ClearingHouseReport.report_month)
        )
    }  # ascending, so the newest report per credential wins
    return FundsOut(
        total=ov.total,
        as_of=max((o.as_of for o in ov.funds), default=None),
        funds=[_fund(o) for o in ov.funds],
        credentials=[
            MislakaCredential(
                id=c.id, label=c.label, owner=c.owner, last_success_at=c.last_success_at
            )
            for c in creds
        ],
        forecast=[
            ForecastOut(
                credential_id=c.id,
                owner=c.owner,
                report_month=r.report_month,
                forecast_monthly_pension=_num(r.data.get("forecast_monthly_pension")),
                forecast_lump_sum=_num(r.data.get("forecast_lump_sum")),
                forecast_total_balance=_num(r.data.get("forecast_total_balance")),
                total_savings=_num(r.data.get("total_savings")),
            )
            for c in creds
            if (r := latest.get(c.id))
        ],
        deposit_alerts=[
            DepositAlertOut(kind=a.kind, fund_id=a.fund_id, month=a.month, title=t, body=b)
            for a in deposit_alerts(db)
            for t, b in [message(a)]
        ],
        gains=[MonthGainOut(**vars(g)) for g in monthly_gains(db)],
        deposits=[
            _deposit(d)
            for d in db.scalars(
                select(FundDeposit).order_by(FundDeposit.date.desc(), FundDeposit.id)
            )
        ],
    )


@router.get("/pension/funds/{id}")
def get_fund(id: int, db: DB) -> FundDetailOut:
    fund = get_or_404(db, Fund, id)
    # ponytail: overview computes every fund; fine for a household's handful of policies
    o = next((o for o in funds_overview(db).funds if o.fund.id == id), None)
    if o is None:  # no snapshots yet -> not listed in /pension/funds either
        raise HTTPException(404, "no balance data for fund")
    deps = db.scalars(
        select(FundDeposit).where(FundDeposit.fund_id == id).order_by(FundDeposit.date)
    )
    return FundDetailOut(
        fund=_fund(o),
        yearly=[YearOut(**vars(r)) for r in fund_yearly(db, id)],
        deposits=[DepositOut(date=d.date, amount=d.amount) for d in deps],
        tracks=fund.tracks or [],
    )
