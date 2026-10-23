import os
from typing import Protocol

import httpx


class AiCategorizer(Protocol):
    def categorize(self, items: list[dict]) -> dict[str, str]:
        """items: [{merchant_key, sample_description, ...}] -> {merchant_key: category name}"""
        ...


class NullCategorizer:
    def categorize(self, items: list[dict]) -> dict[str, str]:
        return {}


class OpenRouterCategorizer:
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, categories: list[str], client: httpx.Client | None = None):
        self.categories = categories
        self.client = client or httpx.Client(timeout=60)

    def categorize(self, items: list[dict]) -> dict[str, str]:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise NotImplementedError("set OPENROUTER_API_KEY to enable AI categorization")
        import json

        prompt = (
            f"Categories: {', '.join(self.categories)}.\n"
            "Reply with a JSON object mapping each merchant_key to one category.\n"
            f"{json.dumps(items, ensure_ascii=False)}"
        )
        r = self.client.post(
            self.URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": os.environ.get("OPENROUTER_MODEL", ""),
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
        )
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])
