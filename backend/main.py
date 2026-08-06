from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import queue_manager
from config import PROJECT_ROOT, settings
from integrations import sheets

FRONTEND = PROJECT_ROOT / "frontend" / "dist" / "dashboard" / "index.html"
LANDING  = PROJECT_ROOT / "frontend" / "dist" / "index.html"
ONBOARDING = PROJECT_ROOT / "frontend" / "dist" / "onboarding" / "index.html"
ASSETS   = PROJECT_ROOT / "frontend" / "dist" / "assets"

# Tracks running pipeline tasks so we can cancel them.
_tasks: dict[int, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield
    for task in list(_tasks.values()):
        task.cancel()


app = FastAPI(title="Account Enrichment Pipeline", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")


async def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """Verifies the Supabase session bearer token and returns {id, email}."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    client = await db.get_client()
    try:
        res = await client.auth.get_user(token)
    except Exception:
        raise HTTPException(401, "Invalid or expired session")
    if not res or not res.user:
        raise HTTPException(401, "Invalid or expired session")
    return {"id": res.user.id, "email": res.user.email}


class AccountIn(BaseModel):
    name: str
    domain: str | None = None


class StartRunBody(BaseModel):
    sheet_id: str | None = None
    value_prop: str
    accounts: list[AccountIn] | None = None


class ProfileIn(BaseModel):
    role: str | None = None
    company: str | None = None
    referral_source: str | None = None
    icp: str | None = None
    target_market: str | None = None
    audience: str | None = None
    industry: str | None = None
    target_roles: str | None = None
    good_score: int = 7
    tone: str = "professional"


def _slim_account(row: dict) -> dict:
    score = None
    for key in ("eval_2", "eval_1"):
        ev = row.get(key)
        if isinstance(ev, dict) and ev.get("score") is not None:
            score = ev["score"]
            break
    hyp = row.get("hypothesis_2") or row.get("hypothesis_1")
    angle = hyp.get("angle") if isinstance(hyp, dict) else None
    dossier = row.get("dossier") if isinstance(row.get("dossier"), dict) else {}
    search_commands = (
        row.get("search_commands") if isinstance(row.get("search_commands"), dict) else {}
    )
    return {
        "id": row["id"],
        "run_id": row.get("run_id"),
        "name": row["name"],
        "domain": row.get("domain"),
        "status": row["status"],
        "batch_number": row.get("batch_number"),
        "score": score,
        "angle": angle,
        "key_insight": dossier.get("key_insight"),
        "target_titles": search_commands.get("target_titles") or [],
        "pipedrive_org_id": row.get("pipedrive_org_id"),
        "updated_at": row.get("updated_at"),
    }


_NO_CACHE = {"Cache-Control": "no-store"}


@app.get("/")
async def landing():
    if not LANDING.exists():
        raise HTTPException(404, "frontend/landing.html not found")
    return FileResponse(LANDING, headers=_NO_CACHE)


@app.get("/dashboard")
async def dashboard():
    if not FRONTEND.exists():
        raise HTTPException(404, "frontend/index.html not found")
    return FileResponse(FRONTEND, headers=_NO_CACHE)


@app.get("/onboarding")
async def onboarding():
    if not ONBOARDING.exists():
        raise HTTPException(404, "frontend/onboarding.html not found")
    return FileResponse(ONBOARDING, headers=_NO_CACHE)


@app.get("/api/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    profile = await db.get_profile(user["id"])
    return profile or {"onboarding_completed": False}


@app.post("/api/profile")
async def save_profile(body: ProfileIn, user: dict = Depends(get_current_user)):
    data = body.model_dump()
    data["onboarding_completed"] = True
    return await db.upsert_profile(user["id"], user.get("email"), data)


@app.post("/api/runs")
async def start_run(body: StartRunBody, user: dict = Depends(get_current_user)):
    if body.accounts:
        raw_accounts = [
            {"name": a.name, "domain": a.domain, "row_index": None}
            for a in body.accounts
            if a.name.strip()
        ]
        if not raw_accounts:
            raise HTTPException(400, "No accounts to process")
        sheet_id = (body.sheet_id or "manual").strip()
    else:
        sheet_id = (body.sheet_id or settings.google_sheet_id).strip()
        if not sheet_id:
            raise HTTPException(400, "sheet_id is required")
        try:
            raw_accounts = sheets.get_accounts(sheet_id)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if not raw_accounts:
            raise HTTPException(400, "Sheet has no accounts to process")

    profile = await db.get_profile(user["id"])
    threshold = (profile or {}).get("good_score") or settings.relevance_threshold
    tone = (profile or {}).get("tone") or "professional"

    run_id = await db.create_run(body.value_prop, sheet_id, user["id"])
    account_ids = await db.insert_accounts(run_id, raw_accounts, user["id"])
    queue_accounts = [
        {**raw, "id": aid} for raw, aid in zip(raw_accounts, account_ids)
    ]
    task = asyncio.create_task(
        queue_manager.run_pipeline(
            run_id, queue_accounts, body.value_prop, threshold, tone
        )
    )
    _tasks[run_id] = task
    task.add_done_callback(lambda _t, rid=run_id: _tasks.pop(rid, None))
    return {"run_id": run_id, "total": len(queue_accounts)}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: int, user: dict = Depends(get_current_user)):
    run = await db.get_run(run_id, user["id"])
    if not run:
        raise HTTPException(404, "run not found")
    return run


@app.get("/api/runs/{run_id}/accounts")
async def get_run_accounts(run_id: int, user: dict = Depends(get_current_user)):
    rows = await db.get_run_accounts(run_id, user["id"])
    return [_slim_account(r) for r in rows]


@app.get("/api/accounts")
async def list_accounts(limit: int = 500, user: dict = Depends(get_current_user)):
    rows = await db.get_all_accounts(user["id"], limit)
    return [_slim_account(r) for r in rows]


@app.get("/api/runs")
async def list_runs(limit: int = 10, user: dict = Depends(get_current_user)):
    return await db.get_recent_runs(user["id"], limit)


@app.get("/api/accounts/{account_id}")
async def get_account(account_id: int, user: dict = Depends(get_current_user)):
    row = await db.get_account(account_id, user["id"])
    if not row:
        raise HTTPException(404, "account not found")
    return row


@app.get("/api/accounts/{account_id}/logs")
async def get_account_logs(account_id: int, user: dict = Depends(get_current_user)):
    # Authorization: confirms this account belongs to the caller before
    # returning its logs (the logs table itself has no user_id column).
    row = await db.get_account(account_id, user["id"])
    if not row:
        raise HTTPException(404, "account not found")
    return await db.get_account_logs(account_id)


@app.delete("/api/runs/{run_id}")
async def cancel_run(run_id: int, user: dict = Depends(get_current_user)):
    run = await db.get_run(run_id, user["id"])
    if not run:
        raise HTTPException(404, "run not found")
    task = _tasks.get(run_id)
    if task and not task.done():
        task.cancel()
    await db.update_run_status(run_id, "cancelled")
    return {"run_id": run_id, "status": "cancelled"}


@app.get("/api/analytics")
async def analytics(user: dict = Depends(get_current_user)):
    return await db.get_analytics(user["id"])


@app.get("/api/sheets/preview")
async def preview_sheet(
    sheet_id: str | None = None, user: dict = Depends(get_current_user)
):
    target = (sheet_id or settings.google_sheet_id).strip()
    if not target:
        raise HTTPException(400, "sheet_id is required")
    try:
        accounts = sheets.get_accounts(target)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"sheet_id": target, "total": len(accounts), "preview": accounts[:10]}
