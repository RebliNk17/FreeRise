import json
from datetime import date

import httpx
import pytest
from test_phase2_routes import _txn, ids  # noqa: F401 - fixture

from freerise import chat

ENV = ("FREERISE_LLM_BASE_URL", "FREERISE_LLM_API_KEY", "FREERISE_LLM_MODEL")


@pytest.fixture
def no_llm(monkeypatch):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)


def test_chat_off_by_default(authed, no_llm):
    assert authed.get("/api/chat/status").json() == {"enabled": False}
    r = authed.post("/api/chat", json={"messages": [{"role": "user", "content": "כמה הוצאתי?"}]})
    assert r.status_code == 503


def test_chat_sends_aggregates_only(authed, ids, sf, monkeypatch):  # noqa: F811
    for k, v in zip(ENV, ("https://llm.test/v1/", "test-key", "test-model"), strict=True):
        monkeypatch.setenv(k, v)
    _txn(
        sf, ids["card"], date(2026, 9, 15), -321, "Secret Shop 4580-1234", cat=ids["cats"]["כלכלה"]
    )
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": " 321 ₪ "}}]})

    real = httpx.Client
    monkeypatch.setattr(
        chat.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler))
    )
    assert authed.get("/api/chat/status").json() == {"enabled": True}
    r = authed.post("/api/chat", json={"messages": [{"role": "user", "content": "כמה על סופר?"}]})
    assert r.json() == {"reply": "321 ₪"}
    assert seen["url"] == "https://llm.test/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key" and seen["body"]["model"] == "test-model"
    system, user = seen["body"]["messages"]
    assert user == {"role": "user", "content": "כמה על סופר?"}
    assert "previous_cycles" in system["content"] and "כלכלה" in system["content"]
    assert "Secret Shop" not in system["content"] and "1234" not in system["content"]


def test_chat_upstream_error_is_502(authed, monkeypatch):
    for k, v in zip(ENV, ("https://llm.test/v1", "k", "m"), strict=True):
        monkeypatch.setenv(k, v)
    real = httpx.Client
    monkeypatch.setattr(
        chat.httpx,
        "Client",
        lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
    )
    r = authed.post("/api/chat", json={"messages": [{"role": "user", "content": "?"}]})
    assert r.status_code == 502
