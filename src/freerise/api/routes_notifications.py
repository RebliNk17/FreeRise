from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update

from freerise.api.deps import DB, get_or_404
from freerise.models import Notification

router = APIRouter()


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    kind: str
    severity: Literal["info", "warning", "critical"]
    title: str
    body: str
    link: str | None
    read_at: datetime | None


class Count(BaseModel):
    count: int


@router.get("/notifications")
def list_notifications(
    db: DB, unread_only: bool = False, limit: Annotated[int, Query(ge=1, le=500)] = 50
) -> list[NotificationOut]:
    q = select(Notification).order_by(Notification.created_at.desc(), Notification.id.desc())
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    return list(db.scalars(q.limit(limit)))


@router.get("/notifications/unread-count")
def unread_count(db: DB) -> Count:
    n = db.scalar(select(func.count()).where(Notification.read_at.is_(None)))
    return Count(count=n)


@router.post("/notifications/{id}/read", status_code=204)
def mark_read(id: int, db: DB) -> None:
    n = get_or_404(db, Notification, id)
    n.read_at = n.read_at or datetime.now(UTC)
    db.commit()


@router.post("/notifications/read-all", status_code=204)
def mark_all_read(db: DB) -> None:
    db.execute(
        update(Notification).where(Notification.read_at.is_(None)).values(read_at=datetime.now(UTC))
    )
    db.commit()
