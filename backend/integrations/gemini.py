from __future__ import annotations

import asyncio
import json
import re
import sys

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

from config import settings

genai.configure(api_key=settings.gemini_api_key)
_model = genai.GenerativeModel("gemini-2.5-flash")

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_RETRY_DELAY_RE = re.compile(r"retry_delay\s*\{\s*seconds:\s*(\d+)", re.IGNORECASE)

MAX_RATE_RETRIES = 3   # retries on Gemini 429
MAX_JSON_RETRIES = 1   # retries on bad JSON output


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = _JSON_FENCE.search(text)
    if match:
        text = match.group(1).strip()
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        return parsed[0]
    raise ValueError(f"expected JSON object, got {type(parsed).__name__}")


def _retry_delay_from(e: BaseException) -> int:
    m = _RETRY_DELAY_RE.search(str(e))
    return int(m.group(1)) if m else 60


def _log(msg: str) -> None:
    print(f"[gemini] {msg}", file=sys.stderr)


async def call_gemini(system: str, user: str) -> dict:
    """Gemini-only. Retries on 429 (waits the API-suggested delay) and on bad JSON."""
    prompt = f"{system}\n\n{user}\n\nReturn ONLY valid JSON. No prose, no fences."
    last_text = ""
    rate_attempts = 0
    json_attempts = 0
    while True:
        try:
            resp = await asyncio.to_thread(
                _model.generate_content,
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.4,
                },
            )
            last_text = (resp.text or "").strip()
            return _extract_json(last_text)
        except google_exceptions.ResourceExhausted as e:
            if rate_attempts >= MAX_RATE_RETRIES:
                raise
            rate_attempts += 1
            delay = min(_retry_delay_from(e), 70) + 2
            _log(f"429 quota (retry {rate_attempts}/{MAX_RATE_RETRIES}); sleeping {delay}s")
            await asyncio.sleep(delay)
        except (json.JSONDecodeError, ValueError):
            if json_attempts >= MAX_JSON_RETRIES:
                raise ValueError(f"Gemini returned non-JSON output: {last_text!r}")
            json_attempts += 1
            _log(f"bad JSON (retry {json_attempts}/{MAX_JSON_RETRIES})")
            await asyncio.sleep(2)
