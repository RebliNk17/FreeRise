from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.models import Notification, NotificationDelivery


def notify(
    session: Session,
    kind: str,
    title: str,
    body: str,
    link: str | None,
    dedup_key: str,
    severity: str = "info",
) -> Notification | None:
    """Create a notification (+ sent in_app delivery); None if dedup_key already exists."""
    if session.scalar(select(Notification.id).where(Notification.dedup_key == dedup_key)):
        return None
    n = Notification(
        kind=kind, severity=severity, title=title, body=body, link=link, dedup_key=dedup_key
    )
    session.add(n)
    session.flush()
    session.add(
        NotificationDelivery(
            notification_id=n.id, channel="in_app", status="sent", sent_at=datetime.now(UTC)
        )
    )
    session.flush()
    return n
