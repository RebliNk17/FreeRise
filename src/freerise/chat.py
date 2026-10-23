"""Cash-flow Q&A ("שאל אותי על התזרים") over an OpenAI-compatible LLM API (e.g. OpenRouter).

Off unless FREERISE_LLM_BASE_URL, FREERISE_LLM_API_KEY and FREERISE_LLM_MODEL are all set.
The model only sees a compact, aggregated context: cycle totals, category totals, recurring
items, savings goals. Never account numbers, card digits, credentials or raw transactions.
Prompts and replies are never logged (they describe the household's money)."""

import json
import os
from dataclasses import dataclass
from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.cashflow.cycles import cycle_for, get_start_day
from freerise.cashflow.plan import cycle_plan, history, projected_month_end
from freerise.cashflow.summary import UNCATEGORIZED, CycleSummary, cycle_summary
from freerise.categorize.ai import chat_completion
from freerise.models import RecurringItem, SavingsPlan

TOP_CATEGORIES = 8
SYSTEM = (
    "אתה עוזר שעונה על שאלות על התזרים של משק בית, בעברית, בקצרה ובבהירות. "
    "ענה רק לפי הנתונים המצורפים (JSON). אם אין בנתונים תשובה, אמור זאת. "
    "סכומים בשקלים. אל תמציא מספרים ואל תיתן ייעוץ השקעות. "
    "מחזור (חודש תזרימי) מסומן בחודש שבו התחיל."
)


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    api_key: str
    model: str


def llm_config() -> LlmConfig | None:
    """None when the feature is off (any of the three env vars missing)."""
    vals = [
        os.environ.get(f"FREERISE_LLM_{k}", "").strip() for k in ("BASE_URL", "API_KEY", "MODEL")
    ]
    return LlmConfig(*vals) if all(vals) else None


def _cycle(s: CycleSummary) -> dict:
    out = {
        "month": f"{s.cycle.label_month:%Y-%m}",
        "income": round(float(s.income)),
        "spending": round(float(s.spending)),
        "net": round(float(s.net)),
    }
    for g in s.groups:
        if g.group == "income":
            continue
        out[g.group] = round(float(g.total))
        top = sorted(g.categories, key=lambda c: -c.total)[:TOP_CATEGORIES]
        out[f"{g.group}_by_category"] = {
            (c.name or UNCATEGORIZED): round(float(c.total)) for c in top if c.total
        }
    return out


def build_context(session: Session, today: date) -> dict:
    """Aggregates only; see the module docstring."""
    cur = cycle_for(today, get_start_day(session))
    plan = cycle_plan(session, today)
    hist = history(session, cur)
    return {
        "today": today.isoformat(),
        "current_cycle": {
            **_cycle(cycle_summary(session, cur)),
            "start": cur.start.isoformat(),
            "end": cur.end.isoformat(),
            "variable_budget": round(float(plan.variable_allowance)),
            "variable_left": round(float(plan.variable_left)),
            "month_end_goal": round(float(plan.goal)),
            "projected_month_end": round(float(projected_month_end(plan, today, hist))),
        },
        "previous_cycles": [_cycle(s) for s in reversed(hist)],  # oldest first
        "recurring": [
            {
                "label": r.label,
                "direction": r.direction,
                "cadence": r.cadence,
                "amount": round(float(r.expected_amount)),
                "next": r.next_expected_date.isoformat(),
            }
            for r in session.scalars(
                select(RecurringItem).where(RecurringItem.status == "confirmed")
            )
        ],
        "savings_goals": [
            {
                "name": p.name,
                "target": round(float(p.target_amount)),
                "saved": round(float(p.saved_amount)),
                "target_date": p.target_date.isoformat(),
            }
            for p in session.scalars(select(SavingsPlan).where(SavingsPlan.active.is_(True)))
        ],
    }


def answer(
    session: Session,
    today: date,
    messages: list[dict],
    cfg: LlmConfig,
    client: httpx.Client | None = None,
) -> str:
    context = json.dumps(build_context(session, today), ensure_ascii=False)
    prompt = [
        {"role": "system", "content": f"{SYSTEM}\n\nנתונים:\n{context}"},
        *messages,
    ]
    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    with client or httpx.Client(timeout=60) as c:
        return chat_completion(c, url, cfg.api_key, cfg.model, prompt).strip()
