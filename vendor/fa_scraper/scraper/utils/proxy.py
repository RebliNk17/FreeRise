"""Optional outbound proxy from env FREERISE_SCRAPER_PROXY. # freerise patch: proxy

Never log the value: it may contain credentials.
"""

import os
from urllib.parse import unquote, urlsplit


def httpx_proxy() -> str | None:
    return os.environ.get("FREERISE_SCRAPER_PROXY") or None


def playwright_proxy() -> dict[str, str] | None:
    raw = httpx_proxy()
    if not raw:
        return None
    u = urlsplit(raw)
    if not u.scheme or not u.hostname:
        raise ValueError("FREERISE_SCRAPER_PROXY must be scheme://[user:pass@]host[:port]")
    proxy = {"server": f"{u.scheme}://{u.netloc.rpartition('@')[2]}"}
    if u.username:
        proxy["username"] = unquote(u.username)
        proxy["password"] = unquote(u.password or "")
    return proxy
