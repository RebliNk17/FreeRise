from datetime import date
from decimal import Decimal

from sqlalchemy import select
from test_summary import acct, tx

from freerise.cashflow.cycles import cycle_by_label
from freerise.cashflow.summary import cycle_summary
from freerise.home.builder import build_home
from freerise.models import Category, Transaction, TransactionSplit

C = cycle_by_label(2026, 10, 10)


def _cid(s, name):
    return s.scalar(select(Category.id).where(Category.name == name))


def _split(s, parts):
    t = s.scalars(select(Transaction).order_by(Transaction.id.desc())).first()
    for name, amount in parts:
        s.add(TransactionSplit(transaction_id=t.id, category_id=_cid(s, name), amount=amount))
    s.flush()
    return t


def _totals(s):
    return {
        c.name: c.total
        for g in cycle_summary(s, C).groups
        for c in g.categories
        if g.group in ("variable", "fixed")
    }


def test_split_counts_as_parts(session):
    a = acct(session, "card")
    tx(session, a, -300, "קניות")
    _split(session, [("כלכלה", Decimal(-200)), ("פארמה", Decimal(-100))])
    assert _totals(session) == {"כלכלה": 200, "פארמה": 100}


def test_remainder_when_amount_changed_after_split(session):
    a = acct(session, "card")
    tx(session, a, -300, "קניות")
    t = _split(session, [("כלכלה", Decimal(-200)), ("פארמה", Decimal(-100))])
    t.amount = Decimal(-350)  # e.g. pending completed for a different amount
    session.flush()
    assert _totals(session) == {"כלכלה": 200, "פארמה": 100, "קניות": 50}


def test_home_lists_each_part(session):
    a = acct(session, "card")
    tx(session, a, -300, "קניות", d=date(2026, 10, 15))
    t = _split(session, [("כלכלה", Decimal(-200)), ("ספורט", Decimal(-100))])
    h = build_home(session, C, date(2026, 10, 20))
    parts = [x for w in h.variable.weeks for x in w.transactions if x.id == t.id]
    assert sorted(x.amount for x in parts) == [-200, -100]
    assert all(x.split_total == -300 and len(x.split) == 2 for x in parts)
    assert h.variable.spent == 300
