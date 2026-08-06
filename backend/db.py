from __future__ import annotations

from datetime import datetime, timezone

from supabase import AsyncClient, create_async_client

from config import settings

_client: AsyncClient | None = None


async def _get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = await create_async_client(
            settings.supabase_url, settings.supabase_service_role_key
        )
    return _client


async def get_client() -> AsyncClient:
    """Public accessor — used by main.py to verify user bearer tokens."""
    return await _get_client()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    client = await _get_client()
    try:
        await client.table("runs").select("id").limit(1).execute()
    except Exception as e:
        raise RuntimeError(
            "Could not reach the Supabase 'runs' table. Run supabase_schema.sql "
            "in the Supabase SQL Editor for this project, then restart the server."
        ) from e


async def create_run(value_prop: str, sheet_id: str, user_id: str) -> int:
    client = await _get_client()
    res = (
        await client.table("runs")
        .insert(
            {
                "created_at": _now(),
                "value_prop": value_prop,
                "sheet_id": sheet_id,
                "status": "pending",
                "user_id": user_id,
            }
        )
        .execute()
    )
    return res.data[0]["id"]


async def insert_accounts(run_id: int, accounts: list[dict], user_id: str) -> list[int]:
    if not accounts:
        return []
    client = await _get_client()
    batch_size_default = 5
    now = _now()
    rows = [
        {
            "run_id": run_id,
            "user_id": user_id,
            "name": acc.get("name"),
            "domain": acc.get("domain"),
            "row_index": acc.get("row_index"),
            "status": "pending",
            "batch_number": (idx // batch_size_default) + 1,
            "updated_at": now,
        }
        for idx, acc in enumerate(accounts)
    ]
    res = await client.table("accounts").insert(rows).execute()
    ids = [row["id"] for row in res.data]
    await client.table("runs").update({"total": len(accounts)}).eq(
        "id", run_id
    ).execute()
    return ids


async def get_run(run_id: int, user_id: str) -> dict | None:
    client = await _get_client()
    res = (
        await client.table("runs")
        .select("*")
        .eq("id", run_id)
        .eq("user_id", user_id)
        .execute()
    )
    return res.data[0] if res.data else None


async def get_run_accounts(run_id: int, user_id: str) -> list[dict]:
    client = await _get_client()
    res = (
        await client.table("accounts")
        .select("*")
        .eq("run_id", run_id)
        .eq("user_id", user_id)
        .order("id")
        .execute()
    )
    return res.data


async def get_all_accounts(user_id: str, limit: int = 500) -> list[dict]:
    client = await _get_client()
    res = (
        await client.table("accounts")
        .select("*")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data


async def get_recent_runs(user_id: str, limit: int = 10) -> list[dict]:
    client = await _get_client()
    res = (
        await client.table("runs")
        .select("*")
        .eq("user_id", user_id)
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data


async def get_account(account_id: int, user_id: str) -> dict | None:
    client = await _get_client()
    res = (
        await client.table("accounts")
        .select("*")
        .eq("id", account_id)
        .eq("user_id", user_id)
        .execute()
    )
    return res.data[0] if res.data else None


async def get_account_logs(account_id: int) -> list[dict]:
    client = await _get_client()
    res = (
        await client.table("logs")
        .select("*")
        .eq("account_id", account_id)
        .order("created_at")
        .order("id")
        .execute()
    )
    return res.data


async def update_account(account_id: int, **fields) -> None:
    if not fields:
        return
    client = await _get_client()
    fields = dict(fields)
    fields["updated_at"] = _now()
    await client.table("accounts").update(fields).eq("id", account_id).execute()


async def update_run_counts(run_id: int) -> None:
    client = await _get_client()
    res = (
        await client.table("accounts")
        .select("status")
        .eq("run_id", run_id)
        .execute()
    )
    statuses = [r["status"] for r in res.data]
    done = sum(1 for s in statuses if s in ("enriched", "dropped", "error"))
    enriched = statuses.count("enriched")
    dropped = statuses.count("dropped")
    errors = statuses.count("error")
    await client.table("runs").update(
        {"done": done, "enriched": enriched, "dropped": dropped, "errors": errors}
    ).eq("id", run_id).execute()


async def update_run_status(run_id: int, status: str) -> None:
    client = await _get_client()
    await client.table("runs").update({"status": status}).eq("id", run_id).execute()


async def add_log(account_id: int, step: str, message: str) -> None:
    client = await _get_client()
    await client.table("logs").insert(
        {
            "account_id": account_id,
            "step": step,
            "message": message,
            "created_at": _now(),
        }
    ).execute()


async def get_profile(user_id: str) -> dict | None:
    client = await _get_client()
    res = await client.table("profiles").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None


async def upsert_profile(user_id: str, email: str | None, fields: dict) -> dict:
    client = await _get_client()
    row = {**fields, "user_id": user_id, "email": email, "updated_at": _now()}
    res = (
        await client.table("profiles")
        .upsert(row, on_conflict="user_id")
        .execute()
    )
    return res.data[0]


async def get_analytics(user_id: str) -> dict:
    client = await _get_client()

    acc_res = (
        await client.table("accounts")
        .select("status, eval_1, eval_2")
        .eq("user_id", user_id)
        .execute()
    )
    accounts = acc_res.data
    total = len(accounts)
    pending = sum(1 for a in accounts if a["status"] == "pending")
    running = sum(1 for a in accounts if a["status"] == "running")
    enriched = sum(1 for a in accounts if a["status"] == "enriched")
    dropped = sum(1 for a in accounts if a["status"] == "dropped")
    error = sum(1 for a in accounts if a["status"] == "error")

    scores: list[int] = []
    histogram = {i: 0 for i in range(1, 11)}
    for a in accounts:
        ev = a.get("eval_2") or a.get("eval_1")
        if isinstance(ev, dict) and ev.get("score") is not None:
            score = ev["score"]
            scores.append(score)
            if score in histogram:
                histogram[score] += 1
    avg_score = sum(scores) / len(scores) if scores else None

    runs_res = (
        await client.table("runs")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    total_runs = (
        runs_res.count if runs_res.count is not None else len(runs_res.data)
    )

    return {
        "total": total,
        "pending": pending,
        "running": running,
        "enriched": enriched,
        "dropped": dropped,
        "error": error,
        "avg_score": avg_score,
        "total_runs": total_runs,
        "score_histogram": histogram,
    }
