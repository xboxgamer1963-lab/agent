from __future__ import annotations

import asyncio
import json
import re
import sys

import httpx

from config import settings

_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_BACKOFF = [2.0, 5.0]


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        return parsed[0]
    raise ValueError(f"expected JSON object from Ollama, got {type(parsed).__name__}")


def _log(msg: str) -> None:
    print(f"[ollama] {msg}", file=sys.stderr)


async def call_ollama(system: str, user: str) -> dict:
    if not settings.ollama_model:
        raise RuntimeError("OLLAMA_MODEL not configured")
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": user + "\n\nReturn ONLY valid JSON. No prose, no fences.",
            },
        ],
        "temperature": 0.4,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    last_exc: Exception | None = None
    total_attempts = len(_BACKOFF) + 1
    for attempt in range(total_attempts):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(settings.ollama_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
            content = (
                (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            )
            return _extract_json(content)
        except (httpx.TimeoutException, httpx.ConnectError,
                httpx.RemoteProtocolError, httpx.ReadError) as e:
            last_exc = e
            if attempt < len(_BACKOFF):
                delay = _BACKOFF[attempt]
                _log(f"{type(e).__name__} (attempt {attempt + 1}/{total_attempts}); retry in {delay}s")
                await asyncio.sleep(delay)
                continue
            raise
    raise last_exc  # unreachable
