from __future__ import annotations

import json

from config import settings
from integrations.gemini import call_gemini


_SYSTEM = """You are a strict B2B sales relevance evaluator.

Score this account 1-10 based on the evidence below. Score 7+ ONLY if ALL of:
  1. There is a specific, recent signal (news or hiring) that creates urgency.
  2. The value proposition directly addresses an evidenced pain point.
  3. The timing is right — the company is in a state of change or growth.
Be harsh. A generic fit is 5. A strong fit backed by evidence is 7+.

"relevant" must be true ONLY if score >= {threshold}.

Return ONLY valid JSON:
{{
  "score":           1-10 int,
  "relevant":        bool,
  "verdict":         "one sentence: ship to Pipedrive or drop?",
  "fit_reasons":     ["specific evidence supporting the score"],
  "talking_points":  ["2-3 sharp cold-call lines"],
  "suggested_angle": "the recommended opening angle"
}}"""


def _normalise(result: dict, threshold: int) -> dict:
    try:
        score = int(result.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    score = max(1, min(10, score)) if score else 0
    relevant = bool(result.get("relevant")) and score >= threshold

    return {
        "score":           score,
        "relevant":        relevant,
        "verdict":         result.get("verdict", ""),
        "fit_reasons":     result.get("fit_reasons") or [],
        "talking_points":  result.get("talking_points") or [],
        "suggested_angle": result.get("suggested_angle", ""),
    }


async def run(
    account: dict,
    value_prop: str,
    hypothesis: dict,
    signals: dict,
) -> dict:
    """Score fit. Small focused call."""
    threshold = settings.relevance_threshold
    system = _SYSTEM.format(threshold=threshold)
    user = (
        f"Company: {account.get('name')}\n"
        f"Domain: {account.get('domain') or 'unknown'}\n\n"
        f"VALUE PROPOSITION:\n{value_prop}\n\n"
        f"1-PAGE HYPOTHESIS:\n{json.dumps(hypothesis, indent=2)}\n\n"
        f"NEWS SIGNALS:\n{json.dumps(signals.get('news_signals') or {}, indent=2)}\n\n"
        f"HIRING SIGNALS:\n{json.dumps(signals.get('linkedin_signals') or {}, indent=2)}"
    )
    raw = await call_gemini(system, user)
    return _normalise(raw, threshold)
