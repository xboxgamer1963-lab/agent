from __future__ import annotations

import asyncio
import json
import re
import sys

import httpx

from config import settings

_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
_TIMEOUT = httpx.Timeout(connect=15.0, read=75.0, write=10.0, pool=10.0)
_MODEL = "deepseek-ai/deepseek-v4-flash"
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_BACKOFF = [2.0]  # one retry only — fail fast to next provider in chain


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
    raise ValueError(f"expected JSON object from NVIDIA, got {type(parsed).__name__}")


def _log(msg: str) -> None:
    print(f"[nvidia] {msg}", file=sys.stderr)


async def call_nvidia(system: str, user: str) -> dict:
    if not settings.nvidia_api_key:
        raise RuntimeError("NVIDIA_API_KEY not configured")
    headers = {
        "Authorization": f"Bearer {settings.nvidia_api_key}",
        "Accept": "application/json",
    }
    payload = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": user
                + "\n\nReturn ONLY valid JSON. No prose, no fences.",
            },
        ],
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 8192,
        "stream": False,
        "chat_template_kwargs": {"thinking": False},
    }

    last_exc: Exception | None = None
    total_attempts = len(_BACKOFF) + 1
    for attempt in range(total_attempts):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(_URL, headers=headers, json=payload)
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
        except httpx.HTTPStatusError as e:
            # 5xx is transient and worth a retry; 4xx is permanent.
            if e.response.status_code >= 500 and attempt < len(_BACKOFF):
                last_exc = e
                delay = _BACKOFF[attempt]
                _log(f"HTTP {e.response.status_code} (attempt {attempt + 1}); retry in {delay}s")
                await asyncio.sleep(delay)
                continue
            raise
    raise last_exc  # unreachable
