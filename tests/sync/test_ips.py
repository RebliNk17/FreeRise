from israeli_finance_scrapers.models.bank import Account, AccountType, InstallmentsInfo
from israeli_finance_scrapers.models.bank import Transaction as IfsTxn

from freerise.sync.ips import IpsScraper


def _map(provider, *txns):
    acc = Account("4250", AccountType.CREDIT_CARD, txns=list(txns))
    return IpsScraper(provider, {})._map_account(acc).transactions


def _inst(ident, n, total=36, date="2026-01-15"):
    return IfsTxn(
        ident,
        date,
        "2026-10-11",
        -1200.0,
        "ILS",
        -100.0,
        "חנות",
        installments=InstallmentsInfo(n, total),
    )


def test_max_installments_keep_the_vendored_identity():
    # Same row the vendored engine stored: `${arn}_${n}`, dated on its own payment month.
    first, eighth = _map("max", _inst("A1", 1), _inst("A1", 8))
    assert (first.identifier, first.date) == ("A1_1", "2026-01-15")
    assert (eighth.identifier, eighth.date) == ("A1_8", "2026-08-15")


def test_isracard_installments_dated_like_the_vendored_engine():
    (t,) = _map("isracard", _inst("B2", 4, 12, "2026-06-20"))
    assert (t.identifier, t.date) == ("B2", "2026-09-20")


def test_isracard_keys_on_the_web_api_voucher_number():
    raw = {"voucherNumber": 4321, "seqVoucherNumber": "0987654321"}
    t = IfsTxn("4321", "2026-10-17", "2026-11-10", -10.0, "USD", -37.5, "SHOP", raw_data=raw)
    assert [x.identifier for x in _map("isracard", t)] == ["987654321"]
    assert [x.identifier for x in _map("amex", t)] == ["987654321"]
    pending = IfsTxn("0012345678901", "2026-10-25", "2026-11-10", -50.0, "ILS", -50.0, "חנות")
    assert [x.identifier for x in _map("isracard", pending)] == ["0012345678901"]


def test_plain_charges_untouched():
    plain = IfsTxn("A1", "2026-08-28", "2026-10-11", -60.0, "ILS", -60.0, "ביטוח")
    (t,) = _map("max", plain)
    assert (t.identifier, t.date) == ("A1", "2026-08-28")
