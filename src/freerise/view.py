"""Temporary account view filter ("חשבונות להצגה"): accounts hidden for one request only.

Unlike Account.excluded (permanent, set on /accounts), this is per browser: the web app sends
?hide_accounts=1,2 to home/cash-flow endpoints, which wrap their work in `hiding(...)`. Every
cash-flow sum that filters accounts with `counted()` then leaves those accounts out too."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import HTTPException

from freerise.models import Account

_HIDDEN: ContextVar[frozenset[int]] = ContextVar("hidden_accounts", default=frozenset())


def counted():
    """SQL condition: accounts that count in cash flow (not excluded, not hidden)."""
    cond = Account.excluded.is_(False)
    if hidden := _HIDDEN.get():
        cond = cond & Account.id.not_in(hidden)
    return cond


def parse_ids(raw: str | None) -> frozenset[int]:
    """'1,2' -> {1, 2}; 400 on junk."""
    try:
        return frozenset(int(x) for x in (raw or "").split(",") if x.strip())
    except ValueError:
        raise HTTPException(400, "hide_accounts: comma-separated ids") from None


@contextmanager
def hiding(raw: str | None) -> Iterator[None]:
    token = _HIDDEN.set(parse_ids(raw))
    try:
        yield
    finally:
        _HIDDEN.reset(token)
