from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from freerise.models import (
    Account,
    Category,
    Credential,
    Notification,
    RecurringItem,
    SyncRun,
    Transaction,
)
from freerise.notify.rules import generate_notifications
from freerise.notify.store import notify

TODAY = date(2026, 10, 23)
_n = 0


def _acct(session, excluded=False, provider="x"):
    cred = Credential(provider=provider, label="l", owner="o", secret_enc=b"s")
    a = Account(
        credential=cred, provider_account_id="1", kind="bank", display_name="a", excluded=excluded
    )
    session.add(a)
    session.flush()
    return a


def _cat(session, name):
    return session.scalar(select(Category.id).where(Category.name == name))


def _tx(session, a, d, amount, cat=None, desc="m"):
    global _n
    _n += 1
    t = Transaction(
        account_id=a.id,
        txn_key=f"k{_n}",
        date=d,
        processed_date=d,
        amount=Decimal(str(amount)),
        description=desc,
        merchant_key=desc,
        status="completed",
        raw={},
        category_id=cat,
    )
    session.add(t)
    session.flush()
    return t


def _kinds(session):
    return sorted(session.scalars(select(Notification.kind)))


def _fires_once(session, kind):
    generate_notifications(session, TODAY)
    assert _kinds(session).count(kind) == 1
    generate_notifications(session, TODAY)
    assert _kinds(session).count(kind) == 1


def test_sync_failed_fires_once(session):
    a = _acct(session)
    for st, fk in (("failed", "auth_failed"), ("otp_timeout", None), ("success", None)):
        session.add(
            SyncRun(
                credential_id=a.credential_id,
                trigger="manual",
                status=st,
                failure_kind=fk,
                finished_at=datetime(2026, 10, 22, 8, tzinfo=UTC),
            )
        )
    # too old
    session.add(
        SyncRun(
            credential_id=a.credential_id,
            trigger="manual",
            status="failed",
            finished_at=datetime(2026, 10, 1, tzinfo=UTC),
        )
    )
    session.flush()
    generate_notifications(session, TODAY)
    assert _kinds(session) == ["sync_failed", "sync_failed"]
    bodies = set(
        session.scalars(select(Notification.body).where(Notification.kind == "sync_failed"))
    )
    assert bodies == {"סיסמה שגויה", "לא הוזן קוד"}  # legacy otp_timeout run without a kind
    generate_notifications(session, TODAY)
    assert len(_kinds(session)) == 2


def test_auth_failure_on_disabled_credential_notifies(session):
    a = _acct(session)
    a.credential.enabled = False  # run_credential auto-disables on wrong password
    session.add(
        SyncRun(
            credential_id=a.credential_id,
            trigger="schedule",
            status="failed",
            failure_kind="auth_failed",
            finished_at=datetime(2026, 10, 22, 8, tzinfo=UTC),
        )
    )
    session.flush()
    _fires_once(session, "sync_failed")
    body = session.scalar(select(Notification.body).where(Notification.kind == "sync_failed"))
    assert "סיסמה שגויה" in body and "הסנכרון הושבת — יש לעדכן סיסמה" in body


def test_sync_failed_blocked_is_not_site_changed(session):
    a = _acct(session)
    session.add(
        SyncRun(
            credential_id=a.credential_id,
            trigger="schedule",
            status="failed",
            failure_kind="provider_changed",
            error="AUTOMATION_BLOCKED: login failed: WAF",
            finished_at=datetime(2026, 10, 22, 8, tzinfo=UTC),
        )
    )
    session.flush()
    _fires_once(session, "sync_failed")
    body = session.scalar(select(Notification.body).where(Notification.kind == "sync_failed"))
    assert body == "הספק חוסם זמנית חיבור אוטומטי"


def test_weekly_allowance_used_fires_once(session):
    a = _acct(session)
    # income gives an allowance; heavy variable spending this week uses it up
    _tx(session, a, date(2026, 10, 12), 10000, _cat(session, "משכורת"))
    _tx(session, a, TODAY, -9000, _cat(session, "כלכלה"))
    _fires_once(session, "weekly_allowance_used")


def test_category_over_expected_fires_once(session):
    a = _acct(session)
    cat = _cat(session, "כלכלה")
    for m in (5, 6, 7, 8, 9):
        _tx(session, a, date(2026, m, 15), -1000, cat)
    _tx(session, a, date(2026, 10, 15), -2500, cat)
    _fires_once(session, "category_over_expected")


def test_installments_ending_fires_once(session):
    a = _acct(session)
    t = _tx(session, a, date(2026, 10, 15), -300)
    t.installment_number = t.installment_total = 6
    session.flush()
    _fires_once(session, "installments_ending")
    n = session.scalar(select(Notification).where(Notification.kind == "installments_ending"))
    assert n.body.startswith("תשלום אחרון אחד במחזור הזה")


def test_large_transaction_fires_once(session):
    a = _acct(session)
    _tx(session, a, TODAY - timedelta(days=1), -4000, desc="big")
    _tx(session, a, TODAY - timedelta(days=1), -1000, desc="small")
    _tx(session, a, TODAY - timedelta(days=10), -9000, desc="old")
    _fires_once(session, "large_transaction")


