"""A scripted fake bank ("demo") for exercising the connect flow without a real provider.

Only offered / runnable when FREERISE_ALLOW_DEMO=1. The username picks the behaviour:
ok | otp (code 123456) | wrong (wrong password) | blocked | locked | slow (no progress).
"""

import asyncio
import os
from datetime import date, timedelta

from scraper import PROVIDER_CONFIGS, ProviderConfig, ScraperOptions, create_scraper
from scraper.base import BaseScraper
from scraper.exceptions import AutomationBlockedError, InvalidOtpError
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType

from freerise.sync import ibs

KEY = "demo"
OTP_CODE = "123456"
STEP_S = float(os.environ.get("FREERISE_DEMO_STEP_S", "1.5"))

# Registered process-wide so PROVIDER_CONFIGS lookups work; offered only when demo_enabled().
PROVIDER_CONFIGS.setdefault(
    KEY, ProviderConfig(name="Demo bank", required_fields=["username", "password"])
)


def demo_enabled() -> bool:
    return os.environ.get("FREERISE_ALLOW_DEMO") == "1"


class DemoScraper(BaseScraper):
    async def initialize(self) -> None:
        await asyncio.sleep(STEP_S)

    async def login(self) -> LoginResult:
        await asyncio.sleep(STEP_S)
        mode = self.credentials.get("username", "ok")
        if mode == "wrong":
            return self._fail_login(LoginResult.INVALID_PASSWORD, "demo: wrong password")
        if mode == "locked":
            return self._fail_login(LoginResult.ACCOUNT_BLOCKED, "demo: account locked")
        if mode == "blocked":
            # Same shape as the real message, advice included, so the UI's stripping is exercised.
            raise AutomationBlockedError(
                "login failed: demo WAF block. Consider: 1) Using show_browser=True "
                "2) Waiting 3) Using residential proxies"
            )
        if mode == "slow":
            await asyncio.sleep(3600)
        if mode == "otp" and not self.credentials.get("otpLongTermToken"):
            self._emit_progress("waiting for OTP code")
            if await self.on_otp_request() != OTP_CODE:
                raise InvalidOtpError("demo: wrong OTP code")
            # Like OneZero: later runs log in with the token, no new SMS.
            self.refreshed_otp_long_term_token = "demo-token"
            await asyncio.sleep(STEP_S)
        return LoginResult.SUCCESS

    async def fetch_data(self) -> list[AccountResult]:
        await asyncio.sleep(STEP_S)
        d = (date.today() - timedelta(days=2)).isoformat()
        t = Transaction(
            type=TransactionType.NORMAL,
            status=TransactionStatus.COMPLETED,
            date=d,
            processed_date=d,
            original_amount=-42.5,
            original_currency="ILS",
            charged_amount=-42.5,
            description="קפה הדגמה",
            identifier=f"demo-{d}",
        )
        return [AccountResult(account_number="12-345-678901", transactions=[t], balance=1234.5)]


def make_scraper(provider: str, credentials: dict, options: ScraperOptions | None = None):
    if provider == KEY:
        if not demo_enabled():
            raise ValueError("demo provider is disabled")
        return DemoScraper(provider, credentials, options)
    if ibs.enabled(provider):  # the npm package; FREERISE_IBS_PROVIDERS picks which providers
        return ibs.IbsScraper(provider, credentials, options)
    return create_scraper(provider, credentials, options)
