from datetime import date
from decimal import Decimal

from sqlalchemy import select

from freerise.cashflow.cycles import cycle_by_label
from freerise.cashflow.summary import cycle_history, cycle_summary
from freerise.models import Account, Category, Credential, RecurringItem, Transaction

C = cycle_by_label(2026, 10, 10)  # 2026-10-10..2026-11-09
_n = 0


def acct(session, kind="bank", excluded=False):
    global _n
    _n += 1
    cred = Credential(provider="x", label="l", owner="o", secret_enc=b"")
    session.add(cred)
    session.flush()
    a = Account(
        credential_id=cred.id,
        provider_account_id=str(_n),
        kind=kind,
        display_name="a",
        excluded=excluded,
    )
    session.add(a)
    session.flush()
    return a


def tx(session, a, amount, cat=None, d=date(2026, 10, 15), status="completed", key=""):
    global _n
    _n += 1
    cid = session.scalar(select(Category.id).where(Category.name == cat)) if cat else None
    session.add(
        Transaction(
            account_id=a.id,
            txn_key=str(_n),
            date=d,
            processed_date=d,
            amount=Decimal(amount),
            description="d",
            status=status,
            category_id=cid,
            merchant_key=key,
            raw={},
        )
    )
    session.flush()


def test_summary_income_spending_net(session):
    a = acct(session)
    tx(session, a, 10000, "משכורת")
    tx(session, a, 200, None)  # uncategorized positive -> income
    tx(session, a, -3000, "משכנתא")
    tx(session, a, -400, "כלכלה")
    tx(session, a, 50, "כלכלה", status="pending")  # refund nets spending
    tx(session, a, -100, None)  # uncategorized expense -> variable
    tx(session, a, -500, "השקעה וחיסכון")
    tx(session, a, -999, "כלכלה", d=date(2026, 11, 10))  # next cycle
    s = cycle_summary(session, C)
    assert s.income == Decimal(10200)
    assert s.spending == Decimal(3000 + 350 + 100 + 500)
    assert s.net == Decimal(10200 - 3950)
    assert s.verdict == "positive"
    g = {x.group: x for x in s.groups}
    assert g["variable"].total == Decimal(450)
    assert g["savings"].total == Decimal(500)
    assert s.uncategorized_count == 2 and s.uncategorized_total == Decimal(300)
    assert s.pending_count == 1


def test_excluded_account_ignored(session):
    tx(session, acct(session, excluded=True), -700, "כלכלה")
    s = cycle_summary(session, C)
    assert s.spending == 0 and s.income == 0


def test_card_bill_not_double_counted(session):
    tx(session, acct(session, "card"), -500, "כלכלה")
    tx(session, acct(session), -500, "חיוב כרטיס אשראי")
    s = cycle_summary(session, C)
    assert s.spending == Decimal(500)


def test_transfer_ignored(session):
    a = acct(session)
    tx(session, a, -800, "העברות")
    tx(session, a, 800, "העברות")
    tx(session, a, -5, "להתעלם")
    s = cycle_summary(session, C)
    assert s.spending == 0 and s.income == 0 and s.verdict == "positive"


def test_history_returns_n_cycles(session):
    a = acct(session)
    tx(session, a, -100, "כלכלה", d=date(2026, 9, 20))
    h = cycle_history(session, C, 3)
    assert [c.start for c, _ in h] == [date(2026, 8, 10), date(2026, 9, 10), date(2026, 10, 10)]
    assert [n for _, n in h] == [0, Decimal(-100), 0]


def test_income_split_fixed_and_variable(session):
    for key, status in (("salary", "confirmed"), ("bonus", "dismissed")):
        session.add(
            RecurringItem(
                merchant_key=key,
                direction="income",
                label=key,
                cadence="monthly",
                amount_kind="fixed",
                expected_amount=Decimal(10000),
                last_date=date(2026, 9, 15),
                next_expected_date=date(2026, 10, 15),
                status=status,
                basis="b",
            )
        )
    a = acct(session)
    tx(session, a, 10000, "משכורת", key="salary")
    tx(session, a, 700, None, key="friend")  # one-off transfer-in
    tx(session, a, 300, "משכורת", key="bonus")  # dismissed recurring -> variable
    tx(session, a, -50, "כלכלה", key="salary")  # expense with same key: not income
    s = cycle_summary(session, C)
    assert s.income == Decimal(11000)
    assert s.income_fixed == Decimal(10000)
    assert s.income_variable == Decimal(1000)


def test_confirmed_recurring_expense_counts_as_fixed(session):
    a = acct(session)
    session.add(
        RecurringItem(
            merchant_key="ליסינג רכב",
            direction="expense",
            label="ליסינג רכב",
            cadence="monthly",
            amount_kind="fixed",
            expected_amount=Decimal("1500"),
            last_date=date(2026, 9, 1),
            next_expected_date=date(2026, 11, 1),
            status="confirmed",
            basis="b",
        )
    )
    tx(session, a, -1500, "רכב", key="ליסינג רכב")
    tx(session, a, -80, "רכב", key="דלק")
    by = {g.group: g.total for g in cycle_summary(session, C).groups}
    assert (by["fixed"], by["variable"]) == (Decimal("1500"), Decimal(80))
