import json
import os
from typing import Protocol

import httpx


def chat_completion(
    client: httpx.Client, url: str, key: str, model: str, messages: list[dict], **extra
) -> str:
    """POST an OpenAI-compatible /chat/completions (OpenRouter and friends); the reply text."""
    r = client.post(
        url,
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": messages, **extra},
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


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
        prompt = (
            f"Categories: {', '.join(self.categories)}.\n"
            "Reply with a JSON object mapping each merchant_key to one category.\n"
            f"{json.dumps(items, ensure_ascii=False)}"
        )
        content = chat_completion(
            self.client,
            self.URL,
            key,
            os.environ.get("OPENROUTER_MODEL", ""),
            [{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return json.loads(content)
