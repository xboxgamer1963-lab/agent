from __future__ import annotations

import json

from integrations.gemini import call_gemini


_SYSTEM = """You are compiling a Pipedrive briefing for a BDR on {name}.

Write a Pipedrive note ~300-400 words, plain text, no markdown. Use this
exact section order and headings (UPPERCASE headings, blank line between
sections):

[AI ENRICHMENT — Score: {score}/10]

WHY NOW
<2-3 sentences synthesising the strongest why-now signal from headline + news + hiring.>

WHERE WE FIT
<2-3 sentences mapping the value prop to a specific, evidenced pain.>

WEDGE USE CASES
1. <use case 1> — <why it's an easy entry>
2. <use case 2> — <why it's an easy entry>
3. <use case 3> — <why it's an easy entry>

TOP OUTREACH ANGLES
1. <angle 1 trigger> — <pitch in 1 sentence>
2. <angle 2 trigger> — <pitch in 1 sentence>
3. <angle 3 trigger> — <pitch in 1 sentence>

KPIS THEY'LL TRACK
<comma-separated list of 3-5 KPIs>

LIKELY OBJECTIONS
1. <objection 1>
2. <objection 2>
3. <objection 3>

LINKEDIN TARGETS
Titles: <comma-separated decision-maker titles>
Primary: <primary_search boolean string>

Return ONLY valid JSON:
{{
  "summary":        "2-3 sentence executive summary of this account",
  "key_insight":    "the single sharpest signal in one sentence",
  "pipedrive_note": "the full briefing above as a single string with \\n line breaks",
  "tags":           ["2-4 short kebab-case tags, e.g. 'series-b', 'hiring-sales'"]
}}"""


async def run(
    account: dict,
    hypothesis: dict,
    news: dict,
    linkedin: dict,
    evaluation: dict,
    search_commands: dict,
    outreach_angles: dict | None = None,
) -> dict:
    name = account.get("name", "")
    score = evaluation.get("score", 0)
    system = _SYSTEM.format(name=name, score=score)
    user = (
        f"Company: {name}\n"
        f"Domain: {account.get('domain') or 'unknown'}\n\n"
        f"1-PAGE HYPOTHESIS:\n{json.dumps(hypothesis, indent=2)}\n\n"
        f"NEWS SIGNALS:\n{json.dumps(news, indent=2)}\n\n"
        f"LINKEDIN SIGNALS:\n{json.dumps(linkedin, indent=2)}\n\n"
        f"EVALUATION:\n{json.dumps(evaluation, indent=2)}\n\n"
        f"OUTREACH ANGLES (use top 3 ranked by strength):\n"
        f"{json.dumps(outreach_angles or {'angles': []}, indent=2)}\n\n"
        f"LINKEDIN SEARCH COMMANDS:\n{json.dumps(search_commands, indent=2)}"
    )
    result = await call_gemini(system, user)
    return {
        "summary":        result.get("summary", ""),
        "key_insight":    result.get("key_insight", ""),
        "pipedrive_note": result.get("pipedrive_note", ""),
        "tags":           result.get("tags") or [],
    }
