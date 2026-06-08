from __future__ import annotations

from integrations.tavily import search


async def run(account: dict) -> list[dict]:
    """Tavily search for recent news. Returns raw results (no Gemini)."""
    name = account.get("name", "")
    domain = account.get("domain", "") or ""
    query = f"{name} {domain} news funding product launch 2024 2025".strip()
    return await search(query, max_results=5)
