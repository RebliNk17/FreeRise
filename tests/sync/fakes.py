from scraper import ScrapingResult
from scraper.base.base_scraper import describe_exception
from scraper.models.account import AccountResult
from scraper.models.transaction import (
    InstallmentInfo,
    Transaction,
    TransactionStatus,
    TransactionType,
)


class FakeScraper:
    """Scripted stand-in for a vendored scraper. Like BaseScraper.scrape, it turns
    exceptions raised during login (incl. the OTP callback) into a failed result."""

    def __init__(self, credentials, result, *, ask_otp=False, mutate=None, refreshed_token=None):
        self.credentials = credentials
        self.result = result
        self.ask_otp = ask_otp
        self.mutate = mutate or {}
        self.on_otp_request = None
        self.otp_code = None
        self.refreshed_otp_long_term_token = None
        self._refreshed_token = refreshed_token

    async def scrape(self):
        if self.ask_otp:
            try:
                self.otp_code = await self.on_otp_request()
            except Exception as e:  # noqa: BLE001 - mirrors BaseScraper.scrape
                return ScrapingResult(
                    success=False, error_type="GENERAL_ERROR", error_message=describe_exception(e)
                )
        self.credentials.update(self.mutate)
        # Real OneZero sets this attribute instead of mutating credentials.
        self.refreshed_otp_long_term_token = self._refreshed_token
        return self.result


def fake_factory(result, **kw):
    def factory(provider, credentials, options):
        s = FakeScraper(credentials, result, **kw)
        factory.created.append((s, options))
        return s

    factory.created = []
    return factory


def txn(
    amount,
    desc="Shop",
    date="2026-10-01T00:00:00.000Z",
    *,
    identifier=None,
    status=TransactionStatus.COMPLETED,
    installments=None,
):
    return Transaction(
        type=TransactionType.INSTALLMENTS if installments else TransactionType.NORMAL,
        status=status,
        date=date,
        processed_date=date,
        original_amount=amount,
        original_currency="ILS",
        charged_amount=amount,
        description=desc,
        identifier=identifier,
        installments=InstallmentInfo(*installments) if installments else None,
    )


def ok(*accounts):
    return ScrapingResult(success=True, accounts=list(accounts))


def account(number, *txns, balance=None):
    return AccountResult(account_number=number, transactions=list(txns), balance=balance)
