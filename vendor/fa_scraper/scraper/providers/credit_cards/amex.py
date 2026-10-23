from scraper.providers.credit_cards.isracard_amex_base import IsracardAmexBaseScraper


class AmexScraper(IsracardAmexBaseScraper):
    """Scraper for American Express Israel credit card transactions.

    Inherits all login and data fetching logic from
    IsracardAmexBaseScraper, configured with the Amex-specific
    base URL and company code.
    """

    BASE_URL = "https://digital.isracard.co.il"
    COMPANY_CODE = "77"
