"""Store a Mislaka (pension clearing house) scrape: funds, balance history, deposits, reports."""

import dataclasses
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from scraper import ScrapingResult
from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.models import ClearingHouseReport, Credential, Fund, FundDeposit, FundSnapshot

# Same as scraper.providers.insurances.mislaka.CLEARING_HOUSE_REPORTS.
REPORTS_KEY = "clearing_house_reports"
CENT = Decimal("0.01")


@dataclasses.dataclass
class IngestStats:
    funds: int = 0  # new funds
    snapshots: int = 0  # new snapshots
    deposits: int = 0  # new deposits
    reports: int = 0  # new reports

    @property
    def added(self) -> int:
        return self.snapshots + self.deposits


def _date(s: str | None) -> date | None:
    return datetime.fromisoformat(s).date() if s else None


def _dec(x) -> Decimal | None:
    try:
        return None if x is None or x == "" else Decimal(str(x))
    except InvalidOperation:
        return None


def _json(s, default):
    if isinstance(s, str):
        try:
            return json.loads(s)
        except ValueError:
            return default
    return s if s is not None else default


def ingest_mislaka(session: Session, credential_id: int, result: ScrapingResult) -> IngestStats:
    """Upsert funds and their history; never deletes. Flush only; caller commits."""
    cred = session.get(Credential, credential_id)
    stats = IngestStats()
    for a in result.accounts:
        m = a.metadata or {}
        details = _json(m.get("details"), {})
        fields = {
            "credential_id": credential_id,
            "product_type": m.get("policy_type") or "unknown",
            "pension_type": m.get("pension_type"),
            "name": m.get("account_name") or a.account_number,
            "company": details.get("manufacturer"),
            "liquidity_date": _date(m.get("liquidity_date")),
            "fee_deposit_pct": _dec(m.get("commission_deposits_pct")),
            "fee_savings_pct": _dec(m.get("commission_savings_pct")),
            "tracks": _json(m.get("investment_tracks"), []),
            "details": details,
            "owner": cred.owner,
        }
        fund = session.scalar(select(Fund).where(Fund.policy_id == a.account_number))
        if fund is None:
            fund = Fund(policy_id=a.account_number, **fields)
            session.add(fund)
            session.flush()
            stats.funds += 1
        else:
            for k, v in fields.items():
                setattr(fund, k, v)

        history = {_date(h["date"]): h["balance"] for h in m.get("balance_history") or []}
        if a.balance is not None and a.balance_date:
            history[_date(a.balance_date)] = a.balance
        existing = {
            s.as_of: s
            for s in session.scalars(select(FundSnapshot).where(FundSnapshot.fund_id == fund.id))
        }
        for as_of, bal in history.items():
            bal = Decimal(str(bal)).quantize(CENT)
            if as_of in existing:
                existing[as_of].balance = bal
            else:
                session.add(FundSnapshot(fund_id=fund.id, as_of=as_of, balance=bal))
                stats.snapshots += 1

        seen = {
            tuple(r)
            for r in session.execute(
                select(FundDeposit.date, FundDeposit.amount).where(FundDeposit.fund_id == fund.id)
            )
        }
        extra = m.get("deposit_details") or {}  # salary month, split, insured salary (ips.py)
        for t in a.transactions:
            key = (_date(t.date), Decimal(str(t.charged_amount)).quantize(CENT))
            raw = dataclasses.asdict(t)
            if d := extra.get(f"{key[0]}|{key[1]}"):
                raw["details"] = d
            if key not in seen:
                seen.add(key)
                session.add(FundDeposit(fund_id=fund.id, date=key[0], amount=key[1], raw=raw))
                stats.deposits += 1
            elif "details" in raw:  # backfill rows stored before details were kept
                for row in session.scalars(
                    select(FundDeposit).where(
                        FundDeposit.fund_id == fund.id,
                        FundDeposit.date == key[0],
                        FundDeposit.amount == key[1],
                    )
                ):
                    row.raw = raw

    for r in result.extras.get(REPORTS_KEY) or []:
        if not (d := _date(r.get("calc_date"))):
            continue
        month = d.replace(day=1)
        row = session.scalar(
            select(ClearingHouseReport).where(
                ClearingHouseReport.credential_id == credential_id,
                ClearingHouseReport.report_month == month,
            )
        )
        if row is None:
            session.add(
                ClearingHouseReport(credential_id=credential_id, report_month=month, data=r)
            )
            stats.reports += 1
        else:
            row.data = r
    session.flush()
    return stats