def test_large_transaction_uses_category_median_and_skips_excluded(session):
    a = _acct(session)
    cat = _cat(session, "כלכלה")
    for m in (5, 6, 7):
        _tx(session, a, date(2026, m, 3), -1000, cat)
    _tx(session, a, TODAY, -2900, cat)  # < 3 * 1000 median -> no alert
    ex = _acct(session, excluded=True)
    _tx(session, ex, TODAY, -9000)
    generate_notifications(session, TODAY)
    assert "large_transaction" not in _kinds(session)


def test_uncategorized_growing_fires_once(session):
    a = _acct(session)
    for _ in range(21):
        _tx(session, a, TODAY, -10)
    _fires_once(session, "uncategorized_growing")


def test_pension_reminder_fires_once(session):
    _acct(session, provider="mislaka")
    _fires_once(session, "pension_reminder")
    a2 = _acct(session, provider="mislaka")
    session.add(
        SyncRun(
            credential_id=a2.credential_id,
            trigger="manual",
            status="success",
            finished_at=datetime(2026, 10, 15, tzinfo=UTC),
        )
    )
    session.flush()
    generate_notifications(session, TODAY)
    assert _kinds(session).count("pension_reminder") == 1


def test_pension_reminder_not_before_21st(session):
    _acct(session, provider="mislaka")
    generate_notifications(session, date(2026, 10, 20))
    assert "pension_reminder" not in _kinds(session)


def test_failing_rule_does_not_stop_others(session, monkeypatch):
    from freerise.notify import rules

    def boom(s, today):
        notify(s, "boom", "t", "b", None, "boom:1")
        raise RuntimeError

    def ok(s, today):
        notify(s, "ok", "t", "b", None, "ok:1")

    monkeypatch.setattr(rules, "RULES", (boom, ok))
    session.add(
        RecurringItem(
            merchant_key="k",
            direction="expense",
            label="l",
            cadence="monthly",
            amount_kind="fixed",
            expected_amount=Decimal(5),
            last_date=TODAY,
            next_expected_date=TODAY,
            status="pending",
            basis="b",
        )
    )
    session.flush()
    assert generate_notifications(session, TODAY) == 1
    assert _kinds(session) == ["ok"]


def test_disabled_credentials_skip_pension_reminder(session):
    a = _acct(session, provider="mislaka")
    a.credential.enabled = False
    session.add(
        SyncRun(
            credential_id=a.credential_id,
            trigger="manual",
            status="failed",
            finished_at=datetime(2026, 10, 22, tzinfo=UTC),
        )
    )
    session.flush()
    generate_notifications(session, TODAY)
    # no pension_reminder; the failed run still notifies (auth failures disable the credential)
    assert _kinds(session) == ["sync_failed"]


def test_large_transaction_link_encoded(session):
    a = _acct(session)
    _tx(session, a, TODAY, -4000, desc="a&b #1")
    generate_notifications(session, TODAY)
    assert session.scalar(select(Notification.link)) == "/search?q=a%26b+%231"


def test_fees_paid_and_new_fee_fire_once(session):
    a = _acct(session)
    fees = _cat(session, "עמלות")
    _tx(session, a, date(2026, 8, 1), "-50", desc="old")  # account has history
    _tx(session, a, date(2026, 9, 12), "-6.90", fees, desc="עמלת פעולה 12 09")  # prev cycle
    _tx(session, a, date(2026, 10, 12), "-6.90", fees, desc="עמלת פעולה 12 10")  # not new
    for i, d in enumerate(("עמלת המרה", "דמי כרטיס", "ריבית חובה", "עמלת משיכה")):
        _tx(session, a, date(2026, 10, 20), "-1", fees, desc=f"{d} {i}0 10")
    _fires_once(session, "fees_paid")
    assert _kinds(session).count("new_fee") == 1
    n = session.scalar(select(Notification).where(Notification.kind == "fees_paid"))
    assert n.body == "עד כה החודש שילמתם ₪10.90 עמלות ב-5 חיובים (a)"
    assert n.link == "/home/2026/10" and n.severity == "info"
    new = session.scalar(select(Notification).where(Notification.kind == "new_fee"))
    assert new.title == "עמלות חדשות" and new.body.endswith(" ועוד 1")
    assert new.body.startswith("עמלת המרה 00 10 ₪1.00 (a), דמי כרטיס 10 10 ₪1.00 (a)")


def test_new_fee_burst_guard(session):
    a = _acct(session)  # freshly connected: no transactions before the previous cycle
    _tx(session, a, date(2026, 10, 12), "-6.90", _cat(session, "עמלות"), desc="עמלת פעולה")
    generate_notifications(session, TODAY)
    n = session.scalar(select(Notification).where(Notification.kind == "fees_paid"))
    assert n.body == "עד כה החודש שילמתם ₪6.90 עמלות בחיוב אחד (a)"
    assert "new_fee" not in _kinds(session)
