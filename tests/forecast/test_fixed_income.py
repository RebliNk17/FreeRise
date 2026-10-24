import itertools
from datetime import date
from decimal import Decimal

from fastapi.encoders import jsonable_encoder
from scraper.models.account import AccountResult
from sqlalchemy import select

from freerise.accounts import account_holder
from freerise.cashflow.cycles import cycle_by_label
from freerise.cashflow.fees import fees_in_cycle
from freerise.cashflow.plan import cycle_plan
from freerise.cashflow.summary import cycle_summary
from freerise.forecast.attribution import attribute_income
from freerise.forecast.next_cycle import expected_in_cycle, next_cycle_forecast
from freerise.forecast.recurring import detect_recurring, mark_fixed_income
from freerise.home.builder import build_home
from freerise.models import Account, Category, Credential, RecurringItem, Transaction
from freerise.reconcile.card_bills import reconcile_range
from freerise.sync.service import _upsert_account

TODAY = date(2026, 10, 23)  # cycles start on the 10th; OCT = 10.10-9.11
SEP, OCT, NOV = (cycle_by_label(2026, m, 10) for m in (9, 10, 11))
_seq = itertools.count()


def _acct(s, kind="bank", owner="שי", holder=None):
    cred = Credential(provider="max", label="l", owner=owner, secret_enc=b"s")
    a = Account(
        credential=cred,
        provider_account_id=f"p{next(_seq)}",
        kind=kind,
        display_name="d",
        holder=holder,
    )
    s.add(a)
    s.flush()
    return a


def _cat(s, name):
    return s.scalar(select(Category.id).where(Category.name == name))


def _tx(s, a, d, amount, key="salary", cat="משכורת", **kw):
    t = Transaction(
        account_id=a.id,
        txn_key=f"fi{next(_seq)}",
        date=d,
        processed_date=d,
        amount=Decimal(str(amount)),
        description=key,
        merchant_key=key,
        category_id=_cat(s, cat) if cat else None,
        status="completed",
        raw={},
        **kw,
    )
    s.add(t)
    s.flush()
    return t


def _salary_item(s, key="salary", nxt=date(2026, 10, 10)):
    s.add(
        RecurringItem(
            merchant_key=key,
            direction="income",
            label=key,
            cadence="monthly",
            amount_kind="variable",
            expected_amount=Decimal(10000),
            last_date=date(2026, 9, 10),
            next_expected_date=nxt,
            status="confirmed",
            basis="b",
        )
    )
    s.flush()


def _salaries(s, *days, amount=10000, nxt=date(2026, 10, 10)):
    a = _acct(s)
    _salary_item(s, nxt=nxt)
    return [_tx(s, a, d, amount) for d in days]


def test_late_salary_moves_to_previous_cycle_when_missing(session):
    # Owner's example: usually on the 1st (start day 10); September's lands on Oct 11.
    days = (date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 11))
    txns = _salaries(session, *days, nxt=date(2026, 11, 1))
    attribute_income(session)
    late = txns[-1]
    assert (late.cycle_date, late.cycle_date_source) == (date(2026, 10, 9), "auto")
    assert [t.cycle_date for t in txns[:2]] == [None, None]
    assert cycle_summary(session, SEP).income == 10000
    assert cycle_summary(session, OCT).income == 0
    # The Oct cycle still expects its own salary (on Nov 1), not yet received.
    line = expected_in_cycle(session, OCT, TODAY).income_items[0]
    assert (line.date, line.charged) == (date(2026, 11, 1), False)
    assert cycle_plan(session, TODAY).expected_income == 10000


def test_one_missed_month_does_not_cascade(session):
    days = (date(2026, 8, 10), date(2026, 10, 11), date(2026, 11, 10), date(2026, 12, 10))
    txns = _salaries(session, *days, date(2027, 1, 11))  # usually the 10th; September missing
    attribute_income(session)
    assert [t.cycle_date for t in txns] == [None] * 5


def test_payment_that_fills_the_gap_moves(session):
    txns = _salaries(session, date(2026, 8, 10), date(2026, 9, 9), date(2026, 10, 10))
    attribute_income(session)
    assert [t.cycle_date for t in txns] == [None, date(2026, 9, 10), None]


def test_no_move_when_previous_cycle_has_one(session):
    txns = _salaries(session, date(2026, 8, 12), date(2026, 9, 12), date(2026, 10, 11))
    attribute_income(session)
    assert [t.cycle_date for t in txns] == [None, None, None]


def test_early_arrival_moves_forward_and_back_when_next_arrives(session):
    a = _acct(session)
    _salary_item(session)
    for d in (date(2026, 8, 10), date(2026, 9, 10)):
        _tx(session, a, d, 10000)
    early = _tx(session, a, date(2026, 10, 8), 10000)
    attribute_income(session)
    assert (early.cycle_date, early.cycle_date_source) == (date(2026, 10, 10), "auto")
    assert cycle_summary(session, OCT).income == 10000
    # The Oct cycle gets its own -> the early one goes back to its own cycle.
    _tx(session, a, date(2026, 10, 12), 10000)
    attribute_income(session)
    assert (early.cycle_date, early.cycle_date_source) == (None, None)


def test_manual_attribution_wins_and_auto_respects_it(session):
    _aug, sep, octo = _salaries(session, date(2026, 8, 12), date(2026, 9, 12), date(2026, 10, 11))
    sep.cycle_date, sep.cycle_date_source = date(2026, 10, 10), "manual"
    attribute_income(session)
    assert (sep.cycle_date, sep.cycle_date_source) == (date(2026, 10, 10), "manual")
    # Sep is empty now, but Oct 11 is nearest its own usual day (12th): it stays.
    assert (octo.cycle_date, octo.cycle_date_source) == (None, None)


