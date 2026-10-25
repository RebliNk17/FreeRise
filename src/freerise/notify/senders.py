import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.models import Notification, NotificationDelivery, Setting
from freerise.notify import telegram

log = logging.getLogger("freerise.notify")
SUPPORTED = ("in_app", "telegram")


class Sender(Protocol):
    """Optional attributes: since (datetime) skips older notifications, kinds (list) filters."""

    channel: str

    def send(self, n: Notification) -> None: ...


def enabled_channels(session: Session) -> list[str]:
    v = session.scalar(select(Setting.value).where(Setting.key == "notification_channels"))
    return list(v) if v else ["in_app"]


def telegram_kinds(session: Session) -> set[str]:
    """Kinds that reach a Telegram chat right now (bot linked, channel on)."""
    cfg = telegram.load(session)
    if not cfg.get("chat_id") or "telegram" not in enabled_channels(session):
        return set()
    return set(telegram.kinds_of(cfg))


def build_senders(session: Session) -> list[Sender]:
    # in_app is written by notify() itself
    cfg = telegram.load(session)
    if not (cfg.get("token_enc") and cfg.get("chat_id")):
        return []
    app_url = session.scalar(select(Setting.value).where(Setting.key == "app_url"))
    return [telegram.TelegramSender(cfg, app_url)]


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
        q = select(Notification).where(Notification.id.not_in(done)).order_by(Notification.id)
        if (since := getattr(sender, "since", None)) is not None:
            q = q.where(Notification.created_at >= since)
        if (kinds := getattr(sender, "kinds", None)) is not None:
            q = q.where(Notification.kind.in_(kinds))
        for n in session.scalars(q):
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
