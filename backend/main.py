from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import db
import queue_manager
from config import PROJECT_ROOT, settings
from integrations import sheets

FRONTEND = PROJECT_ROOT / "frontend" / "index.html"

# Tracks running pipeline tasks so we can cancel them.
_tasks: dict[int, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield
    for task in list(_tasks.values()):
        task.cancel()


app = FastAPI(title="Account Enrichment Pipeline", lifespan=lifespan)


class StartRunBody(BaseModel):
    sheet_id: str | None = None
    value_prop: str


def _slim_account(row: dict) -> dict:
    score = None
    for key in ("eval_2", "eval_1"):
        ev = row.get(key)
        if isinstance(ev, dict) and ev.get("score") is not None:
            score = ev["score"]
            break
    return {
        "id": row["id"],
        "name": row["name"],
        "domain": row.get("domain"),
        "status": row["status"],
        "batch_number": row.get("batch_number"),
        "score": score,
        "updated_at": row.get("updated_at"),
    }


@app.get("/")
async def dashboard():
    if not FRONTEND.exists():
        raise HTTPException(404, "frontend/index.html not found")
    return FileResponse(FRONTEND)


@app.post("/api/runs")
async def start_run(body: StartRunBody):
    sheet_id = (body.sheet_id or settings.google_sheet_id).strip()
    if not sheet_id:
        raise HTTPException(400, "sheet_id is required")
    try:
        raw_accounts = sheets.get_accounts(sheet_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not raw_accounts:
        raise HTTPException(400, "Sheet has no accounts to process")

    run_id = await db.create_run(body.value_prop, sheet_id)
    account_ids = await db.insert_accounts(run_id, raw_accounts)
    queue_accounts = [
        {**raw, "id": aid} for raw, aid in zip(raw_accounts, account_ids)
    ]
    task = asyncio.create_task(
        queue_manager.run_pipeline(run_id, queue_accounts, body.value_prop)
    )
    _tasks[run_id] = task
    task.add_done_callback(lambda _t, rid=run_id: _tasks.pop(rid, None))
    return {"run_id": run_id, "total": len(queue_accounts)}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: int):
    run = await db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run


@app.get("/api/runs/{run_id}/accounts")
async def get_run_accounts(run_id: int):
    rows = await db.get_run_accounts(run_id)
    return [_slim_account(r) for r in rows]


@app.get("/api/accounts/{account_id}")
async def get_account(account_id: int):
    row = await db.get_account(account_id)
    if not row:
        raise HTTPException(404, "account not found")
    return row


@app.get("/api/accounts/{account_id}/logs")
async def get_account_logs(account_id: int):
    return await db.get_account_logs(account_id)


@app.delete("/api/runs/{run_id}")
async def cancel_run(run_id: int):
    task = _tasks.get(run_id)
    if task and not task.done():
        task.cancel()
    await db.update_run_status(run_id, "cancelled")
    return {"run_id": run_id, "status": "cancelled"}


@app.get("/api/sheets/preview")
async def preview_sheet(sheet_id: str | None = None):
    target = (sheet_id or settings.google_sheet_id).strip()
    if not target:
        raise HTTPException(400, "sheet_id is required")
    try:
        accounts = sheets.get_accounts(target)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"sheet_id": target, "total": len(accounts), "preview": accounts[:10]}
