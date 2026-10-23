"""Same raw provider data through both engines -> identical FreeRise rows and txn_keys.

The npm side is the pinned package's real Max / Cal mapping code (tests/sync/ibs_parity.mjs),
the Python side the vendored scrapers; both read the same canned API responses. Re-run on every
package upgrade: a failure here means existing rows would be re-keyed (duplicated) or changed.
"""

import dataclasses
import json
import shutil
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path

import pytest
from scraper import ScraperOptions
from scraper.providers.credit_cards import max as max_mod
from scraper.providers.credit_cards import visa_cal as cal_mod

from freerise.sync import ibs
from freerise.sync.dedup import txn_key

HARNESS = Path(__file__).with_name("ibs_parity.mjs")
pytestmark = pytest.mark.skipif(
    not (shutil.which("node") and (ibs.BRIDGE.parent / "node_modules").is_dir()),
    reason="node / bridge/node_modules not installed",
)


@pytest.fixture(autouse=True)
def israel_tz(monkeypatch):
    # The worker image runs in Asia/Jerusalem; naive provider timestamps are read in local time.
    monkeypatch.setenv("TZ", "Asia/Jerusalem")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


TODAY = date.today()
START = TODAY - timedelta(days=120)


def d(days_ago: int, t: str = "00:00:00") -> str:
    return f"{(TODAY - timedelta(days=days_ago)).isoformat()}T{t}"


def run_npm(company: str, raw: dict) -> dict:
    p = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps({"company": company, "startDate": START.isoformat(), "raw": raw}),
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
        env={"PATH": str(Path(shutil.which("node")).parent), "TZ": "Asia/Jerusalem"},
    )
    return json.loads(p.stdout)


def assert_same(provider, py_accounts, npm_msg, *, ignore=()):
    npm = ibs.to_result(provider, npm_msg)
    assert npm.success

    def norm(accounts):
        out = {}
        for a in accounts:
            txns = sorted(
                (txn_key(t), dataclasses.replace(t, **dict.fromkeys(ignore)))
                for t in a.transactions
            )
            out[a.account_number] = (dataclasses.replace(a, transactions=[]), txns)
        return out

    py, js = norm(py_accounts), norm(npm.accounts)
    assert py.keys() == js.keys()
    for number in py:
        assert py[number][0] == js[number][0], number  # identity, balance, frame, card type
        for (pk, pt), (jk, jt) in zip(py[number][1], js[number][1], strict=True):
            assert pk == jk  # txn_key: what dedup keys on
            assert pt == jt  # every stored field
    return npm


# --- Max ---------------------------------------------------------------------------------


