from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from freerise.api.deps import DB
from freerise.forecast.attribution import attribute_income
from freerise.models import Setting
from freerise.notify import telegram as tg
from freerise.notify.senders import enabled_channels

router = APIRouter()

DEFAULTS = {
    "cycle_start_day": 10,
    "month_end_goal_default": 0,
    "income_grace_days": 10,
    "large_txn_min": 1500,
    "sync_hours": [7, 14, 21],
    "digest_hour": 9,
    "app_url": None,
}


class SettingsOut(BaseModel):
    cycle_start_day: int
    month_end_goal_default: float
    income_grace_days: int  # how far off its day a fixed income may land and still count
    large_txn_min: float  # floor for the "large transaction" alert
    sync_hours: list[int]  # automatic sync times (local hours); empty = manual only
    digest_hour: int  # daily notification check
    app_url: str | None  # public address of this app, for links in Telegram messages


class SettingsIn(BaseModel):
    cycle_start_day: int | None = Field(None, ge=1, le=28)
    month_end_goal_default: float | None = Field(None, ge=0)
    income_grace_days: int | None = Field(None, ge=0, le=15)
    large_txn_min: float | None = Field(None, ge=0)
    sync_hours: list[int] | None = Field(None, max_length=24)
    digest_hour: int | None = Field(None, ge=0, le=23)
    app_url: str | None = Field(None, max_length=200, pattern=r"^(https?://\S+)?$")


def _get(db: DB) -> SettingsOut:
    vals = dict(
        db.execute(select(Setting.key, Setting.value).where(Setting.key.in_(DEFAULTS))).all()
    )
    return SettingsOut(**{k: vals.get(k, d) for k, d in DEFAULTS.items()})


def _put(db: DB, k: str, v: object) -> None:
    row = db.scalar(select(Setting).where(Setting.key == k))
    if row is None:
        db.add(Setting(key=k, value=v))
    else:
        row.value = v


@router.get("/settings")
def get_settings(db: DB) -> SettingsOut:
    return _get(db)


@router.put("/settings")
def put_settings(body: SettingsIn, db: DB) -> SettingsOut:
    vals = body.model_dump(exclude_unset=True)
    if "sync_hours" in vals:
        if any(not 0 <= h <= 23 for h in vals["sync_hours"] or []):
            raise HTTPException(422, "sync_hours must be 0-23")
        vals["sync_hours"] = sorted(set(vals["sync_hours"] or []))
    if "app_url" in vals:
        vals["app_url"] = (vals["app_url"] or "").rstrip("/") or None
    for k, v in vals.items():
        if v is not None or k == "app_url":
            _put(db, k, v)
    db.flush()
    attribute_income(db)  # cycle boundaries / grace may have changed
    db.commit()
    return _get(db)


# --- Telegram ---


class TelegramOut(BaseModel):
    bot_username: str | None = None
    bot_name: str | None = None
    chat_name: str | None = None
    linked: bool = False
    enabled: bool = False
    kinds: list[str] | None = None  # None = all
    link_code: str | None = None
    link_url: str | None = None
    all_kinds: dict[str, str] = tg.KINDS


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=100, pattern=r"^\d+:[\w-]+$")


class TelegramIn(BaseModel):
    enabled: bool | None = None
    kinds: list[str] | None = None


def _tg_out(db: DB, cfg: dict) -> TelegramOut:
    code, bot = cfg.get("link_code"), cfg.get("bot_username")
    return TelegramOut(
        bot_username=bot,
        bot_name=cfg.get("bot_name"),
        chat_name=cfg.get("chat_name"),
        linked=bool(cfg.get("chat_id")),
        enabled="telegram" in enabled_channels(db),
        kinds=cfg.get("kinds"),
        link_code=code,
        link_url=f"https://t.me/{bot}?start={code}" if bot and code else None,
    )


def _set_enabled(db: DB, on: bool) -> None:
    chans = [c for c in enabled_channels(db) if c != "telegram"] + (["telegram"] if on else [])
    _put(db, "notification_channels", chans)


def _token(cfg: dict) -> str:
    if not cfg.get("token_enc"):
        raise HTTPException(409, "no bot connected")
    return tg.token_of(cfg)


def _tg_error(e: tg.TelegramError) -> HTTPException:
    return HTTPException(502, f"Telegram: {e}")


@router.get("/settings/telegram")
def get_telegram(db: DB) -> TelegramOut:
    return _tg_out(db, tg.load(db))


@router.put("/settings/telegram/bot")
def connect_bot(body: TokenIn, db: DB) -> TelegramOut:
    """Save (or replace) the bot token; starts a chat-link code right away."""
    try:
        cfg = tg.connect_bot(body.token.strip())
    except tg.TelegramError as e:
        raise _tg_error(e) from None
    tg.new_link_code(cfg)
    tg.save(db, cfg)
    _set_enabled(db, False)
    db.commit()
    return _tg_out(db, cfg)


@router.post("/settings/telegram/link")
def check_link(db: DB) -> TelegramOut:
    """Poll from the UI while waiting for the user to press Start in Telegram."""
    cfg = tg.load(db)
    token = _token(cfg)
    if not cfg.get("link_code"):
        tg.new_link_code(cfg)
    else:
        try:
            chat = tg.find_chat(token, cfg["link_code"])
        except tg.TelegramError as e:
            raise _tg_error(e) from None
        if chat:
            tg.link_chat(cfg, chat)
            _set_enabled(db, True)
            try:
                tg.send_text(
                    token, chat["id"], "✅ <b>FreeRise מחובר</b>\nמעכשיו ההתראות יגיעו לכאן."
                )
            except tg.TelegramError:
                pass  # linked anyway; the test button will show the error
    tg.save(db, cfg)
    db.commit()
    return _tg_out(db, cfg)


@router.post("/settings/telegram/relink")
def relink(db: DB) -> TelegramOut:
    """Move notifications to another chat: new code, the current chat stays until it is used."""
    cfg = tg.load(db)
    _token(cfg)
    tg.new_link_code(cfg)
    tg.save(db, cfg)
    db.commit()
    return _tg_out(db, cfg)


@router.put("/settings/telegram")
def put_telegram(body: TelegramIn, db: DB) -> TelegramOut:
    cfg = tg.load(db)
    if body.enabled is not None:
        if body.enabled and not cfg.get("chat_id"):
            raise HTTPException(409, "no chat linked")
        _set_enabled(db, body.enabled)
    if "kinds" in body.model_fields_set:
        if body.kinds is not None and set(body.kinds) - tg.KINDS.keys():
            raise HTTPException(422, "unknown kind")
        cfg["kinds"] = body.kinds
        tg.save(db, cfg)
    db.commit()
    return _tg_out(db, cfg)


@router.post("/settings/telegram/test", status_code=204)
def test_telegram(db: DB) -> None:
    cfg = tg.load(db)
    token = _token(cfg)
    if not cfg.get("chat_id"):
        raise HTTPException(409, "no chat linked")
    try:
        tg.send_text(token, cfg["chat_id"], "🧪 <b>הודעת בדיקה מ-FreeRise</b>\nהחיבור עובד.")
    except tg.TelegramError as e:
        raise _tg_error(e) from None


@router.delete("/settings/telegram", status_code=204)
def delete_telegram(db: DB) -> None:
    tg.save(db, None)
    _set_enabled(db, False)
    db.commit()
