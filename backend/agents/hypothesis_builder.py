from __future__ import annotations

import json

from integrations.gemini import call_gemini


_SYSTEM = """You are building a one-page account hypothesis for {name} ({domain}) for a
sales team selling: {value_prop}.

Use ONLY the evidence below — homepage scrape, distilled news signals, distilled
hiring signals. Do not invent facts. Every bullet must be traceable to a specific
signal in the evidence.

{retry_instruction}

Return ONLY valid JSON with EXACTLY these keys:

{{
  "headline":            "1-sentence summary of the why-now signal",
  "angle":               "short label, e.g. 'rapid fleet expansion'",
  "likely_cares":        ["3-5 bullets inferred from homepage + posts"],
  "likely_initiatives":  ["3-5 strategic initiatives from hiring + news"],
  "where_we_fit":        "1-2 sentences mapping value prop to evidenced pain",
  "wedge_use_cases": [
    {{"use_case": "...", "why_easy_entry": "..."}},
    {{"use_case": "...", "why_easy_entry": "..."}},
    {{"use_case": "...", "why_easy_entry": "..."}}
  ],
  "expected_kpis":       ["3-5 KPIs the account would track"],
  "top_stakeholders":    ["3-5 decision-maker titles"],
  "likely_objections":   ["exactly 5, ranked most-likely first"],
  "public_signals":      ["the actual signals used: job posts, headlines, homepage phrasing"]
}}"""


def _normalise(result: dict) -> dict:
    return {
        "headline":           result.get("headline", ""),
        "angle":              result.get("angle", ""),
        "likely_cares":       result.get("likely_cares") or [],
        "likely_initiatives": result.get("likely_initiatives") or [],
        "where_we_fit":       result.get("where_we_fit", ""),
        "wedge_use_cases":    result.get("wedge_use_cases") or [],
        "expected_kpis":      result.get("expected_kpis") or [],
        "top_stakeholders":   result.get("top_stakeholders") or [],
        "likely_objections":  result.get("likely_objections") or [],
        "public_signals":     result.get("public_signals") or [],
    }


async def run(
    account: dict,
    value_prop: str,
    homepage: str,
    signals: dict,
    previous: dict | None = None,
) -> dict:
    """Build the 1-page hypothesis. `previous` is (hypothesis, evaluation) from pass 1."""
    if previous:
        prev_hyp = previous.get("hypothesis") or {}
        prev_eval = previous.get("evaluation") or {}
        retry_instruction = (
            f'RETRY PASS: The previous angle "{prev_hyp.get("angle", "")}" '
            f'scored {prev_eval.get("score", 0)}/10 '
            f'(verdict: "{prev_eval.get("verdict", "")}"). '
            "Pick a completely different angle — different pain, different trigger, "
            "different urgency."
        )
    else:
        retry_instruction = ""

    system = _SYSTEM.format(
        name=account.get("name", ""),
        domain=account.get("domain") or "unknown",
        value_prop=value_prop,
        retry_instruction=retry_instruction,
    )
    user = (
        f"VALUE PROPOSITION:\n{value_prop}\n\n"
        f"HOMEPAGE SCRAPE:\n{homepage or '(scrape returned nothing)'}\n\n"
        f"NEWS SIGNALS:\n{json.dumps(signals.get('news_signals') or {}, indent=2)}\n\n"
        f"HIRING SIGNALS:\n{json.dumps(signals.get('linkedin_signals') or {}, indent=2)}"
    )
    raw = await call_gemini(system, user)
    return _normalise(raw)
