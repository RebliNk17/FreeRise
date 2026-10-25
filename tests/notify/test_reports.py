from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from freerise.api.routes_notifications import list_notifications, unread_count
from freerise.models import Account, Category, Credential, Notification, Setting, Transaction
from freerise.notify.reports import monthly_report, telegram_feed, weekly_report

SUNDAY = date(2026, 10, 25)  # cycles start on the 10th (default)
_n = 0


def _acct(session):
    cred = Credential(provider="max", label="l", owner="o", secret_enc=b"s")
    a = Account(
        credential=cred,
        provider_account_id="1234",
        kind="card",
        display_name="כרטיס",
        created_at=datetime.now(UTC) - timedelta(days=2),  # not a brand-new connection
    )
    session.add(a)
    session.flush()
    return a


def _tx(session, a, d, amount, desc="m", cat=None, n=None, total=None, original=None):
    global _n
    _n += 1
    cid = cat and session.scalar(select(Category.id).where(Category.name == cat))
    t = Transaction(
        account_id=a.id,
        txn_key=f"r{_n}",
        date=d,
        processed_date=d,
        amount=Decimal(str(amount)),
        original_amount=original and Decimal(str(original)),
        description=desc,
        merchant_key=desc,
        status="completed",
        raw={},
        category_id=cid,
        installment_number=n,
        installment_total=total,
    )
    session.add(t)
    session.flush()
    return t


def _ns(session, kind):
    return list(session.scalars(select(Notification).where(Notification.kind == kind)))


def test_weekly_report_once_on_sunday(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 20), -300, "שופרסל", "כלכלה")
    _tx(session, a, date(2026, 10, 22), "-120.5", "קפה", "אוכל בחוץ")
    _tx(session, a, date(2026, 10, 10), -999, "old", "כלכלה")  # the week before: not in it
    weekly_report(session, SUNDAY)
    weekly_report(session, SUNDAY + timedelta(days=1))  # Monday's run: same week, no repeat
    (n,) = _ns(session, "weekly_report")
    assert n.title == "סיכום שבועי · 18.10–24.10" and n.link == "/home"
    assert "הכי הרבה הלך על: סופר ₪300 · אוכל בחוץ ₪120.5" in n.body
    assert "צפי לסוף החודש" in n.body


def test_weekly_report_skips_empty_and_late(session):
    weekly_report(session, SUNDAY)  # nothing synced
    a = _acct(session)
    _tx(session, a, date(2026, 10, 20), -300, "שופרסל", "כלכלה")
    weekly_report(session, SUNDAY + timedelta(days=3))  # Wednesday: too late for last week
    assert _ns(session, "weekly_report") == []


def test_monthly_report_at_cycle_start(session):
    a = _acct(session)
    _tx(session, a, date(2026, 9, 15), 10000, "משכורת")
    _tx(session, a, date(2026, 9, 20), "-300.4", "שופרסל", "כלכלה")
    monthly_report(session, date(2026, 10, 20))  # mid-cycle: not now
    assert _ns(session, "monthly_report") == []
    monthly_report(session, date(2026, 10, 11))
    monthly_report(session, date(2026, 10, 12))
    (n,) = _ns(session, "monthly_report")
    assert n.title == "סיכום חודש ספטמבר" and n.link == "/home/2026/9"
    lines = n.body.split("\n")
    assert lines[0] == "🎉 סיימתם את ספטמבר בפלוס ₪9,699.6"
    assert "הכי הרבה הלך על: סופר ₪300.4" in lines
    assert "📅 התזרים הצפוי לאוקטובר:" in lines


def _telegram(session, on=True):
    for key, value in (
        (
            "telegram",
            {"chat_id": 1, "kinds": ["new_payment", "installment_new", "installment_ended"]},
        ),
        ("notification_channels", ["in_app", "telegram"] if on else ["in_app"]),
    ):
        row = session.scalar(select(Setting).where(Setting.key == key)) or Setting(key=key)
        row.value = value
        session.add(row)
    session.flush()


def test_telegram_feed(session):
    _telegram(session)
    a = _acct(session)
    telegram_feed(session, SUNDAY)  # first run: just sets the mark
    _tx(session, a, SUNDAY, "-49.9", "שופרסל")
    _tx(session, a, SUNDAY, -100, "איקאה", n=1, total=3, original=-300)
    _tx(session, a, date(2026, 8, 1), -80, "מחשב", n=3, total=3)  # purchase date months ago
    _tx(session, a, SUNDAY, -60, "טלוויזיה", n=2, total=3)  # a deal's middle payment
    _tx(session, a, SUNDAY, 20, "זיכוי")
    session.execute(
        Transaction.__table__.update()
        .where(Transaction.description == "מחשב")
        .values(processed_date=SUNDAY)
    )
    telegram_feed(session, SUNDAY)
    telegram_feed(session, SUNDAY)  # nothing new
    (pay,) = _ns(session, "new_payment")
    assert pay.title == "חיוב חדש" and pay.body.startswith("• שופרסל ₪49.9 · ")
    (deal,) = _ns(session, "installment_new")
    assert deal.body.startswith("איקאה: ₪300 ב-3 תשלומים של ₪100 · ")
    (end,) = _ns(session, "installment_ended")
    assert "התשלום האחרון (3/3) של ₪80" in end.body
    # Telegram only: never in the app's bell
    assert list_notifications(session) == [] and unread_count(session).count == 0


def test_telegram_feed_off_sends_no_backlog(session):
    _telegram(session, on=False)
    a = _acct(session)
    telegram_feed(session, SUNDAY)
    _tx(session, a, SUNDAY, -50, "שופרסל")
    telegram_feed(session, SUNDAY)  # off: skipped, the mark moves on
    _telegram(session, on=True)
    telegram_feed(session, SUNDAY)
    assert _ns(session, "new_payment") == []
    _tx(session, a, SUNDAY, -70, "רמי לוי")
    _tx(session, a, SUNDAY, -30, "קפה")
    telegram_feed(session, SUNDAY)
    (n,) = _ns(session, "new_payment")
    assert n.title == "2 חיובים חדשים" and n.link == "/search"
