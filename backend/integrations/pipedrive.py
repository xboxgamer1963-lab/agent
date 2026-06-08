from __future__ import annotations

import httpx

from config import settings

_BASE = "https://api.pipedrive.com/v1"
_TIMEOUT = 20.0


def _params(extra: dict | None = None) -> dict:
    params = {"api_token": settings.pipedrive_api_key}
    if extra:
        params.update(extra)
    return params


async def find_or_create_org(name: str) -> str:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(
            f"{_BASE}/organizations/search",
            params=_params({"term": name, "exact_match": "false", "limit": 1}),
        )
        r.raise_for_status()
        data = r.json().get("data") or {}
        items = data.get("items") or []
        if items:
            org_id = items[0].get("item", {}).get("id")
            if org_id is not None:
                return str(org_id)
        r = await client.post(
            f"{_BASE}/organizations",
            params=_params(),
            json={"name": name},
        )
        r.raise_for_status()
        return str(r.json()["data"]["id"])


async def add_note(org_id: str, content: str) -> str:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(
            f"{_BASE}/notes",
            params=_params(),
            json={"content": content, "org_id": int(org_id)},
        )
        r.raise_for_status()
        return str(r.json()["data"]["id"])


async def add_label(org_id: str, label: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            await client.put(
                f"{_BASE}/organizations/{org_id}",
                params=_params(),
                json={"label": label},
            )
    except Exception:
        return
