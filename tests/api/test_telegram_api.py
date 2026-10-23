import pytest

from freerise.notify import telegram

pytestmark = pytest.mark.usefixtures("restore_settings")


def _fake_telegram(monkeypatch, start_text="/start {code}"):
    sent = []

    def call(token, method, **p):
        assert token == "123456:ABCdefGHIjklMNOpqrSTUvwx"
        if method == "getMe":
            return {"username": "MyFreeRiseBot", "first_name": "FreeRise"}
        if method == "getUpdates":
            code = telegram_state["code"]
            return [
                {
                    "update_id": 1,
                    "message": {
                        "text": start_text.format(code=code),
                        "chat": {"id": 42, "first_name": "Shai"},
                    },
                }
            ]
        if method == "sendMessage":
            sent.append(p)
            return {}
        raise AssertionError(method)

    telegram_state = {}
    monkeypatch.setattr(telegram, "call", call)
    return sent, telegram_state


def test_connect_link_test_disconnect(authed, monkeypatch):
    sent, state = _fake_telegram(monkeypatch)
    r = authed.put("/api/settings/telegram/bot", json={"token": "123456:ABCdefGHIjklMNOpqrSTUvwx"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bot_username"] == "MyFreeRiseBot" and not body["linked"]
    assert body["link_url"] == f"https://t.me/MyFreeRiseBot?start={body['link_code']}"
    assert "token" not in r.text.lower().replace("token_", "")  # token never returned
    state["code"] = body["link_code"]

    r = authed.post("/api/settings/telegram/link").json()
    assert r["linked"] and r["enabled"] and r["chat_name"] == "Shai" and r["link_code"] is None
    assert sent[-1]["chat_id"] == 42

    assert authed.post("/api/settings/telegram/test").status_code == 204
    assert len(sent) == 2

    r = authed.put(
        "/api/settings/telegram", json={"kinds": ["sync_failed"], "enabled": False}
    ).json()
    assert r["kinds"] == ["sync_failed"] and not r["enabled"]
    assert authed.put("/api/settings/telegram", json={"kinds": ["bogus"]}).status_code == 422

    assert authed.delete("/api/settings/telegram").status_code == 204
    r = authed.get("/api/settings/telegram").json()
    assert r["bot_username"] is None and not r["enabled"]


def test_wrong_code_does_not_link(authed, monkeypatch):
    _, state = _fake_telegram(monkeypatch, start_text="/start wrong")
    body = authed.put(
        "/api/settings/telegram/bot", json={"token": "123456:ABCdefGHIjklMNOpqrSTUvwx"}
    ).json()
    state["code"] = body["link_code"]
    assert not authed.post("/api/settings/telegram/link").json()["linked"]


def test_bad_token_rejected(authed, monkeypatch):
    def call(token, method, **p):
        raise telegram.TelegramError("Unauthorized")

    monkeypatch.setattr(telegram, "call", call)
    r = authed.put("/api/settings/telegram/bot", json={"token": "123456:ABCdefGHIjklMNOpqrSTUvwx"})
    assert r.status_code == 502 and "Unauthorized" in r.json()["detail"]
    assert authed.put("/api/settings/telegram/bot", json={"token": "nope"}).status_code == 422


def test_general_settings_roundtrip(authed):
    r = authed.put(
        "/api/settings",
        json={
            "sync_hours": [21, 7, 7],
            "digest_hour": 8,
            "large_txn_min": 2000,
            "app_url": "https://x.dev/",
        },
    ).json()
    assert r["sync_hours"] == [7, 21] and r["digest_hour"] == 8 and r["app_url"] == "https://x.dev"
    assert authed.put("/api/settings", json={"sync_hours": [24]}).status_code == 422
    assert authed.put("/api/settings", json={"app_url": "javascript:x"}).status_code == 422
    authed.put(
        "/api/settings",
        json={"sync_hours": [7, 14, 21], "digest_hour": 9, "large_txn_min": 1500, "app_url": None},
    )
