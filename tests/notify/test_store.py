import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

import freerise
from freerise.models import Notification, NotificationDelivery, Setting
from freerise.notify import telegram
from freerise.notify.senders import deliver_pending
from freerise.notify.store import notify


def _n(session, key="k"):
    return notify(session, "kind", "כותרת", "גוף", "/home", key)


def test_notify_creates_in_app_delivery_and_dedups(session):
    n = _n(session)
    assert n.severity == "info"
    d = session.scalar(
        select(NotificationDelivery).where(NotificationDelivery.notification_id == n.id)
    )
    assert (d.channel, d.status) == ("in_app", "sent")
    assert _n(session) is None
    assert session.scalar(select(Notification.id).where(Notification.dedup_key == "k")) == n.id


class Fake:
    channel = "fake"

    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, n):
        if self.fail:
            raise RuntimeError("x")
        self.sent.append(n.id)


def test_deliver_pending_skips_disabled_channels(session):
    n = _n(session)
    f = Fake()
    assert deliver_pending(session, [f]) == 0
    assert f.sent == []
    session.add(Setting(key="notification_channels", value=["in_app", "fake"]))
    session.flush()
    assert deliver_pending(session, [f]) == 1
    assert f.sent == [n.id]
    assert deliver_pending(session, [f]) == 0  # already sent


def test_deliver_failure_recorded_and_retried(session):
    _n(session)
    session.add(Setting(key="notification_channels", value=["fake"]))
    session.flush()
    deliver_pending(session, [Fake(fail=True)])
    d = session.scalar(select(NotificationDelivery).where(NotificationDelivery.channel == "fake"))
    assert (d.status, d.error) == ("failed", "RuntimeError")
    assert deliver_pending(session, [Fake()]) == 1
    assert d.status == "sent"


def test_deliver_respects_since_and_kinds(session):
    old = _n(session, "old")
    session.add(Setting(key="notification_channels", value=["fake"]))
    session.flush()
    f = Fake()
    f.since = old.created_at + timedelta(seconds=1)
    assert deliver_pending(session, [f]) == 0
    f.since, f.kinds = None, ["other"]
    assert deliver_pending(session, [f]) == 0
    f.kinds = ["kind"]
    assert deliver_pending(session, [f]) == 1


def test_telegram_format_escapes_and_links(session):
    n = notify(session, "k", "<a>", "x & y", "/home", "t", "warning")
    msg = telegram.format_message(n, "https://fr.example/home")
    assert msg.startswith("⚠️ <b>&lt;a&gt;</b>\nx &amp; y")
    assert 'href="https://fr.example/home"' in msg
    assert "href" not in telegram.format_message(n)


def test_telegram_format_kind_emoji_and_bold_amounts(session):
    n = notify(session, "weekly_report", "סיכום", "הוצאתם ₪1,234.5, יותר מ-₪2,000 -₪3", None, "w")
    assert telegram.format_message(n) == (
        "📊 <b>סיכום</b>\nהוצאתם <b>₪1,234.5</b>, יותר מ-<b>₪2,000</b> <b>-₪3</b>"
    )


def test_telegram_link_button_falls_back_to_text_link(session, monkeypatch):
    n = notify(session, "sync_failed", "t", "b", "/accounts?edit=3", "s", "critical")
    sent = []

    def call(token, method, **p):
        if "reply_markup" in p and "localhost" in str(p):
            raise telegram.TelegramError("Bad Request: BUTTON_URL_INVALID")
        sent.append(p)

    monkeypatch.setattr(telegram, "call", call)
    cfg = {"chat_id": 1, "token_enc": None}
    telegram.TelegramSender(cfg, "https://fr.example").send(n)
    button = sent[-1]["reply_markup"]["inline_keyboard"][0][0]
    assert button == {"text": "לתיקון החיבור", "url": "https://fr.example/accounts?edit=3"}
    telegram.TelegramSender(cfg, "http://localhost:3000").send(n)
    assert "reply_markup" not in sent[-1]
    assert 'href="http://localhost:3000/accounts?edit=3"' in sent[-1]["text"]


def test_find_chat_matches_code_only(monkeypatch):
    calls = []

    def call(token, method, **p):
        calls.append(p)
        return [
            {"update_id": 5, "message": {"text": "/start nope", "chat": {"id": 1}}},
            {
                "update_id": 6,
                "message": {"text": "/start@Bot abc", "chat": {"id": 2, "first_name": "Dana"}},
            },
        ]

    monkeypatch.setattr(telegram, "call", call)
    assert telegram.find_chat("t", "abc") == {"id": 2, "name": "Dana"}
    assert calls[1]["offset"] == 7  # read updates are acknowledged
    assert telegram.find_chat("t", "zzz") is None


def test_every_alert_kind_can_reach_telegram():
    """Telegram's default list is KINDS minus the feed: a kind left out is silently never sent."""
    src = Path(freerise.__file__).parent.rglob("*.py")
    made = {k for p in src for k in re.findall(r'notify\(\s*\w+,\s*"(\w+)"', p.read_text())}
    assert made and made <= telegram.KINDS.keys()
