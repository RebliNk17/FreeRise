from datetime import date
from decimal import Decimal

from sqlalchemy import select

from freerise.cashflow.cycles import cycle_by_label
from freerise.insights.history import spent_vs_expected
from freerise.models import Account, Category, CategoryBudget, Credential, Transaction

OCT = cycle_by_label(2026, 10, 10)


def acct(s, kind):
    a = Account(
        credential=Credential(provider="x", label="l", owner="o", secret_enc=b""),
        provider_account_id="h1",
        kind=kind,
        display_name="a",
    )
    s.add(a)
    s.flush()
    return a


def tx(s, a, amount, cat, d):
    cid = s.scalar(select(Category.id).where(Category.name == cat))
    s.add(
        Transaction(
            account_id=a.id,
            txn_key=f"h{d}",
            date=d,
            processed_date=d,
            amount=Decimal(amount),
            description="d",
            status="completed",
            category_id=cid,
            raw={},
        )
    )
    s.flush()


def test_spent_vs_expected_uses_prior_median_and_budgets(session):
    a = acct(session, "card")
    for m in range(1, 10):
        tx(session, a, -400 if m == 9 else -100, "כלכלה", d=date(2026, m, 15))
    cid = session.scalar(select(Category.id).where(Category.name == "כלכלה"))
    session.add(CategoryBudget(cycle_start=date(2026, 8, 10), category_id=cid, amount=Decimal(250)))
    session.flush()

    rows = spent_vs_expected(session, OCT, "variable")
    assert [(r.label_month, r.spent, r.expected) for r in rows] == [
        (4, 100, 100),
        (5, 100, 100),
        (6, 100, 100),
        (7, 100, 100),
        (8, 100, 100),
        (9, 400, 100),
    ]
    by_cat = spent_vs_expected(session, OCT, "variable", cid)
    assert by_cat[-2].expected == 250  # the user's amount for August wins
