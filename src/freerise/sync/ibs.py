"""Run a provider through the original npm `israeli-bank-scrapers` (bridge/run.mjs).

Same surface as a vendored scraper (scrape(), on_otp_request, on_progress), and the result is
mapped onto the vendored models exactly as the vendored engine fills them, so txn_key, account
identity and failure_kind come out identical whichever engine scraped (tests/sync/test_ibs*.py).
Pick providers with FREERISE_IBS_PROVIDERS: a comma list of FreeRise provider keys, "all" (default) for
every mapped provider, "-key" to keep one on the vendored engine ("all,-max"), empty = none.
Providers missing from COMPANIES (Mislaka, HaPhoenix) have no package equivalent and always run on
the vendored engine.
"""

import asyncio
import contextlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.utils.phone_numbers import normalize_israeli_mobile
from scraper import ScraperOptions, ScrapingResult
from scraper.models.account import AccountResult, CardType
from scraper.models.transaction import (
    InstallmentInfo,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from scraper.providers.credit_cards.max import _idle_card_accounts

BRIDGE = Path(__file__).resolve().parents[3] / "bridge" / "run.mjs"
DEFAULT_PROVIDERS = "all"
# FreeRise provider key -> (package companyId, credential fields the package reads). The stored field
# names are the package's own loginFields (tests/sync/test_ibs.py checks both registries).
UP = ("username", "password")
COMPANIES = {
    "hapoalim": ("hapoalim", ("userCode", "password")),
    "leumi": ("leumi", UP),
    "discount": ("discount", ("id", "password", "num")),
    "mercantile": ("mercantile", ("id", "password", "num")),
    "mizrahi": ("mizrahi", UP),
    "otsar hahayal": ("otsarHahayal", UP),
    "union": ("union", UP),
    "beinleumi": ("beinleumi", UP),
    "massad": ("massad", UP),
    "yahav": ("yahav", ("username", "nationalID", "password")),
    "onezero": ("oneZero", ("email", "password", "phoneNumber", "otpLongTermToken")),
    "pagi": ("pagi", UP),
    "pepper": ("pepper", ("phoneNumber", "password", "otpLongTermToken")),
    "max": ("max", UP),  # the stored optional `id` is not sent: upstream has no ID challenge
    "visa cal": ("visaCal", UP),
    "isracard": ("isracard", ("id", "card6Digits", "password")),
    "amex": ("amex", ("id", "card6Digits", "password")),
    "beyahad bishvilha": ("beyahadBishvilha", ("id", "password")),
    "behatsdaa": ("behatsdaa", ("id", "password")),
}
# Package progress events -> the vendored BaseScraper messages service.STAGES knows.
STAGES = {
    "INITIALIZING": "initializing",
    "START_SCRAPING": "initializing",
    "LOGGING_IN": "logging in",
    "LOGIN_SUCCESS": "fetching data",
    "LOGIN_FAILED": "login failed",
    "CHANGE_PASSWORD": "login failed",
    "END_SCRAPING": "done",
    "TERMINATING": "terminating",
}
IL = ZoneInfo("Asia/Jerusalem")
TIMEOUT_S = float(os.environ.get("FREERISE_IBS_TIMEOUT_S", "1500"))
STDERR_TAIL = 2000
# Max builds `${arn}_${n}` even when the deal has no ARN; the vendored engine leaves those None.
NO_ARN = re.compile(r"(undefined|null)_\d+")
# BaseScraperWithBrowser throws on login results its switch lacks (ACCOUNT_BLOCKED, ...).
UNEXPECTED_LOGIN = re.compile(r'unexpected login result "([A-Z_]+)"')


def enabled(provider: str) -> bool:
    chosen = {
        p.strip() for p in os.environ.get("FREERISE_IBS_PROVIDERS", DEFAULT_PROVIDERS).split(",")
    }
    on = provider in chosen or "all" in chosen
    return provider in COMPANIES and on and f"-{provider}" not in chosen


def _il_date(ts: str) -> str:
    """Israel-local YYYY-MM-DD, what the vendored engine stores (and txn_key hashes).

    The package emits UTC instants for most providers; a date-only or naive value is local."""
    dt = datetime.fromisoformat(ts)
    return (dt.astimezone(IL) if dt.tzinfo else dt).date().isoformat()


def _txn(provider: str, t: dict) -> Transaction:
    charged, original = t.get("chargedAmount"), t.get("originalAmount")
    if not all(isinstance(x, (int, float)) for x in (charged, original)):
        # JSON null = NaN in the package (an amount it could not parse). Never store a guess.
        raise ValueError(f"non-numeric amount for {t.get('description')!r}")
    ident = t.get("identifier")
    # Some providers give numeric identifiers; the vendored models (and the DB column) are text.
    ident = None if ident in (None, "") else str(ident)
    if provider == "max" and ident and NO_ARN.fullmatch(ident):
        ident = None
    inst = t.get("installments")
    desc = t.get("description") or ""
    return Transaction(
        type=TransactionType(t["type"]),
        status=TransactionStatus(t["status"]),
        # The package emits UTC instants; the vendored engine Israel-local dates (txn_key uses it).
        date=_il_date(t["date"]),
        processed_date=_il_date(t.get("processedDate") or t["date"]),
        original_amount=original,
        original_currency=t.get("originalCurrency") or "ILS",
        # Both vendored mappers negate the raw amount, so a zero is -0.0 there ("-0.00" in txn_key).
        charged_amount=charged if charged else -0.0,
        charged_currency=t.get("chargedCurrency"),
        description=desc.strip() if provider == "max" else desc,
        memo=t.get("memo") or None,
        category=t.get("category"),
        identifier=ident,
        installments=InstallmentInfo(inst["number"], inst["total"]) if inst else None,
    )


def to_result(provider: str, msg: dict) -> ScrapingResult:
    if not msg.get("success"):
        et = msg.get("errorType") or "GENERAL_ERROR"
        em = msg.get("errorMessage") or f"no detail reported by the {provider} scraper"
        if "Automation detected and blocked" in em:
            et = "AUTOMATION_BLOCKED"
        elif et == "GENERIC" and (m := UNEXPECTED_LOGIN.search(em)):
            et = m[1]
        elif et == "GENERIC" and re.search(r"\d+ ?ms exceeded", em):  # puppeteer's own timeouts
            et = "TIMEOUT"
        elif et == "GENERIC":
            et = "GENERAL_ERROR"  # what the vendored engine reports for the same failures
        return ScrapingResult(success=False, error_type=et, error_message=em)
    accounts = [
        AccountResult(
            account_number=str(a["accountNumber"]),
            transactions=[_txn(provider, t) for t in a.get("txns") or []],
            balance=a.get("balance"),
            balance_date=a.get("balanceDate"),
            card_type=CardType(a["cardType"]) if a.get("cardType") else None,
            card_frame=a.get("cardFrame"),
            savings_account=bool(a.get("savingsAccount")),
        )
        for a in msg.get("accounts") or []
    ]
    if provider == "max":
        seen = {a.account_number for a in accounts}
        accounts += _idle_card_accounts(msg.get("freeriseHomePageCards") or {}, seen)
    return ScrapingResult(success=True, accounts=accounts)


class IbsScraper:
    def __init__(
        self,
        provider: str,
        credentials: dict,
        options: ScraperOptions | None = None,
        *,
        cmd: list[str] | None = None,
        timeout_s: float = TIMEOUT_S,
    ):
        self.provider, self.credentials = provider, credentials
        self.options = options or ScraperOptions()
        self.cmd = cmd or [shutil.which("node") or "node", str(BRIDGE)]
        self.timeout_s = timeout_s
        self.on_otp_request = None
        self.on_progress = None
        self.refreshed_otp_long_term_token = None

    def _fail(self, message: str, error_type: str = "GENERAL_ERROR") -> ScrapingResult:
        return ScrapingResult(success=False, error_type=error_type, error_message=message)

    async def scrape(self) -> ScrapingResult:
        company, fields = COMPANIES[self.provider]
        creds = {f: self.credentials[f] for f in fields if self.credentials.get(f)}
        if "phoneNumber" in creds:  # OneZero wants +9725...; users type 05x (as the vendored one)
            creds["phoneNumber"] = normalize_israeli_mobile(creds["phoneNumber"])
        request = {
            "companyId": company,
            "credentials": creds,
            "startDate": self.options.start_date.isoformat(),
            "futureMonths": self.options.future_months_to_scrape,
            "screenshotPath": self.options.store_failure_screenshot_path,
        }
        env = {**os.environ, "TZ": "Asia/Jerusalem"}  # dates/start filter are Israel-local
        env.pop("DEBUG", None)  # the package's debug() output includes account data
        if os.environ.get("FREERISE_SCRAPER_PROXY"):  # the Cal API calls use Node's own fetch
            proxy = os.environ["FREERISE_SCRAPER_PROXY"]
            env |= {"NODE_USE_ENV_PROXY": "1", "HTTPS_PROXY": proxy, "HTTP_PROXY": proxy}
        proc = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            limit=256 * 1024 * 1024,  # the result is one line holding every transaction
        )
        stderr = bytearray()

        async def drain_stderr():
            while chunk := await proc.stderr.read(4096):
                stderr.extend(chunk)
                del stderr[:-STDERR_TAIL]

        drainer = asyncio.create_task(drain_stderr())
        try:
            proc.stdin.write(json.dumps(request).encode() + b"\n")
            await proc.stdin.drain()
            async with asyncio.timeout(self.timeout_s):
                return await self._converse(proc, stderr)
        except TimeoutError:
            return self._fail(f"bridge timeout after {self.timeout_s:.0f}s", "TIMEOUT")
        finally:
            await _stop(proc)
            drainer.cancel()

    async def _converse(self, proc, stderr: bytearray) -> ScrapingResult:
        while line := await proc.stdout.readline():
            try:
                msg = json.loads(line)
                kind = msg["type"]
            except ValueError, KeyError, TypeError:
                return self._fail("bridge: unreadable output")
            if kind == "progress":
                stage = str(msg.get("stage"))
                if self.on_progress:
                    self.on_progress(STAGES.get(stage, stage.lower()))
            elif kind == "otp_request":
                code = await self.on_otp_request()  # OtpTimeout propagates; the bridge is killed
                proc.stdin.write(json.dumps({"type": "otp", "code": code}).encode() + b"\n")
                await proc.stdin.drain()
            elif kind == "result":
                # OneZero: a long-term token minted from a fresh SMS code; service.py stores it.
                if token := msg.pop("freeriseOtpLongTermToken", None):
                    self.refreshed_otp_long_term_token = token
                try:
                    return to_result(self.provider, msg)
                except (ValueError, KeyError, TypeError) as e:
                    return self._fail(f"bridge result unreadable: {type(e).__name__}: {e}")
        await proc.wait()
        tail = stderr.decode(errors="replace").strip()[-500:]
        return self._fail(f"bridge exited ({proc.returncode}) without a result: {tail}")


async def _stop(proc) -> None:
    """SIGTERM lets puppeteer close Chrome; SIGKILL if it hangs."""
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), 10)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
