from __future__ import annotations

from integrations.firecrawl import scrape

_MAX_CHARS = 5000


async def run(account: dict) -> str:
    """Firecrawl the company's homepage. Returns markdown (truncated) or ""."""
    domain = (account.get("domain") or "").strip()
    if not domain:
        return ""
    if not domain.startswith(("http://", "https://")):
        domain = f"https://{domain}"
    markdown = await scrape(domain)
    if not markdown:
        return ""
    return markdown[:_MAX_CHARS]
