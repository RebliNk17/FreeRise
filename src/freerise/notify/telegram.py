"""Telegram Bot API: the sender and the "connect a chat" flow.

Config lives in one settings row ("telegram"); the bot token is encrypted with CREDENTIALS_KEY.
No webhook: linking reads getUpdates on demand, so it works on a server with no public URL.
"""

import base64
import html
import secrets
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.crypto import decrypt_str, encrypt_str
from freerise.models import Notification, Setting

KEY = "telegram"
ICONS = {"info": "🔔", "warning": "⚠️", "critical": "🚨"}
# Every kind notify/rules.py can create; the settings page lets you pick which reach Telegram.
KINDS = {
    "sync_failed": "סנכרון נכשל",
    "sync_paused": "סנכרון הושהה",
    "large_transaction": "עסקה גדולה",
    "new_recurring": "חיוב קבוע חדש",
    "weekly_allowance_used": "תקציב השבוע נוצל",
    "category_over_expected": "חריגה בקטגוריה",
    "installments_ending": "תשלומים מסתיימים",
    "uncategorized_growing": "עסקאות ממתינות לסיווג",
    "card_bill_mismatch": "חיוב אשראי לא תואם",
    "card_unknown": "חיוב מכרטיס לא מחובר",
    "fees_paid": "עמלות החודש",
    "new_fee": "עמלה חדשה",
    "negative_cycle": "חודש במינוס",
    "low_balance_before_income": "יתרה נמוכה לפני משכורת",
    "pension_reminder": "תזכורת פנסיה",
}


class TelegramError(Exception):
    """Telegram said no; the message is Telegram's description (never contains the token)."""


def call(token: str, method: str, **params) -> dict | list | bool:
    try:
        r = httpx.post(f"https://api.telegram.org/bot{token}/{method}", json=params, timeout=15)
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:  # str(e) may hold the URL, i.e. the token
        raise TelegramError(f"network error ({type(e).__name__})") from None
    if not data.get("ok"):
        raise TelegramError(data.get("description") or f"HTTP {r.status_code}")
    return data["result"]


def load(session: Session) -> dict:
    return dict(session.scalar(select(Setting.value).where(Setting.key == KEY)) or {})


def save(session: Session, cfg: dict | None) -> None:
    row = session.scalar(select(Setting).where(Setting.key == KEY))
    if cfg is None:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(Setting(key=KEY, value=cfg))
    else:
        row.value = cfg  # new dict -> JSONB change is detected
    session.flush()


def token_of(cfg: dict) -> str | None:
    enc = cfg.get("token_enc")
    return decrypt_str(base64.b64decode(enc)) if enc else None


def connect_bot(token: str) -> dict:
    """Check the token with getMe; returns a fresh config (no chat linked yet)."""
    me = call(token, "getMe")
    return {
        "token_enc": base64.b64encode(encrypt_str(token)).decode(),
        "bot_username": me["username"],
        "bot_name": me.get("first_name"),
    }


def new_link_code(cfg: dict) -> str:
    cfg["link_code"] = secrets.token_urlsafe(9)  # t.me/<bot>?start=<code>: [A-Za-z0-9_-]
    return cfg["link_code"]


def find_chat(token: str, code: str) -> dict | None:
    """Look for "/start <code>" in the bot's pending updates; consumes what it read."""
    updates = call(token, "getUpdates", timeout=0, allowed_updates=["message"])
    if updates:
        call(token, "getUpdates", offset=updates[-1]["update_id"] + 1, timeout=0)
    for u in reversed(updates):
        msg = u.get("message") or {}
        parts = (msg.get("text") or "").split()
        # "/start@MyBot code" in a group
        if len(parts) == 2 and parts[0].split("@")[0] == "/start" and parts[1] == code:
            chat = msg["chat"]
            name = chat.get("title") or " ".join(
                filter(None, (chat.get("first_name"), chat.get("last_name")))
            )
            return {"id": chat["id"], "name": name or chat.get("username") or str(chat["id"])}
    return None


def link_chat(cfg: dict, chat: dict) -> None:
    cfg.update(chat_id=chat["id"], chat_name=chat["name"], link_code=None)
    # Only notifications from now on; never flood a new chat with the whole history.
    cfg["since"] = datetime.now(UTC).isoformat()


def format_message(n: Notification, app_url: str | None) -> str:
    text = f"{ICONS.get(n.severity, '🔔')} <b>{html.escape(n.title)}</b>\n{html.escape(n.body)}"
    if app_url and n.link:
        href = html.escape(app_url.rstrip("/") + n.link, quote=True)
        text += f'\n\n<a href="{href}">פתיחה ב-FreeRise ←</a>'
    return text


def send_text(token: str, chat_id: int, text: str) -> None:
    call(
        token,
        "sendMessage",
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        link_preview_options={"is_disabled": True},
    )


class TelegramSender:
    channel = "telegram"

    def __init__(self, cfg: dict, app_url: str | None):
        self.token, self.chat_id, self.app_url = token_of(cfg), cfg["chat_id"], app_url
        self.since = datetime.fromisoformat(cfg["since"]) if cfg.get("since") else None
        self.kinds = cfg.get("kinds")  # None = every kind

    def send(self, n: Notification) -> None:
        send_text(self.token, self.chat_id, format_message(n, self.app_url))
