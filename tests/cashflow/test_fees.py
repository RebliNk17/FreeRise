from datetime import date
from decimal import Decimal

from sqlalchemy import select

from freerise.cashflow.cycles import cycle_by_label
from freerise.cashflow.fees import fee_key, fees_in_cycle
from freerise.models import Account, Category, Credential, Transaction

C = cycle_by_label(2026, 10, 10)  # 2026-10-10..2026-11-09 (default start day 10)
_n = 0


def acct(session, excluded=False):
    cred = Credential(provider="x", label="l", owner="o", secret_enc=b"")
    a = Account(
        credential=cred, provider_account_id="1", kind="bank", display_name="b", excluded=excluded
    )
    session.add(a)
    session.flush()
    return a


def fee(session, a, amount, d, key, cat="עמלות"):
    global _n
    _n += 1
    cid = cat and session.scalar(select(Category.id).where(Category.name == cat))
    session.add(
        Transaction(
            account_id=a.id,
            txn_key=f"f{_n}",
            date=d,
            processed_date=d,
            amount=Decimal(amount),
            description=key,
            merchant_key=key,
            status="completed",
            raw={},
            category_id=cid,
        )
    )
    session.flush()


def test_fees_totals_previous_and_new_merchants(session):
    a, hidden = acct(session), acct(session, excluded=True)
    fee(session, a, "-6.90", date(2026, 9, 12), "עמלת פעולה 01 09")  # previous cycle
    fee(session, a, "-6.90", date(2026, 10, 12), "עמלת פעולה 01 10")  # same fee, new numbers
    fee(session, a, "-12.40", date(2026, 10, 20), "עמלת המרה")  # new merchant
    fee(session, a, "3", date(2026, 10, 21), "עמלת פעולה 01 10")  # refund: not a paid fee
    fee(session, a, "-50", date(2026, 10, 22), "עמלה חבויה", cat=None)  # uncategorized
    fee(session, hidden, "-99", date(2026, 10, 15), "עמלת מוחרג")
    f = fees_in_cycle(session, C)
    assert (f.total, f.count, f.previous_total) == (Decimal("19.30"), 2, Decimal("6.90"))
    assert [x.description for x in f.items] == ["עמלת פעולה 01 10", "עמלת המרה"]
    assert f.items[0].amount == Decimal("6.90") and f.items[0].account_id == a.id
    assert f.new_fee_merchants == ["עמלת המרה"]


def test_fees_empty(session):
    f = fees_in_cycle(session, C)
    assert (f.total, f.count, f.items, f.new_fee_merchants) == (0, 0, [], [])


def test_fee_key_drops_number_tokens():
    assert fee_key("ריבית חובה 01 10 31 10") == "ריבית חובה"
    assert fee_key("עמלת המרה 12 40 usd") == "עמלת המרה usd"
