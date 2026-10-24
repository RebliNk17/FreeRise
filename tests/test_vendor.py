import ast
import re
from pathlib import Path

from scraper import PROVIDER_CONFIGS, BaseScraper, create_scraper

VENDOR = Path(__file__).parent.parent / "vendor"


def test_all_needed_providers_registered():
    assert {"onezero", "isracard", "amex", "max", "visa cal", "mislaka"} <= set(PROVIDER_CONFIGS)


def test_create_scraper_returns_instance():
    s = create_scraper("max", {"username": "u", "password": "p"}, None)
    assert isinstance(s, BaseScraper)


def test_no_transfer_endpoints():
    # String literals only: max.py has a docstring mentioning "transfer receiver/transfer".
    bad = re.compile(r"/transfer|/payment|makePayment|createTransfer", re.IGNORECASE)
    hits = []
    for p in VENDOR.rglob("*.py"):
        tree = ast.parse(p.read_text())
        docs = {
            id(n.body[0].value)
            for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and n.body
            and isinstance(n.body[0], ast.Expr)
        }
        hits += [
            f"{p}:{n.lineno}"
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and id(n) not in docs
            and bad.search(n.value)
        ]
    assert not hits, hits


def test_max_reports_cards_without_transactions():
    from scraper.providers.credit_cards.max import _idle_card_accounts

    cards = {
        "1234": {"Last4Digits": "1234", "CreditLimit": 10000, "OpenToBuy": 5576},
        "5678": {"Last4Digits": "5678", "CreditLimit": 12000, "OpenToBuy": 12000},
    }
    idle = _idle_card_accounts(cards, {"1234": ["txn"]})
    assert [a.account_number for a in idle] == ["5678"]
    assert idle[0].transactions == [] and idle[0].card_frame == 12000


async def test_cal_login_settles_on_dashboard_only(monkeypatch):
    from types import SimpleNamespace

    from scraper.providers.credit_cards import visa_cal

    assert await visa_cal._login_settled(
        SimpleNamespace(url="https://digital-web.cal-online.co.il/dashboard")
    )
    # still on the homepage with no login frame (spinner): keep waiting
    no_frame = SimpleNamespace(url="https://www.cal-online.co.il/", frames=[])
    monkeypatch.setattr(visa_cal, "_get_login_frame", _raise)  # skip the real 10s frame wait
    assert not await visa_cal._login_settled(no_frame)


async def _raise(*_):
    raise TimeoutError
