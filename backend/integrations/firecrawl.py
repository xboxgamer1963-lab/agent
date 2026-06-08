from __future__ import annotations

import httpx

from config import settings

_URL = "https://api.firecrawl.dev/v1/scrape"
_TIMEOUT = 10.0


async def scrape(url: str) -> str:
    """Scrape a URL to markdown. Returns "" on any failure (never raises)."""
    if not url:
        return ""
    headers = {"Authorization": f"Bearer {settings.firecrawl_api_key}"}
    body = {"url": url, "formats": ["markdown"]}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(_URL, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return ""
    return (data.get("data", {}) or {}).get("markdown", "") or ""
