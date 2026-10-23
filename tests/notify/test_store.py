from datetime import timedelta

from sqlalchemy import select

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
    msg = telegram.format_message(n, "https://fr.example/")
    assert msg.startswith("⚠️ <b>&lt;a&gt;</b>\nx &amp; y")
    assert 'href="https://fr.example/home"' in msg
    assert "href" not in telegram.format_message(n, None)


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
