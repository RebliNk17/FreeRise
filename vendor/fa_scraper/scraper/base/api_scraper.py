import httpx

from scraper.base.base_scraper import BaseScraper
from scraper.utils.proxy import httpx_proxy  # freerise patch: proxy


class ApiScraper(BaseScraper):
    """Scraper using HTTP requests only (no browser)."""

    client: httpx.AsyncClient

    async def initialize(self) -> None:
        """Create an async HTTP client."""
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            proxy=httpx_proxy(),  # freerise patch: proxy
        )

    async def terminate(self, success: bool) -> None:
        """Close the HTTP client."""
        if hasattr(self, "client"):
            await self.client.aclose()
