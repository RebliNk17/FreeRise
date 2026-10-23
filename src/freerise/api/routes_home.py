from typing import Annotated

from fastapi import APIRouter, Path
from fastapi.encoders import jsonable_encoder

from freerise.api.deps import DB, today
from freerise.cashflow.cycles import Cycle, cycle_by_label, cycle_for, get_start_day
from freerise.home.builder import build_home
from freerise.view import hiding

router = APIRouter()


def _home(db: DB, c: Cycle) -> dict:
    out = jsonable_encoder(build_home(db, c, today()))  # Decimal -> number
    db.commit()  # first call seeds default tracking
    return out


@router.get("/home/current")
def home_current(db: DB, hide_accounts: str | None = None) -> dict:
    with hiding(hide_accounts):
        return _home(db, cycle_for(today(), get_start_day(db)))


@router.get("/home/{year}/{month}")
def home_for(
    db: DB,
    year: Annotated[int, Path(ge=2000, le=2100)],
    month: Annotated[int, Path(ge=1, le=12)],
    hide_accounts: str | None = None,
) -> dict:
    with hiding(hide_accounts):
        return _home(db, cycle_by_label(year, month, get_start_day(db)))
