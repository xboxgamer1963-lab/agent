from __future__ import annotations

import asyncio

from integrations.tavily import search


async def run(account: dict) -> list[dict]:
    """Tavily searches for hiring + team-growth signals. Returns raw results."""
    name = account.get("name", "")
    domain = account.get("domain", "") or ""
    q1 = (
        f"{name} hiring jobs "
        "site:linkedin.com OR site:greenhouse.io OR site:lever.co"
    )
    q2 = f"{name} {domain} team growth engineering sales 2024 2025".strip()
    r1, r2 = await asyncio.gather(
        search(q1, max_results=5),
        search(q2, max_results=5),
    )
    return r1 + r2
