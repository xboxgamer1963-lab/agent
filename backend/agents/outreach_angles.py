from __future__ import annotations

import json

from integrations.gemini import call_gemini


_SYSTEM = """Generate 12 outreach angles for {name} ({domain}) selling: {value_prop}.

Pick angles SPECIFICALLY supported by the evidence (homepage, news, hiring)
and the 1-page hypothesis attached. Rank by strength of evidence (strongest
first). Do not invent triggers that are not supported.

If the value prop is in Fleet Telematics / IoT, draw from these common
triggers when evidence supports them: fuel spend spike, safety incidents,
CSA score pressure, ELD/compliance needs, maintenance downtime, asset
theft, route inefficiency, insurance renewal. If the value prop is in a
different space, infer the equivalent industry-specific triggers.

For each angle return: trigger, pain, outcome_kpi, proof_idea, pitch.
Pitch is a single sentence a BDR can paste directly into a cold message.

Return ONLY valid JSON:

{{
  "angles": [
    {{
      "trigger":     "...",
      "pain":        "...",
      "outcome_kpi": "...",
      "proof_idea":  "...",
      "pitch":       "..."
    }}
    /* 12 total */
  ]
}}"""


def _normalise(result: dict) -> dict:
    angles = result.get("angles") or []
    cleaned = []
    for a in angles:
        if not isinstance(a, dict):
            continue
        cleaned.append({
            "trigger":     a.get("trigger", ""),
            "pain":        a.get("pain", ""),
            "outcome_kpi": a.get("outcome_kpi", ""),
            "proof_idea":  a.get("proof_idea", ""),
            "pitch":       a.get("pitch", ""),
        })
    return {"angles": cleaned}


async def run(
    account: dict,
    value_prop: str,
    hypothesis: dict,
) -> dict:
    system = _SYSTEM.format(
        name=account.get("name", ""),
        domain=account.get("domain") or "unknown",
        value_prop=value_prop,
    )
    user = (
        f"VALUE PROPOSITION:\n{value_prop}\n\n"
        f"1-PAGE HYPOTHESIS:\n{json.dumps(hypothesis, indent=2)}"
    )
    raw = await call_gemini(system, user)
    return _normalise(raw)