def max_raw():
    def tx(card, days_ago, amount, **kw):
        return {
            "shortCardNumber": card,
            "purchaseDate": d(days_ago),
            "paymentDate": d(days_ago - 30),
            "actualPaymentAmount": amount,
            "originalAmount": amount,
            "originalCurrency": "ILS",
            "paymentCurrency": 376,
            "planName": "רגילה",
            "planTypeId": 5,
            "comments": "",
            "merchantName": "חנות",
            "categoryId": 1,
            **kw,
        }

    month = f"{TODAY.year}-{TODAY.month}-01"
    txns = [
        tx("1111", 10, 50, dealData={"arn": "A1"}, merchantName=" קפה ג'ו "),
        # UTC late evening = the next day in Israel.
        tx("1111", 11, 19.9, dealData={"arn": "A2"}, purchaseDate=d(11, "22:30:00Z")),
        tx("1111", 5, "12.30", paymentDate=None, merchantName="סופר"),  # pending, no ARN
        tx(
            "1111",
            40,
            100,
            planName="תשלומים",
            planTypeId=2,
            comments="תשלום 2 מתוך 3",
            dealData={"arn": "A3"},
        ),
        tx("1111", 20, 60, planName="תשלומים", planTypeId=2, comments="תשלום 1 מתוך 2"),  # no ARN
        tx(
            "1111",
            15,
            37.2,
            originalAmount=10,
            originalCurrency="USD",
            paymentCurrency=840,
            dealData={"arn": "A5"},
        ),
        tx(
            "1111",
            12,
            500,
            comments="העברה",
            fundsTransferReceiverOrTransfer="דני",
            fundsTransferComment="שכירות",
            dealData={"arn": "A6"},
        ),
        tx("1111", 9, 0, merchantName="אפס"),  # zero, no ARN: "-0.00" in the key
        tx("1111", 8, -20, dealData={"arn": "A8"}),  # refund
        tx("1111", 7, 33, merchantName="כפול"),  # two identical identifier-less charges
        tx("1111", 7, 33, merchantName="כפול"),
        tx("2222", 6, 70, dealData={"arn": "B1"}, categoryId=2),
        {"shortCardNumber": "1111", "planName": "", "merchantName": "summary row"},
    ]
    card = lambda last4, limit, otb: {
        "Last4Digits": last4,
        "CreditLimit": limit,
        "OpenToBuy": otb,
        "CycleSummary": [{"Date": d(-10), "CurrencySymbol": "₪"}],
    }
    return {
        "categories": {"result": [{"id": 1, "name": "מזון"}, {"id": 2, "name": "דלק"}]},
        "home": {
            "Result": {
                "UserCards": {
                    "Cards": [
                        card("1111", 10000, 7500.55),
                        card("2222", 5000, None),
                        card("3333", 3000, 3000),
                    ]
                }
            }
        },
        "months": {month: txns},
    }


async def test_max_parity(monkeypatch):
    raw = max_raw()
    month = next(iter(raw["months"]))

    async def fetch(page, url, ignore_errors=False):
        if "getCategories" in url:
            return raw["categories"]
        if "getHomePageData" in url:
            return raw["home"]
        from urllib.parse import parse_qs, urlsplit

        m = json.loads(parse_qs(urlsplit(url).query)["filterData"][0])["date"]
        return {"result": {"transactions": raw["months"][month] if m == month else []}}

    monkeypatch.setattr(max_mod, "fetch_get_within_page", fetch)
    s = max_mod.MaxScraper("max", {}, ScraperOptions(start_date=START))
    s.page = None
    py = await s.fetch_data()
    npm = assert_same("max", py, run_npm("max", raw))

    by = {a.account_number: a for a in npm.accounts}
    assert set(by) == {"1111", "2222", "3333"}  # idle card 3333 kept (freerise patch)
    t = {x.identifier: x for x in by["1111"].transactions}
    assert t["A3_2"].installments.number == 2  # ARN + installment number
    assert t["A2"].date == (TODAY - timedelta(days=10)).isoformat()  # Israel-local date
    assert by["1111"].balance == -2499.45 and by["1111"].card_frame == 10000


# --- Visa Cal ------------------------------------------------------------------------------


