import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.models import Notification, NotificationDelivery, Setting

log = logging.getLogger("freerise.notify")
SUPPORTED = ("in_app",)  # extend with "telegram" once TelegramSender is implemented


class Sender(Protocol):
    channel: str

    def send(self, n: Notification) -> None: ...


class TelegramSender:
    """Placeholder; not registered by default."""

    channel = "telegram"

    def send(self, n: Notification) -> None:
        raise NotImplementedError


def enabled_channels(session: Session) -> list[str]:
    v = session.scalar(select(Setting.value).where(Setting.key == "notification_channels"))
    return list(v) if v else ["in_app"]


def build_senders(session: Session) -> list[Sender]:
    return []  # ponytail: in_app is written by notify(); add Telegram here when it exists


def deliver_pending(session: Session, senders: list[Sender]) -> int:
    """Send every notification not yet delivered on each enabled non-in-app channel."""
    enabled = set(enabled_channels(session))
    count = 0
    for sender in senders:
        if sender.channel == "in_app" or sender.channel not in enabled:
            continue
        done = select(NotificationDelivery.notification_id).where(
            NotificationDelivery.channel == sender.channel,
            NotificationDelivery.status == "sent",
        )
        for n in session.scalars(select(Notification).where(Notification.id.not_in(done))):
            d = session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.notification_id == n.id,
                    NotificationDelivery.channel == sender.channel,
                )
            ) or NotificationDelivery(notification_id=n.id, channel=sender.channel)
            session.add(d)
            try:
                sender.send(n)
                d.status, d.sent_at, d.error = "sent", datetime.now(UTC), None
                count += 1
            except Exception as e:  # noqa: BLE001 - one bad delivery must not stop the rest
                d.status, d.error = "failed", type(e).__name__
                log.warning("delivery via %s failed: %s", sender.channel, type(e).__name__)
        session.flush()
    return count
