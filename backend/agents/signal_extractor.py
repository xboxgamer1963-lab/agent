from __future__ import annotations

from integrations.gemini import call_gemini


_SYSTEM = """You distill structured signals from raw web search snippets about {name}.

Return ONLY valid JSON with EXACTLY these keys (no extras, no missing keys):

{{
  "news_signals": {{
    "headline":        "most important news in one sentence, or null",
    "funding":         "e.g. 'Series B $40M, March 2025', or null",
    "product_launch": "string or null",
    "exec_change":    "string or null",
    "growth_signal":  "string or null",
    "sources":        ["url", "url"]
  }},
  "linkedin_signals": {{
    "open_roles":         ["role title", "role title"],
    "pain_signals":       ["short phrase", "short phrase"],
    "team_growth":        "one sentence summary",
    "likely_initiatives": ["short phrase", "short phrase"]
  }}
}}

Rules:
- Use ONLY information supported by the snippets. Do NOT invent.
- Set string fields to null and array fields to [] when no evidence.
- Keep each string under 25 words."""


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


def _normalise(result: dict) -> dict:
    news = result.get("news_signals") or {}
    linkedin = result.get("linkedin_signals") or {}
    return {
        "news_signals": {
            "headline":       news.get("headline"),
            "funding":        news.get("funding"),
            "product_launch": news.get("product_launch"),
            "exec_change":    news.get("exec_change"),
            "growth_signal":  news.get("growth_signal"),
            "sources":        news.get("sources") or [],
        },
        "linkedin_signals": {
            "open_roles":         linkedin.get("open_roles") or [],
            "pain_signals":       linkedin.get("pain_signals") or [],
            "team_growth":        linkedin.get("team_growth") or "",
            "likely_initiatives": linkedin.get("likely_initiatives") or [],
        },
    }


async def run(
    account: dict,
    news_results: list[dict],
    linkedin_results: list[dict],
) -> dict:
    """Returns {news_signals, linkedin_signals}. Small output, fast call."""
    system = _SYSTEM.format(name=account.get("name", ""))
    user = (
        f"NEWS SEARCH RESULTS:\n{_format_results(news_results)}\n\n"
        f"HIRING / LINKEDIN SEARCH RESULTS:\n{_format_results(linkedin_results)}"
    )
    raw = await call_gemini(system, user)
    return _normalise(raw)
