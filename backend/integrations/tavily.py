from __future__ import annotations

import httpx

from config import settings

_URL = "https://api.tavily.com/search"
_TIMEOUT = 20.0


async def search(query: str, max_results: int = 5) -> list[dict]:
    """Tavily search. Returns list of {title, url, content, score}.

    Per error-handling rules: on timeout / non-200, return [] instead of
    raising — downstream agents must handle empty inputs gracefully.
    """
    body = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
        "include_raw_content": False,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(_URL, json=body)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return []
    results = data.get("results", []) or []
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "score": r.get("score", 0),
        }
        for r in results
    ]
