from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from freerise.api.deps import DB
from freerise.forecast.attribution import attribute_income
from freerise.models import Setting

router = APIRouter()

DEFAULTS = {"cycle_start_day": 10, "month_end_goal_default": 0, "income_grace_days": 10}


class SettingsOut(BaseModel):
    cycle_start_day: int
    month_end_goal_default: float
    income_grace_days: int  # how far off its day a fixed income may land and still count


class SettingsIn(BaseModel):
    cycle_start_day: int | None = Field(None, ge=1, le=28)
    month_end_goal_default: float | None = Field(None, ge=0)
    income_grace_days: int | None = Field(None, ge=0, le=15)


def _get(db: DB) -> SettingsOut:
    vals = dict(
        db.execute(select(Setting.key, Setting.value).where(Setting.key.in_(DEFAULTS))).all()
    )
    return SettingsOut(**{k: vals.get(k, d) for k, d in DEFAULTS.items()})


@router.get("/settings")
def get_settings(db: DB) -> SettingsOut:
    return _get(db)


@router.put("/settings")
def put_settings(body: SettingsIn, db: DB) -> SettingsOut:
    for k, v in body.model_dump(exclude_none=True).items():
        row = db.scalar(select(Setting).where(Setting.key == k))
        if row is None:
            db.add(Setting(key=k, value=v))
        else:
            row.value = v
    db.flush()
    attribute_income(db)  # cycle boundaries / grace may have changed
    db.commit()
    return _get(db)
