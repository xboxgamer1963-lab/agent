from __future__ import annotations

from integrations.gemini import call_gemini

_SYSTEM = """You are analyzing a company's website and public search results to infer who
THEY sell to — their Ideal Customer Profile (ICP) — so their sales team can configure an
account-research tool with it.

Use ONLY the evidence given below. Do not invent facts you cannot support from the
homepage content or search snippets. If something is genuinely unclear, make a
reasonable, clearly-scoped best guess rather than leaving a field empty.

Return ONLY valid JSON with EXACTLY these keys:

{
  "company":        "the company's name",
  "industry":       "short label, e.g. 'Fleet & Logistics SaaS'",
  "target_market":  "1 sentence describing the market segment they sell into",
  "audience":       "1 sentence describing the buyer persona / team they sell to",
  "icp":            "2-4 sentences describing their best-fit customer — size, signals, pain points",
  "target_roles":   "comma-separated decision-maker titles, e.g. 'VP Operations, Safety Director'"
}"""


def _normalise(result: dict) -> dict:
    return {
        "company":       result.get("company") or "",
        "industry":      result.get("industry") or "",
        "target_market": result.get("target_market") or "",
        "audience":      result.get("audience") or "",
        "icp":           result.get("icp") or "",
        "target_roles":  result.get("target_roles") or "",
    }


def _format_results(results: list[dict], limit_chars: int = 400) -> str:
    if not results:
        return "(no results)"
    blocks = []
    for r in results:
        title = r.get("title", "")
        url = r.get("url", "")
        content = (r.get("content") or "")[:limit_chars]
        blocks.append(f"- {title}\n  {url}\n  {content}")
    return "\n\n".join(blocks)


async def run(website: str, homepage: str, search_results: list[dict]) -> dict:
    """Infer the ICP of the company OWNING `website` from its homepage + search results."""
    user = (
        f"WEBSITE: {website}\n\n"
        f"HOMEPAGE SCRAPE:\n{homepage or '(scrape returned nothing)'}\n\n"
        f"SEARCH RESULTS ABOUT THE COMPANY:\n{_format_results(search_results)}"
    )
    raw = await call_gemini(_SYSTEM, user)
    return _normalise(raw)
