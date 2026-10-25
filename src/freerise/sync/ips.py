"""Run banks, credit cards, and pension providers through `israeli-finance-scrapers`.

Maps the unified `ScrapingResult` (`Account` for banks/cards and `FundPolicy` for pensions/savings)
onto FreeRise's `ScrapingResult` / `AccountResult` models so all 8 pure-HTTP providers
(`onezero`, `pepper`, `visa cal`, `max`, `isracard`, `amex`, `hafenix`, `migdal`) run natively in
Python without launching a browser.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from israeli_finance_scrapers import (
    Account as IfsAccount,
)
from israeli_finance_scrapers import (
    FundPolicy,
)
from israeli_finance_scrapers import (
    ScraperOptions as IfsOptions,
)
from israeli_finance_scrapers import (
    create_scraper as create_ifs_scraper,
)
from scraper import ScraperOptions, ScrapingResult
from scraper.models.account import AccountResult
from scraper.models.transaction import (
    InstallmentInfo,
    Transaction,
    TransactionStatus,
    TransactionType,
)

DEFAULT_PROVIDERS = "all"

PROVIDERS: dict[str, str] = {
    "onezero": "onezero",
    "pepper": "pepper",
    "visa cal": "visa_cal",
    "max": "max",
    "isracard": "isracard",
    "amex": "amex",
    "hafenix": "haphoenix",
    "migdal": "migdal",
}

_ERROR_MAP: dict[str, str] = {
    "INVALID_CREDENTIALS": "INVALID_PASSWORD",
    "INVALID_PASSWORD": "INVALID_PASSWORD",
    "INVALID_OTP": "INVALID_OTP",
    "OTP_CANCELED": "GENERAL_ERROR",
    "OTP_TIMEOUT": "OTP_TIMEOUT",
    "ACCOUNT_BLOCKED": "ACCOUNT_BLOCKED",
    "TOKEN_EXPIRED": "INVALID_PASSWORD",
    "NETWORK_ERROR": "GENERAL_ERROR",
    "PROVIDER_ERROR": "GENERAL_ERROR",
    "PARSE_ERROR": "GENERAL_ERROR",
    "INIT_ERROR": "GENERAL_ERROR",
    "GENERAL_ERROR": "GENERAL_ERROR",
}

_STAGES: dict[str, str] = {
    "initializing": "initializing",
    "logging_in": "logging in",
    "login_success": "fetching data",
    "fetching_data": "fetching data",
}


def enabled(provider: str) -> bool:
    if provider in ("hafenix", "migdal"):
        return True
    chosen = {
        p.strip() for p in os.environ.get("FREERISE_IFS_PROVIDERS", DEFAULT_PROVIDERS).split(",")
    }
    on = provider in chosen or "all" in chosen
    return provider in PROVIDERS and on and f"-{provider}" not in chosen


class IpsScraper:
    """Adapter around `israeli_finance_scrapers.BaseScraper` matching FreeRise's `BaseScraper`."""

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
        ifs_key = PROVIDERS[self.provider_name]
        start_dt = getattr(self.options, "start_date", None)
        start_str = (
            start_dt.isoformat()
            if hasattr(start_dt, "isoformat")
            else (str(start_dt) if start_dt else None)
        )
        ifs_opts = IfsOptions(
            start_date=start_str,
            timeout=float(getattr(self.options, "timeout", 60.0) or 60.0),
        )
        inner = create_ifs_scraper(ifs_key, self.credentials, ifs_opts)
        inner.on_otp_request = self.on_otp_request
        if self.on_progress:
            inner.on_progress = lambda st: self.on_progress(_STAGES.get(st, st))

        res = await inner.scrape()
        if res.long_term_token and res.long_term_token != self.credentials.get("otpLongTermToken"):
            self.refreshed_otp_long_term_token = res.long_term_token

        if not res.success:
            err_key = str(res.error_type or "GENERAL_ERROR")
            return ScrapingResult(
                success=False,
                error_type=_ERROR_MAP.get(err_key, "GENERAL_ERROR"),
                error_message=res.error_message,
            )

        if res.funds:
            accounts = [self._map_fund(f) for f in res.funds]
        else:
            accounts = [self._map_account(a) for a in res.accounts]
        return ScrapingResult(success=True, accounts=accounts)

    def _map_account(self, a: IfsAccount) -> AccountResult:
        txns: list[Transaction] = []
        for t in a.txns:
            inst = (
                InstallmentInfo(number=t.installments.number, total=t.installments.total)
                if t.installments is not None
                else None
            )
            t_type = (
                TransactionType.INSTALLMENTS
                if (t.type.value == "installments" or inst is not None)
                else TransactionType.NORMAL
            )
            t_status = (
                TransactionStatus.PENDING
                if t.status.value == "pending"
                else TransactionStatus.COMPLETED
            )
            bdate = t.date[:10] if t.date else ""
            pdate = (t.processed_date[:10] if t.processed_date else bdate) or bdate
            txns.append(
                Transaction(
                    type=t_type,
                    status=t_status,
                    date=bdate,
                    processed_date=pdate,
                    original_amount=t.original_amount,
                    original_currency=t.original_currency or a.currency or "ILS",
                    charged_amount=t.charged_amount,
                    charged_currency=a.currency or "ILS",
                    description=t.description,
                    memo=t.memo,
                    identifier=str(t.identifier) if t.identifier is not None else None,
                    installments=inst,
                    category=t.category,
                )
            )
        return AccountResult(
            account_number=a.account_number,
            transactions=txns,
            balance=a.balance,
            card_frame=a.credit_limit,
        )

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