def test_user_defined_income_projected_every_cycle_without_history(session):
    a = _acct(session)
    t = _tx(session, a, date(2026, 9, 15), 5000, key="freelance", cat="הכנסות אחרות")
    mark_fixed_income(
        session, t.merchant_key, "f", t.category_id, a.id, t.date, 31, Decimal(6000), True
    )
    oct_line = next(x for x in expected_in_cycle(session, OCT, TODAY).income_items)
    assert (oct_line.date, oct_line.amount, oct_line.charged) == (date(2026, 10, 31), 6000, False)
    assert next_cycle_forecast(session, TODAY).income_total == 6000  # Nov 30
    assert cycle_plan(session, TODAY).expected_income == 6000
    # Long after its next_expected_date: still expected (never "stopped").
    dec = cycle_by_label(2026, 12, 10)
    assert [x.date for x in expected_in_cycle(session, dec, date(2026, 12, 20)).income_items] == [
        date(2026, 12, 31)
    ]
    # Not before its first occurrence.
    assert expected_in_cycle(session, cycle_by_label(2026, 7, 10), TODAY).income_items == []


def test_detect_recurring_keeps_user_defined_day_and_amount(session):
    a = _acct(session)
    for m, amt in ((7, 4000), (8, 4100), (9, 4200)):
        _tx(session, a, date(2026, m, 15), amt, key="job")
    detect_recurring(session, TODAY)
    item = session.scalar(select(RecurringItem).where(RecurringItem.merchant_key == "job"))
    assert item.status == "confirmed" and not item.user_defined  # auto-confirmed
    mark_fixed_income(session, "job", "job", None, a.id, date(2026, 9, 15), 20, Decimal(5000), True)
    detect_recurring(session, TODAY)
    assert item.user_defined and item.status == "confirmed"
    assert (item.expected_amount, item.expected_day, item.next_expected_date) == (
        5000,
        20,
        date(2026, 9, 20),
    )
    # Variable amount: detection may refresh the amount, never the day.
    mark_fixed_income(session, "job", "job", None, a.id, date(2026, 9, 15), 20, Decimal(1), False)
    detect_recurring(session, TODAY)
    assert item.expected_amount != 1 and item.expected_day == 20


def test_shifted_txns_use_effective_date_and_edge_weeks(session):
    card = _acct(session, kind="card")
    fwd = _tx(session, card, date(2026, 10, 9), -100, key="shop", cat="קניות")
    fwd.cycle_date, fwd.cycle_date_source = date(2026, 10, 10), "manual"
    back = _tx(session, card, date(2026, 10, 12), -40, key="shop", cat="קניות")
    back.cycle_date, back.cycle_date_source = date(2026, 10, 9), "manual"
    fee = _tx(session, card, date(2026, 10, 9), -7, key="fee", cat="עמלות")
    fee.cycle_date, fee.cycle_date_source = date(2026, 10, 10), "manual"
    session.flush()

    assert fees_in_cycle(session, OCT).total == 7 and fees_in_cycle(session, SEP).total == 0
    h = jsonable_encoder(build_home(session, OCT, TODAY))
    first = h["variable"]["weeks"][0]
    assert [t["id"] for t in first["transactions"]] == [fwd.id]  # moved forward -> first week
    assert first["transactions"][0]["cycle_shift"] == "next"
    assert first["transactions"][0]["cycle_label"] == "אוקטובר 2026"
    assert cycle_plan(session, TODAY).weeks[0].spent == 100
    hs = jsonable_encoder(build_home(session, SEP, TODAY))
    last = hs["variable"]["weeks"][-1]
    assert [t["id"] for t in last["transactions"]] == [back.id]  # moved back -> last week
    assert last["transactions"][0]["cycle_shift"] == "previous"


def test_reconcile_uses_real_date(session):
    bank = _acct(session)
    bill = _tx(session, bank, date(2026, 10, 15), -500, key="חיוב מ-ישראכרט", cat=None)
    bill.category_id = session.scalar(select(Category.id).where(Category.group == "card_bill"))
    bill.cycle_date, bill.cycle_date_source = date(2026, 10, 9), "manual"
    session.flush()
    assert bill.id in {r.bank_txn_id for r in reconcile_range(session, OCT.start, OCT.end)}
    assert bill.id not in {r.bank_txn_id for r in reconcile_range(session, SEP.start, SEP.end)}


def test_holder_fallback_and_sync_metadata(session):
    a = _acct(session, owner="שי")
    assert account_holder(a) == "שי"
    a.holder = "אורטל"
    assert account_holder(a) == "אורטל"
    cred = a.credential
    res = AccountResult(account_number=a.provider_account_id, metadata={"ownerName": "דנה"})
    assert _upsert_account(session, cred, res).holder == "אורטל"  # user value kept
    a.holder = ""  # cleared by the user: shows the owner, sync doesn't refill it
    assert _upsert_account(session, cred, res).holder == "" and account_holder(a) == "שי"
    a.holder = None
    assert _upsert_account(session, cred, res).holder == "דנה"
    assert build_home(session, OCT, TODAY).multi_holder is False  # one account
    _acct(session, owner="אורטל")
    assert build_home(session, OCT, TODAY).multi_holder is True
