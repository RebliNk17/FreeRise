"""Run an institutional pension/savings provider through `israeli-pension-scrapers`.

Maps the unified `PensionScrapingResult` (`FundPolicy`, `InvestmentTrack`, `DepositTransaction`,
`InsuranceCover`) onto `ScrapingResult` / `AccountResult` so `ingest_mislaka` stores policies,
balance snapshots, investment tracks, management fees, and monthly salary deposits identically
across all pension providers (HaPhoenix, Migdal, etc.).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from israeli_pension_scrapers import (
    FundPolicy,
)
from israeli_pension_scrapers import (
    ScraperOptions as IpsOptions,
)
from israeli_pension_scrapers import (
    create_scraper as create_ips_scraper,
)
from scraper import ScraperOptions, ScrapingResult
from scraper.models.account import AccountResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType

PROVIDERS: dict[str, str] = {
    "hafenix": "haphoenix",
    "migdal": "migdal",
}

_ERROR_MAP: dict[str, str] = {
    "INVALID_CREDENTIALS": "INVALID_PASSWORD",
    "INVALID_OTP": "INVALID_OTP",
    "OTP_TIMEOUT": "OTP_TIMEOUT",
    "ACCOUNT_BLOCKED": "ACCOUNT_BLOCKED",
    "NETWORK_ERROR": "GENERAL_ERROR",
    "PROVIDER_ERROR": "GENERAL_ERROR",
    "PARSE_ERROR": "GENERAL_ERROR",
    "GENERAL_ERROR": "GENERAL_ERROR",
}


def enabled(provider: str) -> bool:
    return provider in PROVIDERS


class IpsScraper:
    """Adapter around `israeli_pension_scrapers.BasePensionScraper` matching `BaseScraper`."""

    def __init__(
        self,
        provider: str,
        credentials: dict[str, Any],
        options: ScraperOptions | None = None,
    ) -> None:
        self.provider_name = provider
        self.credentials = credentials
        self.options = options or ScraperOptions()
        self.on_otp_request: Callable[[], Any] | None = None
        self.on_progress: Callable[[str], None] | None = None
        self.refreshed_otp_long_term_token: str | None = None

    async def scrape(self) -> ScrapingResult:
        ips_key = PROVIDERS[self.provider_name]
        ips_opts = IpsOptions(
            start_date=getattr(self.options, "start_date", None),
            timeout=float(getattr(self.options, "timeout", 60.0) or 60.0),
        )
        inner = create_ips_scraper(ips_key, self.credentials, ips_opts)
        inner.on_otp_request = self.on_otp_request
        inner.on_progress = self.on_progress

        res = await inner.scrape()
        self.refreshed_otp_long_term_token = res.refreshed_long_term_token

        if not res.success:
            err_key = res.error_type.value if res.error_type else "GENERAL_ERROR"
            return ScrapingResult(
                success=False,
                error_type=_ERROR_MAP.get(err_key, "GENERAL_ERROR"),
                error_message=res.error_message,
            )

        accounts = [self._map_fund(f) for f in res.funds]
        return ScrapingResult(success=True, accounts=accounts)

    def _map_fund(self, f: FundPolicy) -> AccountResult:
        tracks = [
            {
                "name": t.name,
                "yield_pct": t.yield_ytd_pct or 0.0,
                "allocation_pct": t.allocation_pct or 0.0,
                "sum": t.balance or 0.0,
            }
            for t in f.tracks
        ]
        covers = [
            {
                "title": c.title,
                "desc": c.description or "",
                "amount": c.insured_amount or c.monthly_amount or 0.0,
            }
            for c in f.insurance_covers
        ]
        transactions: list[Transaction] = []
        for dep in f.deposits:
            memo_parts: list[str] = []
            if dep.employee_amount:
                memo_parts.append(f"עובד: {dep.employee_amount:.0f}")
            if dep.employer_amount:
                memo_parts.append(f"מעסיק: {dep.employer_amount:.0f}")
            if dep.compensation_amount:
                memo_parts.append(f"פיצויים: {dep.compensation_amount:.0f}")
            transactions.append(
                Transaction(
                    type=TransactionType.NORMAL,
                    status=TransactionStatus.COMPLETED,
                    date=dep.date,
                    processed_date=dep.date,
                    original_amount=dep.total_amount,
                    original_currency=f.currency or "ILS",
                    charged_amount=dep.total_amount,
                    charged_currency=f.currency or "ILS",
                    description=dep.description
                    or (f"הפקדה - {dep.employer_name}" if dep.employer_name else "הפקדה"),
                    identifier=dep.identifier,
                    memo=" / ".join(memo_parts) if memo_parts else None,
                )
            )

        balance_date = f.balance_date or f.data_as_of_date or ""
        history = [{"date": p.date, "balance": p.balance} for p in f.balance_history]
        if not history and balance_date:
            history = [{"date": balance_date, "balance": f.balance}]

        details: dict[str, Any] = {
            "manufacturer": f.manufacturer,
            "employer": f.employer_name,
            "establishment_date": f.establishment_date,
            "start_date": f.start_date,
            **(f.extra or {}),
        }

        return AccountResult(
            account_number=f.policy_id,
            transactions=transactions,
            balance=f.balance,
            balance_date=balance_date or None,
            metadata={
                "provider": self.provider_name,
                "policy_id": f.policy_id,
                "policy_type": f.product_type.value,
                "pension_type": f.pension_type.value if f.pension_type else None,
                "account_name": f.name,
                "balance": f.balance,
                "balance_date": balance_date,
                "investment_tracks": json.dumps(tracks, ensure_ascii=False),
                "commission_deposits_pct": f.fees.from_deposit_pct,
                "commission_savings_pct": f.fees.from_savings_pct,
                "insurance_covers": json.dumps(covers, ensure_ascii=False) if covers else None,
                "liquidity_date": f.liquidity_date,
                "balance_history": history or None,
                "details": json.dumps(details, ensure_ascii=False),
            },
        )
