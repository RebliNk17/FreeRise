import json

import httpx
import pytest

from freerise.categorize.ai import NullCategorizer, OpenRouterCategorizer
from freerise.categorize.cli import export_uncategorized, import_rules


def test_export_import_roundtrip(session, cat, mk_txn, tmp_path):
    t1, t2 = mk_txn("שופרסל דיל", "-100"), mk_txn("שופרסל דיל", "-50")
    out = tmp_path / "e.jsonl"
    assert export_uncategorized(session, out) == 1
    rec = json.loads(out.read_text().splitlines()[0])
    assert (rec["merchant_key"], rec["count"], rec["total"], rec["kind"]) == (
        t1.merchant_key,
        2,
        -150.0,
        "card",
    )
    inp = tmp_path / "i.jsonl"
    inp.write_text(
        json.dumps({"merchant_key": t1.merchant_key, "category": "כלכלה"}, ensure_ascii=False)
        + "\n"
        + json.dumps({"merchant_key": "x", "category": "לא קיים"}, ensure_ascii=False)
    )
    assert import_rules(session, inp) == (1, 1)
    assert t1.category_id == t2.category_id == cat("כלכלה").id
    assert t1.category_source == "ai"


def test_ai_stub_and_openrouter(monkeypatch):
    assert NullCategorizer().categorize([{}]) == {}
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(NotImplementedError):
        OpenRouterCategorizer(["כלכלה"]).categorize([])
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "m")
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        content = json.dumps({"a": "כלכלה"})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert OpenRouterCategorizer(["כלכלה"], client).categorize([{"merchant_key": "a"}]) == {
        "a": "כלכלה"
    }
    assert seen["body"]["model"] == "m"
