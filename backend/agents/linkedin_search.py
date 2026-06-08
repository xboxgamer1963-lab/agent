from __future__ import annotations

import json

from integrations.gemini import call_gemini


_SYSTEM = """You generate LinkedIn Sales Navigator Boolean searches that a BDR
can paste directly into Sales Navigator. Pick the 2-4 decision-maker titles
most likely to own the buying decision for this value proposition given the
account's pain signals.

primary_search MUST follow this exact shape:
("Title A" OR "Title B" OR "Title C") AND "{company_name}"

backup_search MUST be a broader fallback — a wider title set, optionally
without the company name AND clause, that surfaces adjacent decision makers.

Return ONLY valid JSON with keys: target_titles (array of strings),
primary_search (string), backup_search (string), why_these_titles (string)."""


async def run(
    account: dict,
    evaluation: dict,
    linkedin: dict,
) -> dict:
    name = account.get("name", "")
    system = _SYSTEM.format(company_name=name)
    user = (
        f"Company: {name}\n\n"
        f"Evaluator output:\n{json.dumps(evaluation, indent=2)}\n\n"
        f"LinkedIn / hiring signals:\n{json.dumps(linkedin, indent=2)}"
    )
    result = await call_gemini(system, user)

    return {
        "target_titles": result.get("target_titles") or [],
        "primary_search": result.get("primary_search", ""),
        "backup_search": result.get("backup_search", ""),
        "why_these_titles": result.get("why_these_titles", ""),
    }