def cal_raw():
    def tx(ident, days_ago, amount, **kw):
        return {
            "trnIntId": ident,
            "trnPurchaseDate": d(days_ago),
            "debCrdDate": d(-10),
            "trnAmt": abs(amount),
            "amtBeforeConvAndIndex": amount,
            "trnCurrencySymbol": "ILS",
            "debCrdCurrencySymbol": "ILS",
            "trnTypeCode": "5",
            "numOfPayments": 0,
            "curPaymentNum": 0,
            "merchantName": "מכולת",
            "branchCodeDesc": "מזון",
            "transTypeCommentDetails": [],
            **kw,
        }

    month = lambda txns, immediate=(): {
        "statusCode": 1,
        "result": {
            "bankAccounts": [
                {
                    "debitDates": [{"transactions": list(txns)}],
                    "immidiateDebits": {"debitDays": [{"transactions": list(immediate)}]},
                }
            ]
        },
    }
    final = TODAY.replace(day=1) + timedelta(days=32)
    key = f"{final.year}-{final.month}"
    return {
        "session": {
            "init": {
                "result": {
                    "cards": [
                        {"cardUniqueId": "uid1", "last4Digits": "4321"},
                        {"cardUniqueId": "uid2", "last4Digits": "8765"},
                    ]
                }
            },
            "auth-module": {"auth": {"calConnectToken": "test-token"}},
        },
        "frames": {
            "uid1": {
                "result": {
                    "bankIssuedCards": {
                        "cardLevelFrames": [
                            {
                                "cardUniqueId": "uid1",
                                "nextTotalDebit": 1234.5,
                                "nextDebitDate": d(-10),
                            }
                        ],
                        "frameLimitForCardAmount": 20000,
                        "nextTotalDebitForAccount": 5000,
                    }
                }
            },
            "uid2": {
                "result": {
                    "calIssuedCards": {
                        "nextTotalDebitForAccount": 300,
                        "nextTotalDebitDateForAccount": d(-12),
                        "frameLimitForCardAmount": 8000,
                    }
                }
            },
        },
        "pending": {
            "uid1": {
                "statusCode": 1,
                "result": {
                    "cardsList": [
                        {
                            "authDetalisList": [
                                {
                                    "merchantName": "מסעדה",
                                    "trnPurchaseDate": d(2, "10:00:00"),
                                    "trnAmt": 80,
                                    "trnCurrencySymbol": "ILS",
                                    "trnTypeCode": "5",
                                    "branchCodeDesc": "מסעדות",
                                    "numberOfPayments": 0,
                                    "transTypeCommentDetails": [],
                                }
                            ]
                        }
                    ]
                },
            },
            "uid2": {"statusCode": 96, "title": "no pending"},
        },
        "months": {
            f"uid1:{key}": month(
                [
                    tx("C1", 10, 100),
                    tx("C2", 9, -30, trnTypeCode="6", transTypeCommentDetails=["זיכוי"]),
                    tx(
                        "C3", 40, 100, trnAmt=300, trnTypeCode="8", numOfPayments=3, curPaymentNum=2
                    ),
                    tx("C4", 15, 37.5, trnAmt=10, trnCurrencySymbol="USD"),
                ],
                [tx("C5", 3, 45, trnPurchaseDate=d(4, "21:30:00Z"))],
            ),
            f"uid2:{key}": month([tx("D1", 6, 70)]),
        },
        "emptyMonth": month([]),
    }


async def test_cal_parity(monkeypatch):
    raw = cal_raw()

    class Page:
        async def evaluate(self, script):
            return raw["session"]["init" if "'init'" in script else "auth-module"]

    async def fetch_post(url, body, headers):
        if "GetFrameStatus" in url:
            return raw["frames"][body["cardsForFrameData"][0]["cardUniqueId"]]
        if "getClearanceRequests" in url:
            return raw["pending"][body["cardUniqueIDArray"][0]]
        k = f"{body['cardUniqueId']}:{body['year']}-{body['month']}"
        return raw["months"].get(k, raw["emptyMonth"])

    monkeypatch.setattr(cal_mod, "fetch_post", fetch_post)
    s = cal_mod.VisaCalScraper("visa cal", {}, ScraperOptions(start_date=START))
    s.page = Page()
    py = await s.fetch_data()
    # memo is the one deliberate difference: the vendored port str()s the comment list
    # ("[]", "['זיכוי']"); the package joins it ("", "זיכוי") and FreeRise stores "" as None.
    npm = assert_same("visa cal", py, run_npm("visaCal", raw), ignore=("memo",))
    memos = {t.identifier: t.memo for t in npm.accounts[0].transactions}
    assert memos["C1"] is None and memos["C2"] == "זיכוי"
    assert {t.identifier: t.memo for t in py[0].transactions}["C1"] == "[]"
