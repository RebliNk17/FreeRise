from sqlalchemy import select

from freerise.models import Notification, NotificationDelivery, Setting
from freerise.notify.senders import TelegramSender, deliver_pending
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


def test_telegram_placeholder_raises(session):
    n = _n(session)
    try:
        TelegramSender().send(n)
    except NotImplementedError:
        return
    raise AssertionError
